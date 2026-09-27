package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

/** VmodeClient against a fake air receiver on localhost UDP. */
public class VmodeClientTest {
    private static final Pattern SEQ = Pattern.compile("seq=(\\d+)");
    private DatagramSocket fakeAir;
    private final List<String> received = new CopyOnWriteArrayList<>();
    private final List<VmodeProtocol.Reply> replies = new CopyOnWriteArrayList<>();
    private final List<String> noReply = new CopyOnWriteArrayList<>();
    private VmodeClient client;

    @Before public void setUp() throws Exception {
        fakeAir = new DatagramSocket(0, InetAddress.getLoopbackAddress());
    }

    @After public void tearDown() {
        if (client != null) client.close();
        fakeAir.close();
    }

    private void startClient(int tries) throws Exception {
        client = new VmodeClient(new InetSocketAddress(InetAddress.getLoopbackAddress(), fakeAir.getLocalPort()),
                new VmodeClient.Listener() {
                    @Override public void onReply(VmodeProtocol.Reply r) {
                        replies.add(r);
                    }

                    @Override public void onNoReply(String verb) {
                        noReply.add(verb);
                    }
                }, 50, tries);
        client.start();
    }

    /** Answers from the fake air: drops the first {@code drop} requests, then replies twice to each (a duplicate). */
    private Thread serve(int drop, int answers) {
        Thread t = new Thread(() -> {
            try {
                byte[] buf = new byte[512];
                for (int i = 0; i < drop + answers; i++) {
                    DatagramPacket p = new DatagramPacket(buf, buf.length);
                    fakeAir.receive(p);
                    String line = new String(p.getData(), 0, p.getLength(), StandardCharsets.US_ASCII);
                    received.add(line);
                    if (i < drop) continue;
                    Matcher m = SEQ.matcher(line);
                    String seq = m.find() ? m.group(1) : "-1";
                    byte[] out = ("VMODE1 ack seq=" + seq + " state=committed").getBytes(StandardCharsets.US_ASCII);
                    for (int k = 0; k < 2; k++) fakeAir.send(new DatagramPacket(out, out.length, p.getSocketAddress()));
                    byte[] beacon = "VMODE1 state preset=race phase=ok".getBytes(StandardCharsets.US_ASCII);
                    fakeAir.send(new DatagramPacket(beacon, beacon.length, p.getSocketAddress()));
                }
            } catch (Exception ignored) {
                // socket closed at tearDown
            }
        });
        t.start();
        return t;
    }

    @Test public void retriesUntilAReplyAndDeliversItOnce() throws Exception {
        startClient(5);
        Thread t = serve(2, 1);
        client.request("apply", seq -> VmodeProtocol.apply(seq, null, 4000, 25));
        t.join(2000);
        Thread.sleep(300);                                   // leave time for the duplicate and any extra retry
        assertEquals(3, received.size());                    // 2 lost + the one answered, then no more resends
        assertEquals(1, replies.stream().filter(r -> "ack".equals(r.verb)).count());
        assertEquals(1, replies.stream().filter(r -> "state".equals(r.verb)).count());
        assertTrue(noReply.isEmpty());
    }

    @Test public void targetIsTheAirUnlessAnIpv4OverrideIsSet() {
        assertEquals(new InetSocketAddress("10.5.0.10", 9998), VmodeClient.target(""));
        assertEquals(new InetSocketAddress("10.5.0.10", 9998), VmodeClient.target("pc.local:9998"));   // no DNS
        assertEquals(new InetSocketAddress("192.168.100.213", 9998), VmodeClient.target("192.168.100.213:9998"));
    }

    @Test public void givesUpAfterTheLastTry() throws Exception {
        startClient(3);
        Thread t = serve(3, 0);
        client.request("list", VmodeProtocol::list);
        t.join(2000);
        for (int i = 0; i < 20 && noReply.isEmpty(); i++) Thread.sleep(50);
        assertEquals(3, received.size());
        assertEquals(List.of("list"), noReply);
        assertTrue(replies.isEmpty());
    }
}
