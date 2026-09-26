package com.openipc.xr;

import static org.junit.Assert.*;
import org.junit.Test;

public class PhaseReportTest {
    @Test public void datagramCarriesWaitConcentrationAndPeriod() {
        long[] t = {1_000_000_000L - 1_500_000};
        PhaseMeter.Result r = PhaseMeter.measure(t, 1, 1_000_000_000L, 8_333_333L);
        assertEquals("PPXR1 seq=7 frames=1 wait_us=1500 conc=1.000 period_us=8333\n",
                PhaseReport.datagram(7, r, 8_333_333L));
    }

    @Test public void targetParsesHostAndPort() {
        PhaseReport.Target t = PhaseReport.Target.parse("192.168.100.10:5610");
        assertEquals("192.168.100.10", t.host);
        assertEquals(5610, t.port);
    }

    @Test public void emptyOrMalformedTargetIsOff() {
        assertNull(PhaseReport.Target.parse(""));
        assertNull(PhaseReport.Target.parse(null));
        assertNull(PhaseReport.Target.parse("hostonly"));
        assertNull(PhaseReport.Target.parse("host:notaport"));
        assertNull(PhaseReport.Target.parse("host:70000"));
    }
}
