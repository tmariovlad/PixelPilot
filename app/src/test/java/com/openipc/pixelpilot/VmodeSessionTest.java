package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import com.openipc.xr.PresetCatalog;
import com.openipc.xr.PresetMenu;

import java.util.ArrayList;
import java.util.List;
import java.util.function.IntFunction;

import org.junit.Before;
import org.junit.Test;

public class VmodeSessionTest {
    /** Records what the session sends; replies are fed by the test. */
    static final class FakeSender implements VmodeSender {
        final List<String> sent = new ArrayList<>();
        int seq;

        @Override
        public int request(String verb, IntFunction<String> build) {
            sent.add(build.apply(++seq));
            return seq;
        }

        String last() {
            return sent.get(sent.size() - 1);
        }
    }

    private FakeSender air;
    private VmodeSession s;
    private PresetCatalog shown;

    private static VmodeProtocol.Reply r(String line) {
        return VmodeProtocol.parse(line);
    }

    private static PresetMenu.Action action(String mode, int kbps) {
        PresetMenu m = new PresetMenu();
        m.setCatalog(VmodeProtocol.catalog(r(VmodeProtocolTest.LIST)));
        m.update(XrStick.RIGHT, 0);                       // open
        if (mode != null) m.update(XrStick.RIGHT, 1);     // wide
        if (kbps > 0) m.update(XrStick.UP, 2);            // 4000
        m.update(XrStick.PRESS, 3);
        return m.update(0, 3 + PresetMenu.HOLD_APPLY_MS);
    }

    /** Input bits, spelled out for readability. */
    static final class XrStick {
        static final int RIGHT = com.openipc.xr.XrBridge.INPUT_STICK_RIGHT;
        static final int UP = com.openipc.xr.XrBridge.INPUT_STICK_UP;
        static final int PRESS = com.openipc.xr.XrBridge.INPUT_STICK_PRESS;
    }

    @Before public void setUp() {
        air = new FakeSender();
        s = new VmodeSession(air, c -> shown = c);
        s.ensureList();
        s.onReply(r(VmodeProtocolTest.LIST));
    }

    @Test public void listIsAskedOnceAndShown() {
        s.ensureList();
        assertEquals(1, air.sent.size());
        assertEquals("race", shown.activeMode);
        assertEquals("  Race", s.videoSuffix());
    }

    @Test public void modeSwitchCountsDownThenCommitsAfterVideoAtTheNewSize() {
        s.apply(action("wide", 0));
        assertEquals("VMODE1 apply seq=2 preset=wide revert_s=25", air.last());
        s.onReply(r("VMODE1 ack seq=2 state=accepted token=k7"));
        s.tick(0, 0, 640, 480);
        assertTrue(s.switching());
        assertEquals("SWITCHING TO Wide... 25 s", s.headline());
        s.onReply(r("VMODE1 state preset=race phase=pending pending=wide left_s=24 kbps=2000 req_kbps=2000"));
        s.tick(4000, 40, 848, 480);
        assertEquals("VMODE1 commit seq=3 token=k7", air.last());
        s.onReply(r("VMODE1 ack seq=3 state=committed"));
        assertEquals("Wide ACTIVE", s.headline());
        assertEquals("wide", shown.activeMode);
    }

    @Test public void noCommitWithoutPendingFromTheAir() {
        s.apply(action("wide", 0));
        s.onReply(r("VMODE1 ack seq=2 state=accepted token=k7"));
        s.tick(4000, 100, 848, 480);
        assertEquals(2, air.sent.size());
    }

    @Test public void revertFromTheAirIsShown() {
        s.apply(action("wide", 0));
        s.onReply(r("VMODE1 ack seq=2 state=accepted token=k7"));
        s.onReply(r("VMODE1 state preset=race phase=reverted kbps=2000 req_kbps=2000"));
        assertFalse(s.switching());
        assertEquals("REVERTED TO Race: NO VIDEO", s.headline());
    }

    @Test public void bitrateOnlyChangeNeedsNoCommit() {
        s.apply(action(null, 4000));
        assertEquals("VMODE1 apply seq=2 kbps=4000 revert_s=25", air.last());
        s.onReply(r("VMODE1 ack seq=2 state=committed"));
        assertEquals("4 Mbit/s ACTIVE", s.headline());
        assertEquals(4000, shown.requestedKbps);
        s.onReply(r("VMODE1 state preset=race phase=ok kbps=3000 req_kbps=4000"));
        assertEquals("  Race 3.0 Mbit (capped)", s.videoSuffix());
    }

    @Test public void busyAndNoReplyAreRefusals() {
        s.apply(action("wide", 0));
        s.onReply(r("VMODE1 ack seq=2 state=busy"));
        assertEquals("NOT APPLIED: AIR BUSY", s.headline());
        s.apply(action("wide", 0));
        s.onNoReply("apply");
        assertEquals("NOT APPLIED: NO REPLY FROM AIR", s.headline());
    }

    @Test public void aSwitchDoneElsewhereUpdatesTheActivePreset() {
        s.onReply(r("VMODE1 state preset=wide phase=ok kbps=2000 req_kbps=2000"));
        assertEquals("wide", shown.activeMode);
    }
}
