package com.openipc.pixelpilot;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import org.junit.Test;

public class TunToUdpPumpTest {

    /** Scripted TUN: each step is one wait result, followed (if readable) by one read result. */
    private static final class FakeTun implements TunToUdpPump.Tun {
        final Deque<Boolean> waits = new ArrayDeque<>();
        final Deque<byte[]> reads = new LinkedList<>();  // null = read returns 0; empty array = -1 (LinkedList allows null)
        int awaitCalls, readCalls, lastTimeout;

        @Override
        public boolean awaitReadable(int timeoutMs) {
            awaitCalls++;
            lastTimeout = timeoutMs;
            return waits.isEmpty() ? false : waits.pop();
        }

        @Override
        public int read(byte[] buffer) {
            readCalls++;
            byte[] r = reads.pop();
            if (r == null) return 0;
            if (r.length == 0) return -1;
            System.arraycopy(r, 0, buffer, 0, r.length);
            return r.length;
        }
    }

    /** Stops the pump after a fixed number of loop checks. */
    private static final class Budget {
        int left;
        Budget(int n) { left = n; }
        boolean next() { return left-- > 0; }
    }

    @Test
    public void idleTunnelWaitsInsteadOfReading() throws Exception {
        FakeTun tun = new FakeTun();  // never readable
        List<byte[]> sent = new ArrayList<>();
        Budget budget = new Budget(5);

        TunToUdpPump.run(tun, sent::add, budget::next, new byte[64]);

        assertEquals(5, tun.awaitCalls);
        assertEquals(0, tun.readCalls);  // the old loop read (and got 0) on every turn: a busy spin
        assertEquals(TunToUdpPump.WAIT_MS, tun.lastTimeout);
        assertEquals(0, sent.size());
    }

    @Test
    public void everyReadIsPrecededByAWait() throws Exception {
        FakeTun tun = new FakeTun();
        tun.waits.add(true);
        tun.reads.add(null);  // readable but read returns 0 (spurious wake-up)
        tun.waits.add(true);
        tun.reads.add(new byte[] {1, 2, 3});
        List<byte[]> sent = new ArrayList<>();

        long n = TunToUdpPump.run(tun, sent::add, new Budget(4)::next, new byte[64]);

        assertEquals(1, n);
        assertEquals(4, tun.awaitCalls);
        assertEquals(2, tun.readCalls);
        assertArrayEquals(new byte[] {0, 3, 1, 2, 3}, sent.get(0));
    }

    @Test
    public void endOfStreamStopsThePump() throws Exception {
        FakeTun tun = new FakeTun();
        tun.waits.add(true);
        tun.reads.add(new byte[0]);  // -1
        List<byte[]> sent = new ArrayList<>();

        TunToUdpPump.run(tun, sent::add, new Budget(100)::next, new byte[64]);

        assertEquals(1, tun.awaitCalls);
        assertEquals(0, sent.size());
    }

    @Test
    public void frameHasBigEndianLengthPrefix() {
        byte[] packet = new byte[300];
        packet[0] = 7;
        packet[299] = 9;
        byte[] f = TunToUdpPump.frame(packet, 300);
        assertEquals(302, f.length);
        assertEquals(1, f[0]);           // 300 = 0x012C
        assertEquals((byte) 0x2C, f[1]);
        assertEquals(7, f[2]);
        assertEquals(9, f[301]);
    }
}
