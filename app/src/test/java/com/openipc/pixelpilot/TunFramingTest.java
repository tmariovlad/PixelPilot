package com.openipc.pixelpilot;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.junit.Test;

public class TunFramingTest {

    private static List<byte[]> split(byte[] datagram, int length) throws Exception {
        List<byte[]> out = new ArrayList<>();
        TunFraming.forEachPacket(datagram, length, (b, off, len) -> out.add(Arrays.copyOfRange(b, off, off + len)));
        return out;
    }

    private static byte[] concat(byte[]... parts) {
        int n = 0;
        for (byte[] p : parts) n += p.length;
        byte[] out = new byte[n];
        int o = 0;
        for (byte[] p : parts) {
            System.arraycopy(p, 0, out, o, p.length);
            o += p.length;
        }
        return out;
    }

    @Test
    public void encodeWritesABigEndianLengthPrefix() {
        byte[] packet = new byte[300];
        packet[0] = 7;
        packet[299] = 9;
        byte[] f = TunFraming.encode(packet, 300);
        assertEquals(302, f.length);
        assertEquals(1, f[0]);  // 300 = 0x012C
        assertEquals((byte) 0x2C, f[1]);
        assertEquals(7, f[2]);
        assertEquals(9, f[301]);
    }

    @Test
    public void singlePacketDatagram() throws Exception {
        byte[] d = TunFraming.encode(new byte[] {1, 2, 3}, 3);
        List<byte[]> got = split(d, d.length);
        assertEquals(1, got.size());
        assertArrayEquals(new byte[] {1, 2, 3}, got.get(0));
    }

    /** wfb_tun aggregates: before this class the app wrote all three packets to tun0 as one corrupt packet. */
    @Test
    public void aggregatedDatagramYieldsEveryPacketInOrder() throws Exception {
        byte[] d = concat(TunFraming.encode(new byte[] {1}, 1), TunFraming.encode(new byte[] {2, 2}, 2),
                TunFraming.encode(new byte[] {3, 3, 3}, 3));
        List<byte[]> got = split(d, d.length);
        assertEquals(3, got.size());
        assertArrayEquals(new byte[] {1}, got.get(0));
        assertArrayEquals(new byte[] {2, 2}, got.get(1));
        assertArrayEquals(new byte[] {3, 3, 3}, got.get(2));
    }

    @Test
    public void emptyKeepAliveAndTruncatedTailDeliverNothingBogus() throws Exception {
        assertEquals(0, split(new byte[0], 0).size());  // wfb_tun keep-alive
        byte[] d = concat(TunFraming.encode(new byte[] {5, 5}, 2), new byte[] {0, 9, 1});  // 2nd claims 9 bytes, has 1
        List<byte[]> got = split(d, d.length);
        assertEquals(1, got.size());
        assertArrayEquals(new byte[] {5, 5}, got.get(0));
    }

    @Test
    public void onlyTheValidPartOfTheBufferIsRead() throws Exception {
        byte[] buf = new byte[64];  // receive buffer larger than the datagram, stale bytes after it
        byte[] d = TunFraming.encode(new byte[] {4, 4}, 2);
        System.arraycopy(d, 0, buf, 0, d.length);
        buf[d.length] = 0;
        buf[d.length + 1] = 3;
        assertEquals(1, split(buf, d.length).size());
    }
}
