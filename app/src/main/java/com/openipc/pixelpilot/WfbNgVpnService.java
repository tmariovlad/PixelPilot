package com.openipc.pixelpilot;

import android.net.VpnService;
import android.content.Intent;
import android.os.Binder;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructPollfd;
import android.util.Log;

import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import android.util.Log;

import java.net.InetAddress;
import java.net.UnknownHostException;

public class WfbNgVpnService extends VpnService {
    private static final String TAG = "WfbNgVpnService";

    // The TUN interface descriptor
    private ParcelFileDescriptor vpnInterface = null;

    // Threads for bidirectional traffic
    private Thread udpToVpnThread;
    private Thread vpnToUdpThread;
    // UDP:8000 socket of udpToVpnThread; closing it is what wakes that thread's blocking receive().
    private DatagramSocket udpInSocket;
    // Stop waits this long for both threads: the TUN pump notices within one poll timeout.
    private static final long STOP_TIMEOUT_MS = 3 * TunToUdpPump.WAIT_MS;

    // Control flags
    private volatile boolean isRunning = false;

    // Local binder for WfbServiceControl.Binding. Activities bind instead of calling startService(): Android 8+
    // refuses startService() while the app's uid is idle, which is the case when an activity is created or resumed
    // with the display off (USB attach with the headset asleep) -> BackgroundServiceStartNotAllowedException.
    // bindService() is not subject to that check, and the tunnel lives exactly as long as an activity is bound.
    private final Binder tunnelBinder = new Binder();

    @Override
    public IBinder onBind(Intent intent) {
        if (isTunnelIntent(intent)) {
            startTunnel();
            return tunnelBinder;
        }
        return super.onBind(intent);  // VpnService.SERVICE_INTERFACE: the system's binding, must stay intact
    }

    // establish() makes the system bind too (Vpn.establish binds with SERVICE_INTERFACE), so the service can outlive
    // our unbind. Returning true makes Android call onRebind on the next bind instead of handing back the cached
    // binder without a callback; otherwise the tunnel would stay down after an onPause/onResume (headset asleep).
    @Override
    public boolean onUnbind(Intent intent) {
        if (isTunnelIntent(intent)) {
            stopTunnel();
            return true;
        }
        return super.onUnbind(intent);
    }

    @Override
    public void onRebind(Intent intent) {
        if (isTunnelIntent(intent)) {
            startTunnel();
        } else {
            super.onRebind(intent);
        }
    }

