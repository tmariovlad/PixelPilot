package com.openipc.pixelpilot;

import java.io.IOException;
import java.util.function.BooleanSupplier;

/**
 * Moves packets from the VPN (TUN) interface to wfb-ng's local UDP port, each prefixed with its length
 * (2 bytes, network byte order).
 *
 * <p>The TUN descriptor from {@code VpnService.Builder.establish()} is non-blocking by default, and a read on
 * an empty non-blocking descriptor returns 0 instead of blocking (libcore {@code IoBridge.read}, EAGAIN).
 * Reading in a loop therefore spins a whole core while the tunnel is idle. The pump waits for the descriptor
 * to become readable (with a timeout, so a stop request is still seen) before every read.
 */
final class TunToUdpPump {
    /** How long one wait for data may block before the running flag is checked again. */
    static final int WAIT_MS = 100;

    interface Tun {
        /** Blocks up to {@code timeoutMs} until data can be read; false on timeout. */
        boolean awaitReadable(int timeoutMs) throws IOException;

        /** Like {@link java.io.InputStream#read(byte[])}: -1 at end of stream, 0 if nothing was ready. */
        int read(byte[] buffer) throws IOException;
    }

    interface Sink {
        void send(byte[] frame) throws IOException;
    }

    private TunToUdpPump() {}

    /** Pumps until {@code running} turns false or the TUN reaches end of stream; returns the packets sent. */
    static long run(Tun tun, Sink sink, BooleanSupplier running, byte[] buffer) throws IOException {
        long sent = 0;
        while (running.getAsBoolean()) {
            if (!tun.awaitReadable(WAIT_MS)) continue;
            int length = tun.read(buffer);
            if (length == -1) break;
            if (length == 0) continue;
            sink.send(frame(buffer, length));
            sent++;
        }
        return sent;
    }

    /** The first {@code length} bytes of {@code packet}, prefixed with the length (big-endian, 2 bytes). */
    static byte[] frame(byte[] packet, int length) {
        byte[] out = new byte[2 + length];
        out[0] = (byte) ((length >> 8) & 0xFF);
        out[1] = (byte) (length & 0xFF);
        System.arraycopy(packet, 0, out, 2, length);
        return out;
    }
}
