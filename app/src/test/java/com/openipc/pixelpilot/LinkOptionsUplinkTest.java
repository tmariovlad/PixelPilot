package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.junit.Test;

public class LinkOptionsUplinkTest {

    private static LinkOptions.Uplink from(Map<String, Integer> prefs) {
        return LinkOptions.Uplink.from((key, def) -> prefs.getOrDefault(key, def));
    }

    @Test
    public void defaultsAreFourReportsPerSecondWithFecOneOfThreeAtMcs0() {
        LinkOptions.Uplink up = from(new HashMap<>());
        assertEquals(4, up.rateHz);
        assertEquals(1, up.fecK);
        assertEquals(3, up.fecN);
        assertEquals(0, up.mcs);
        assertEquals(12, up.framesPerSecond());
    }

    /** Upstream: 10 reports/s x FEC 1/5 = 50 frames/s. The defaults must cut that by at least 70 %. */
    @Test
    public void defaultsCutTheUplinkAirtimeAgainstUpstream() {
        int upstream = 10 * 5 / 1;
        assertTrue(from(new HashMap<>()).framesPerSecond() * 10 <= upstream * 3);
    }

    @Test
    public void storedValuesWinOverTheDefaults() {
        Map<String, Integer> prefs = new HashMap<>();
        prefs.put(LinkOptions.Uplink.RATE_HZ, 10);
        prefs.put(LinkOptions.Uplink.FEC_K, 1);
        prefs.put(LinkOptions.Uplink.FEC_N, 2);
        prefs.put(LinkOptions.Uplink.MCS, 1);
        LinkOptions.Uplink up = from(prefs);
        assertEquals(10, up.rateHz);
        assertEquals(2, up.fecN);
        assertEquals(1, up.mcs);
        assertEquals(20, up.framesPerSecond());
    }
}
