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
        isRunning = true;
        startVpnThreads(vpnInterface);
        Log.i(TAG, "VPN tunnel started");
        return true;
    }

    /** Stops the traffic threads and closes the TUN interface. */
    private synchronized void stopTunnel() {
        isRunning = false;
        if (udpToVpnThread != null) {
            udpToVpnThread.interrupt();
        }
        if (vpnToUdpThread != null) {
            vpnToUdpThread.interrupt();
        }
        if (vpnInterface != null) {
            try {
                vpnInterface.close();
            } catch (IOException e) {
                Log.e(TAG, "Failed to close VPN interface", e);
            }
            vpnInterface = null;
        }
        Log.i(TAG, "VPN tunnel stopped");
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
    private void startVpnThreads(final ParcelFileDescriptor vpnInterfacePfd) {
        // Prepare input (read from VPN) and output (write to VPN) streams
        final FileInputStream vpnInput = new FileInputStream(vpnInterfacePfd.getFileDescriptor());
        final FileOutputStream vpnOutput = new FileOutputStream(vpnInterfacePfd.getFileDescriptor());

        // 1) Thread to capture rtl8812 → [ local UDP:8000 → TUN ]
        udpToVpnThread = new Thread(new Runnable() {
            @Override
            public void run() {
                Log.i(TAG, "UDP (WFB) → VPN thread started");
                byte[] buffer = new byte[4024];

                try (DatagramSocket socket = new DatagramSocket(null)) {
                    // Set reuse address before binding
                    socket.setReuseAddress(true);
                    // Bind to local UDP port 8000 on all interfaces
                    socket.bind(new InetSocketAddress(8000));

                    while (isRunning) {
                        // Read data from UDP into buffer
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);

                        // log packet data and lentgh

                        if (packet.getLength() < 1)
                            continue;

                        // Write to the VPN interface (TUN)
                        try{
                            vpnOutput.write(packet.getData(), 2, packet.getLength()-2);
                        } catch (IOException e) {
                            Log.e(TAG, "UDP → VPN thread error", e);
                        }
                    }
                } catch (IOException e) {
                    Log.e(TAG, "UDP → VPN thread error", e);
                }
                Log.i(TAG, "UDP → VPN thread stopped");
            }
        }, "UdpToVpnThread");

        // 2) Thread to capture [ TUN → local UDP:8001 ] → rtl8812
        vpnToUdpThread = new Thread(new Runnable() {
            @Override
            public void run() {
                Log.i(TAG, "VPN → UDP (WFB) thread started");
                byte[] buffer = new byte[1024];

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
