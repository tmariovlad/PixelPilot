package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.Before;
import org.junit.Test;

/** O123 rules 1 + 4: the stored channel follows the air's beacon {@code ch=}; nothing is sent, nothing retuned. */
public class ChannelFollowTest {
    /** The stored preference; records every write. */
    static final class FakeStore implements ChannelFollow.Store {
        int channel;
        final List<Integer> writes = new ArrayList<>();

        FakeStore(int channel) {
            this.channel = channel;
        }

        @Override
        public int channel() {
            return channel;
        }

        @Override
        public void setChannel(int ch) {
            writes.add(ch);
            channel = ch;
        }
    }

    private static final String EXT = " preset=race phase=ok pending= token= left_s=0 kbps=8000 req_kbps=8000 mcs=3"
            + " fec=8/12 fps= enc=h265 isp=384 cpu=1200 streams=1 txp=18";

    private static VmodeProtocol.Reply beacon(String chPart) {
        return VmodeProtocol.parse("VMODE1 state seq=41" + EXT + chPart
                + " codec=h265 alink=1 payload=2400 what= reason=");
    }

    private FakeStore store;
    private List<String> logs;
    private ChannelFollow follow;

    @Before
    public void setUp() {
        store = new FakeStore(165);
        logs = new ArrayList<>();
        follow = new ChannelFollow(store, logs::add);
    }

    @Test
    public void aBeaconOnAnotherChannelUpdatesTheStoredChannelAndSendsNothing() {
        VmodeSessionTest.FakeSender air = new VmodeSessionTest.FakeSender();
        VmodeSession session = new VmodeSession(air, c -> { });
        VmodeProtocol.Reply r = beacon(" ch=157");

        assertTrue(follow.onReply(r));
        session.onReply(r);   // the same line through the preset session, as XrVideoActivity feeds both

        assertEquals(157, store.channel);
        assertEquals(List.of(157), store.writes);
        assertTrue("no apply / retune request", air.sent.isEmpty());
        assertEquals(1, logs.size());
        assertTrue(logs.get(0), logs.get(0).contains("165") && logs.get(0).contains("157"));
    }

    @Test
    public void theSameChannelWritesNothing() {
        assertFalse(follow.onReply(beacon(" ch=165")));
        assertTrue(store.writes.isEmpty());
        assertTrue(logs.isEmpty());
    }

    @Test
    public void aV1BeaconWithoutChIsNoInformation() {
        assertFalse(follow.onReply(VmodeProtocol.parse(
                "VMODE1 state seq=3 preset=race phase=ok pending= token= left_s=0 kbps=8000 req_kbps=8000")));
        assertTrue(store.writes.isEmpty());
    }

    @Test
    public void anIllegalOrMalformedChannelIsIgnored() {
        for (String ch : new String[] {" ch=52", " ch=144", " ch=169", " ch=0", " ch=-1", " ch=abc", " ch="}) {
            assertFalse(ch, follow.onReply(beacon(ch)));
        }
        assertTrue(store.writes.isEmpty());
    }

    @Test
    public void anAnnouncedSwitchIsNotStoredYet() {
        assertFalse(follow.onReply(beacon(" ch=157 ch_to=149")));
        assertTrue(store.writes.isEmpty());
    }

    @Test
    public void onlyASettledPhaseIsStored() {
        // During a switch the air may still revert (no commit within revert_s): storing its channel then would
        // leave the app on a channel the air leaves again.
        for (String phase : new String[] {"applying", "pending", "reverting"}) {
            VmodeProtocol.Reply r = VmodeProtocol.parse("VMODE1 state seq=9 preset=race phase=" + phase
                    + " ch=157 codec=h265");
            assertFalse(phase, follow.onReply(r));
        }
        assertTrue(store.writes.isEmpty());
        for (String phase : new String[] {"ok", "reverted", "failed"}) {
            store.channel = 165;
            assertTrue(phase, follow.onReply(VmodeProtocol.parse("VMODE1 state seq=9 preset=race phase=" + phase
                    + " ch=157 codec=h265")));
        }
        assertEquals(List.of(157, 157, 157), store.writes);
    }

    @Test
    public void onlyTheStateBeaconCounts() {
        // An ack also carries key=value fields (here even a settled phase); only the beacon states where the air is.
        assertFalse(follow.onReply(VmodeProtocol.parse("VMODE1 ack seq=4 state=accepted token=k1 phase=ok ch=157")));
        assertFalse(follow.onReply(null));
        assertTrue(store.writes.isEmpty());
    }

    @Test
    public void aLaterSettledChannelIsStoredTheSameWay() {
        assertTrue(follow.onReply(beacon(" ch=157")));
        assertFalse(follow.onReply(beacon(" ch=157")));
        assertTrue(follow.onReply(beacon(" ch=149")));   // after a completed switch (rule 2's store step)
        assertEquals(List.of(157, 149), store.writes);
    }
}
