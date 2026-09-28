package com.openipc.pixelpilot.stats;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;

/**
 * Subscribes to waybeam's RTP timing sidecar on the air unit (default 10.5.0.10:5602 over the wfb tunnel), keeps the
 * subscription alive, and runs the SYNC exchange for the air↔Quest clock offset. Each MSG_FRAME goes to the listener
 * with its receive time on the Quest's CLOCK_MONOTONIC (System.nanoTime on Android). One background thread.
 */
public final class SidecarClient implements AutoCloseable {
    public static final String AIR_HOST = "10.5.0.10";  // NOSONAR: tunnel address of the air unit
    public static final int AIR_PORT = 5602;
    public static final int SUBSCRIBE_MS = 2000;        // the air drops a subscriber after 5 s of silence
    public static final int SYNC_MS = 1000;
    private static final int RECV_TIMEOUT_MS = 100;

    public interface Listener {
        void onFrame(SidecarProtocol.Frame frame, long questRecvUs);
    }

    private final InetSocketAddress air;
    private final Listener listener;
    private final int subscribeMs, syncMs;
    private final ClockSync clock = new ClockSync(16);
    private volatile boolean running;
    private DatagramSocket socket;
    private Thread thread;

    public SidecarClient(InetSocketAddress air, Listener listener, int subscribeMs, int syncMs) {
        this.air = air;
        this.listener = listener;
        this.subscribeMs = subscribeMs;
        this.syncMs = syncMs;
    }

    public ClockSync clock() {
        return clock;
    }

    static long nowUs() {
        return System.nanoTime() / 1000;
    }

    public synchronized void start() throws SocketException {
        if (running) return;
        socket = new DatagramSocket();
        socket.setSoTimeout(RECV_TIMEOUT_MS);
        running = true;
        thread = new Thread(this::loop, "sidecar");
        thread.setDaemon(true);
        thread.start();
    }

    private void send(byte[] d) {
        try {
            socket.send(new DatagramPacket(d, d.length, air));
        } catch (IOException ignored) {
            // no route while the tunnel is down: the next period tries again
        }
    }

    private void loop() {
        byte[] buf = new byte[256];
        long nextSubscribe = 0, nextSync = 0;
        while (running) {
            long nowMs = System.nanoTime() / 1_000_000;
            if (nowMs >= nextSubscribe) {
                send(SidecarProtocol.subscribe());
                nextSubscribe = nowMs + subscribeMs;
            }
            if (nowMs >= nextSync) {
                send(SidecarProtocol.syncRequest(nowUs()));
                nextSync = nowMs + syncMs;
            }
            DatagramPacket p = new DatagramPacket(buf, buf.length);
            try {
                socket.receive(p);
            } catch (SocketTimeoutException e) {
                continue;
            } catch (IOException e) {
                if (!running) break;
                continue;
            }
            long recvUs = nowUs();
            int type = SidecarProtocol.messageType(p.getData(), p.getLength());
            if (type == SidecarProtocol.MSG_FRAME) {
                SidecarProtocol.Frame f = SidecarProtocol.parseFrame(p.getData(), p.getLength());
                if (f != null) listener.onFrame(f, recvUs);
            } else if (type == SidecarProtocol.MSG_SYNC_RESP) {
                SidecarProtocol.SyncResponse r = SidecarProtocol.parseSyncResponse(p.getData(), p.getLength());
                if (r != null) clock.add(r.t1Us, r.t2Us, r.t3Us, recvUs);
            }
        }
    }

    @Override
    public void close() {
        Thread t;
        synchronized (this) {
            if (!running) return;
            running = false;
            t = thread;
        }
        socket.close();
        try {
            t.join(1000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