    private static boolean isTunnelIntent(Intent intent) {
        return intent != null && WfbServiceControl.ACTION_BIND_TUNNEL.equals(intent.getAction());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP_SERVICE".equals(intent.getAction())) {
            stopTunnel();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!startTunnel()) {
            stopSelf();
            return START_NOT_STICKY;
        }
        return START_STICKY;
    }

    /** Establishes the TUN interface and starts the traffic threads, unless already running. */
    private synchronized boolean startTunnel() {
        if (isRunning) {
            Log.w(TAG, "VPN tunnel is already running");
            return true;
        }
        try {
            vpnInterface = establishVpnInterface();
        } catch (Exception e) {
            Log.e(TAG, "Failed to establish VPN interface", e);
            return false;
        }
        if (vpnInterface == null) {
            // establish() returns null when VPN permission is gone (revoked, or another always-on VPN took over);
            // the video does not use the tunnel, so the app goes on without it (VpnService.Builder.establish docs)
            Log.w(TAG, "VPN interface not established (permission revoked or not prepared): tunnel off");
            return false;
        }
        try {
            udpInSocket = bindUdpIn();
        } catch (IOException e) {
            Log.e(TAG, "Failed to bind UDP:8000 for the VPN tunnel", e);
            closeQuietly(vpnInterface);
            vpnInterface = null;
            return false;
        }
        isRunning = true;
        startVpnThreads(vpnInterface, udpInSocket);
        Log.i(TAG, "VPN tunnel started");
        return true;
    }

    /**
     * Stops the traffic threads, then closes the TUN interface: closing it first made the pump's poll/read fail with
     * EBADF. The UDP socket is closed as part of the stop request, since that is what wakes a blocking receive().
     */
    private synchronized void stopTunnel() {
        final DatagramSocket udpIn = udpInSocket;
        try {
            boolean clean = OrderedShutdown.stop(() -> {
                isRunning = false;
                if (udpIn != null) udpIn.close();
            }, STOP_TIMEOUT_MS, vpnInterface, vpnToUdpThread, udpToVpnThread);
            if (!clean) Log.w(TAG, "VPN threads still running after " + STOP_TIMEOUT_MS + " ms; interface closed anyway");
        } catch (IOException e) {
            Log.e(TAG, "Failed to close VPN interface", e);
        }
        vpnInterface = null;
        udpInSocket = null;
        udpToVpnThread = null;
        vpnToUdpThread = null;
        Log.i(TAG, "VPN tunnel stopped");
    }

    /** UDP:8000, where wfb-ng hands over the packets received for the tunnel. */
    private static DatagramSocket bindUdpIn() throws IOException {
        DatagramSocket socket = new DatagramSocket(null);
        socket.setReuseAddress(true);
        socket.bind(new InetSocketAddress(8000));
        return socket;
    }

    private static void closeQuietly(ParcelFileDescriptor pfd) {
        if (pfd == null) return;
        try {
            pfd.close();
        } catch (IOException e) {
            Log.e(TAG, "Failed to close VPN interface", e);
        }
    }

    /**
     * Construct and return the VPN (TUN) interface using VpnService.Builder
     */
    private ParcelFileDescriptor establishVpnInterface() throws Exception {
        // Build a new VPN interface using the VpnService.Builder
        Builder builder = new Builder();

        // Give the interface a human-readable name
        builder.setSession("wfb-ng");

        // Set the interface address to 10.5.0.3/24
        // On many devices, addAddress requires prefix length instead of a netmask
        builder.addAddress("10.5.0.3", 24);

        // Route only 10.5.0.0/24 through this interface
        builder.addRoute("10.5.0.0", 24);

        // Same MTU as wfb_tun on the air unit, so no packet is larger than the tunnel can carry
        builder.setMtu(TunFraming.TUN_MTU);

        // You can optionally set DNS servers if needed
        // builder.addDnsServer("8.8.8.8");

        // Build and return the file descriptor for the TUN interface
        ParcelFileDescriptor pfd = builder.establish();
        Log.i(TAG, "VPN interface (wfb-ng) established with IP 10.5.0.3/24");
        return pfd;
    }

    /**
     * Start the bidirectional traffic threads:
     *  1) A thread to read from local UDP port 8000 and inject into VPN
     *  2) A thread to read from VPN and send to local UDP port 8001
     */
    private void startVpnThreads(final ParcelFileDescriptor vpnInterfacePfd, final DatagramSocket udpIn) {
        // Prepare input (read from VPN) and output (write to VPN) streams
        final FileInputStream vpnInput = new FileInputStream(vpnInterfacePfd.getFileDescriptor());
        final FileOutputStream vpnOutput = new FileOutputStream(vpnInterfacePfd.getFileDescriptor());

        // 1) Thread to capture rtl8812 → [ local UDP:8000 → TUN ]
        udpToVpnThread = new Thread(new Runnable() {
            @Override
            public void run() {
                Log.i(TAG, "UDP (WFB) → VPN thread started");
                byte[] buffer = new byte[4024];

                try (DatagramSocket socket = udpIn) {
                    while (isRunning) {
                        // Read data from UDP into buffer
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);

                        // log packet data and lentgh

                        // wfb_tun may put several framed packets in one datagram (or none: keep-alive)
                        try {
                            TunFraming.forEachPacket(packet.getData(), packet.getLength(), vpnOutput::write);
                        } catch (IOException e) {
                            Log.e(TAG, "UDP → VPN thread error", e);
                        }
                    }
                } catch (IOException e) {
                    // stopTunnel closes the socket to end receive(); only a failure while running is an error
                    if (isRunning) Log.e(TAG, "UDP → VPN thread error", e);
                }
                Log.i(TAG, "UDP → VPN thread stopped");
            }
        }, "UdpToVpnThread");

        // 2) Thread to capture [ TUN → local UDP:8001 ] → rtl8812
        vpnToUdpThread = new Thread(new Runnable() {
            @Override
            public void run() {
                Log.i(TAG, "VPN → UDP (WFB) thread started");
                byte[] buffer = new byte[TunFraming.TUN_MTU];  // one TUN read = one whole packet

                try (DatagramSocket socket = new DatagramSocket()) {
                    socket.setReuseAddress(true);
                    final InetSocketAddress wfbTx = new InetSocketAddress("127.0.0.1", 8001);
                    TunToUdpPump.run(
                            pollingTun(vpnInterfacePfd.getFileDescriptor(), vpnInput),
                            frame -> socket.send(new DatagramPacket(frame, frame.length, wfbTx)),
                            () -> isRunning,
                            buffer);
                } catch (IOException e) {
                    Log.e(TAG, "VPN→UDP thread error", e);
                }
                Log.i(TAG, "VPN → UDP thread stopped");
            }
        }, "VpnToUdpThread");

        // Start the two threads
        udpToVpnThread.start();
        vpnToUdpThread.start();
        Log.i(TAG, "VPN threads started");
    }

    /** TUN reads that wait for data with poll(2) instead of spinning on the non-blocking descriptor. */
    private static TunToUdpPump.Tun pollingTun(final FileDescriptor fd, final FileInputStream in) {
        final StructPollfd[] pollFds = {new StructPollfd()};
        pollFds[0].fd = fd;
        pollFds[0].events = (short) OsConstants.POLLIN;
        return new TunToUdpPump.Tun() {
            @Override
            public boolean awaitReadable(int timeoutMs) throws IOException {
                try {
                    return Os.poll(pollFds, timeoutMs) > 0;
                } catch (ErrnoException e) {
                    if (e.errno == OsConstants.EINTR) return false;
                    throw new IOException("poll on the VPN interface failed", e);
                }
            }

            @Override
            public int read(byte[] buffer) throws IOException {
                return in.read(buffer);
            }
        };
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.i(TAG, "VPN Service destroyed");
        stopTunnel();
    }
}
