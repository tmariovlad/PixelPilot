package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

/** SidecarClient against a fake waybeam sidecar on localhost UDP. */
public class SidecarClientTest {
    private static final long AIR_AHEAD_US = 3_000_000_000L;   // the fake air's clock runs 3000 s ahead
    private DatagramSocket fakeAir;
    private SidecarClient client;
    private final List<SidecarProtocol.Frame> frames = new CopyOnWriteArrayList<>();
    private final List<Long> recvUs = new CopyOnWriteArrayList<>();

    @Before public void setUp() throws Exception {
        fakeAir = new DatagramSocket(0, InetAddress.getLoopbackAddress());
        fakeAir.setSoTimeout(3000);
    }

    @After public void tearDown() {
        if (client != null) client.close();
        fakeAir.close();
    }

    private void start(int subscribeMs, int syncMs, CountDownLatch gotFrame) throws Exception {
        client = new SidecarClient(new InetSocketAddress(InetAddress.getLoopbackAddress(), fakeAir.getLocalPort()),
                (f, questRecvUs) -> {
                    frames.add(f);
                    recvUs.add(questRecvUs);
                    gotFrame.countDown();
                }, subscribeMs, syncMs);
        client.start();
    }

    private static long questNowUs() {
        return System.nanoTime() / 1000;
    }

    @Test public void subscribesThenReceivesFramesAndSyncsTheClock() throws Exception {
        CountDownLatch gotFrame = new CountDownLatch(1);
        start(2000, 50, gotFrame);
        byte[] buf = new byte[64];
        SocketAddress probe = null;
        boolean sawSubscribe = false, synced = false;
        long deadline = System.currentTimeMillis() + 3000;
        while ((!sawSubscribe || !synced) && System.currentTimeMillis() < deadline) {
            DatagramPacket p = new DatagramPacket(buf, buf.length);
            fakeAir.receive(p);
            probe = p.getSocketAddress();
            int type = SidecarProtocol.messageType(p.getData(), p.getLength());
            if (type == SidecarProtocol.MSG_SUBSCRIBE) {
                sawSubscribe = true;
                byte[] f = SidecarProtocolTest.frame(0xABCD, 9000, 0, 1, 100, 12, 1, 2, true, false, false);
                fakeAir.send(new DatagramPacket(f, f.length, probe));
            } else if (type == SidecarProtocol.MSG_SYNC_REQ) {
                long t1 = ByteBuffer.wrap(p.getData(), 8, 8).getLong();
                long t = questNowUs() + AIR_AHEAD_US;
                byte[] r = SidecarProtocolTest.syncResp(t1, t, t);
                fakeAir.send(new DatagramPacket(r, r.length, probe));
                synced = true;
            }
        }
        assertTrue("no MSG_SUBSCRIBE", sawSubscribe);
        assertTrue(gotFrame.await(2, TimeUnit.SECONDS));
        assertEquals(0xABCD, frames.get(0).ssrc);
        assertEquals(9000, frames.get(0).rtpTs);
        long age = questNowUs() - recvUs.get(0);
        assertTrue("receive time on the Quest's monotonic clock", age >= 0 && age < 3_000_000);
        long waitUntil = System.currentTimeMillis() + 2000;
        while (!client.clock().synced() && System.currentTimeMillis() < waitUntil) Thread.sleep(10);
        assertTrue(client.clock().synced());
        long err = Math.abs(client.clock().offsetUs() - AIR_AHEAD_US);
        assertTrue("offset within the loopback round trip, was off by " + err + " us", err < 50_000);
    }

    @Test public void resubscribesPeriodically() throws Exception {
        start(100, 60_000, new CountDownLatch(1));
        byte[] buf = new byte[64];
        int subscribes = 0;
        long deadline = System.currentTimeMillis() + 1500;
        while (subscribes < 3 && System.currentTimeMillis() < deadline) {
            DatagramPacket p = new DatagramPacket(buf, buf.length);
            fakeAir.receive(p);
            if (SidecarProtocol.messageType(p.getData(), p.getLength()) == SidecarProtocol.MSG_SUBSCRIBE) subscribes++;
        }
        assertEquals(3, subscribes);
    }

    @Test public void closeStopsSending() throws Exception {
        start(50, 60_000, new CountDownLatch(1));
        byte[] buf = new byte[64];
        fakeAir.receive(new DatagramPacket(buf, buf.length));
        client.close();
        client = null;
        fakeAir.setSoTimeout(300);
        int after = 0;
        try {
            while (true) {
                fakeAir.receive(new DatagramPacket(buf, buf.length));
                after++;
            }
        } catch (java.net.SocketTimeoutException expected) {
            // quiet: nothing more arrives
        }
        assertTrue("at most one datagram in flight at close, got " + after, after <= 1);
    }
}
