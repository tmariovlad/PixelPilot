package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import com.openipc.xr.PresetCatalog;

import org.junit.Test;

public class VmodeProtocolTest {
    static final String LIST = "VMODE1 list seq=1 active=race default=race kbps=2000 "
            + "presets=race|Race|640x480@167|33x44|26.7-32.0,wide|Wide|1920x1080@90>848x480|99x98|35.3-41.6 "
            + "qualities=2000|0,4000|1.7,6000|3.1";

    @Test public void requestsCarryOnlyTheAxesThatChange() {
        assertEquals("VMODE1 apply seq=3 preset=wide revert_s=25", VmodeProtocol.apply(3, "wide", 0, 25));
        assertEquals("VMODE1 apply seq=4 kbps=4000 revert_s=25", VmodeProtocol.apply(4, null, 4000, 25));
        assertEquals("VMODE1 commit seq=5 token=ab12", VmodeProtocol.commit(5, "ab12"));
        assertEquals("VMODE1 list seq=1", VmodeProtocol.list(1));
        assertEquals("VMODE1 save_default seq=9", VmodeProtocol.saveDefault(9));
    }

    @Test public void parsesTheCatalog() {
        PresetCatalog c = VmodeProtocol.catalog(VmodeProtocol.parse(LIST));
        assertEquals(2, c.modes.size());
        assertEquals("Wide", c.modes.get(1).label);
        assertEquals("1920x1080@90>848x480", c.modes.get(1).desc);
        assertEquals("35.3-41.6", c.modes.get(1).g2g);
        assertEquals(3, c.qualities.size());
        assertEquals(4000, c.qualities.get(1).kbps);
        assertEquals("1.7", c.qualities.get(1).costMs);
        assertEquals("race", c.activeMode);
        assertEquals(2000, c.requestedKbps);
    }

    @Test public void malformedEntriesAreSkipped() {
        PresetCatalog c = VmodeProtocol.catalog(VmodeProtocol.parse(
                "VMODE1 list seq=1 presets=race|Race|640x480@167,wide|Wide|1x1@1|1x1|- qualities=x|1,2000|0"));
        assertEquals(1, c.modes.size());
        assertEquals(1, c.qualities.size());
    }

    @Test public void beaconHasNoSeqAndForeignLinesAreIgnored() {
        VmodeProtocol.Reply r = VmodeProtocol.parse("VMODE1 state preset=race phase=ok kbps=1800 req_kbps=2000");
        assertEquals(-1, r.seq());
        assertEquals("state", r.verb);
        assertEquals(1800, r.intField("kbps", 0));
        assertNull(VmodeProtocol.parse("PPXR1 something"));
        assertNull(VmodeProtocol.parse(""));
    }
}
