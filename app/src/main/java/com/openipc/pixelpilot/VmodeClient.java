package com.openipc.pixelpilot;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.IntFunction;

/**
 * UDP transport of the VMODE1 protocol to the air unit (docs/xr/presets-design.md): one socket for the session, so
 * replies and the 1 Hz state beacon come back to it. A request is resent every {@code retryMs} until a reply with its
 * {@code seq} arrives, at most {@code tries} times; later duplicates of that reply are dropped. Callbacks run on the
 * client's receive or retry thread.
 */
final class VmodeClient implements VmodeSender, AutoCloseable {
    /** The air unit's end of the wfb tunnel and the receiver's port (proposed; see the design's open points). */
    static final String AIR_RECEIVER = "10.5.0.10:9998";   // NOSONAR: tunnel address
    /** Debug override "host:port", e.g. a fake air on the PC (scripts/quest/vmode_fake.py); empty = the air unit. */
    static final String PREF_TARGET = "vmode_air";

    interface Listener {
        /** A reply to one of our requests, or a state beacon (seq -1). */
        void onReply(VmodeProtocol.Reply reply);

        /** No reply to request {@code verb} after every try. */
        void onNoReply(String verb);
    }

    private final InetSocketAddress target;
    private final Listener listener;
    private final long retryMs;
    private final int tries;
    private final ScheduledExecutorService retries = Executors.newSingleThreadScheduledExecutor();
    private final Map<Integer, ScheduledFuture<?>> pending = new ConcurrentHashMap<>();
    private DatagramSocket socket;
    private int nextSeq = 1;

    VmodeClient(InetSocketAddress target, Listener listener, long retryMs, int tries) {
        this.target = target;
        this.listener = listener;
        this.retryMs = retryMs;
        this.tries = tries;
    }

    /** {@code hostPort} "a.b.c.d:port" (an IPv4 literal: no DNS on the UI thread), else {@link #AIR_RECEIVER}. */
    static InetSocketAddress target(String hostPort) {
        String t = hostPort != null && hostPort.matches("\\d+\\.\\d+\\.\\d+\\.\\d+:\\d+") ? hostPort : AIR_RECEIVER;
        int colon = t.lastIndexOf(':');
        return new InetSocketAddress(t.substring(0, colon), Integer.parseInt(t.substring(colon + 1)));
    }

    void start() throws SocketException {
        socket = new DatagramSocket();
        Thread receiver = new Thread(this::receive, "vmode-rx");
        receiver.setDaemon(true);
        receiver.start();
    }

    @Override
    public synchronized int request(String verb, IntFunction<String> build) {
        final int seq = nextSeq++;
        final byte[] data = build.apply(seq).getBytes(StandardCharsets.US_ASCII);
        final int[] sent = {1};
        // Registered before the first send, so a fast reply always finds its seq pending.
        pending.put(seq, retries.scheduleWithFixedDelay(() -> {
            if (sent[0]++ >= tries) {
                ScheduledFuture<?> f = pending.remove(seq);
                if (f != null) {
                    f.cancel(false);
                    listener.onNoReply(verb);
                }
                return;
            }
            send(data);
        }, retryMs, retryMs, TimeUnit.MILLISECONDS));
        send(data);
        return seq;
    }

    private void send(byte[] data) {
        try {
            socket.send(new DatagramPacket(data, data.length, target));
        } catch (IOException | RuntimeException ignored) {
            // counts as a lost try; no route (tunnel down) ends as onNoReply
        }
    }

    private void receive() {
        byte[] buf = new byte[2048];
        while (!socket.isClosed()) {
            DatagramPacket p = new DatagramPacket(buf, buf.length);
            try {
                socket.receive(p);
            } catch (IOException e) {
                return;   // closed
            }
            deliver(VmodeProtocol.parse(new String(p.getData(), 0, p.getLength(), StandardCharsets.US_ASCII)));
        }
    }

    private void deliver(VmodeProtocol.Reply r) {
        if (r == null) return;
        if (r.seq() >= 0) {
            ScheduledFuture<?> f = pending.remove(r.seq());
            if (f == null) return;   // a duplicate of a reply already delivered, or not ours
            f.cancel(false);
        }
        listener.onReply(r);
    }

    @Override
    public void close() {
        retries.shutdownNow();
        if (socket != null) socket.close();
    }
}
