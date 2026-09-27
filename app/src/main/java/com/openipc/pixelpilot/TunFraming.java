package com.openipc.pixelpilot;

/**
 * The wfb-ng tunnel framing (wfb_tun, wfb-ng/src/wfb_tun.c): each IP packet is sent as a big-endian u16 length
 * followed by the packet, and one UDP datagram may carry several such packets (wfb_tun aggregates for up to
 * agg_timeout_ms, 5 ms by default) or none (an empty keep-alive datagram).
 */
final class TunFraming {
    /** wfb_tun's MTU (1445) minus the 2-byte header: the largest IP packet the tunnel carries (wfb_tun.c:37,332). */
    static final int TUN_MTU = 1443;
    static final int HEADER_BYTES = 2;

    interface PacketSink {
        void accept(byte[] buffer, int offset, int length) throws java.io.IOException;
    }

    private TunFraming() {}

    /** One packet, framed: the first {@code length} bytes of {@code packet} behind a big-endian u16 length. */
    static byte[] encode(byte[] packet, int length) {
        byte[] out = new byte[HEADER_BYTES + length];
        out[0] = (byte) ((length >> 8) & 0xFF);
        out[1] = (byte) (length & 0xFF);
        System.arraycopy(packet, 0, out, HEADER_BYTES, length);
        return out;
    }

    /**
     * Hands every framed packet in {@code datagram[0, length)} to {@code sink}, in order. Stops at a header that
     * does not fit or claims more bytes than remain (a truncated or foreign datagram). Returns the packets delivered.
     */
    static int forEachPacket(byte[] datagram, int length, PacketSink sink) throws java.io.IOException {
        int offset = 0;
        int count = 0;
        while (offset + HEADER_BYTES <= length) {
            int size = ((datagram[offset] & 0xFF) << 8) | (datagram[offset + 1] & 0xFF);
            int start = offset + HEADER_BYTES;
            if (size == 0 || start + size > length) break;
            sink.accept(datagram, start, size);
            count++;
            offset = start + size;
        }
        return count;
    }
}
