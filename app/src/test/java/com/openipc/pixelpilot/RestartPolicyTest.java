package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class RestartPolicyTest {
    @Test public void aLiveLinkIsNeverRestarted() {
        RestartPolicy p = new RestartPolicy();
        for (long t = 0; t < 60_000; t += 250) assertFalse(p.onTick(t, true));
    }

    @Test public void firstRestartIsImmediateThenBacksOff() {
        RestartPolicy p = new RestartPolicy();
        assertTrue(p.onTick(0, false));
        assertFalse(p.onTick(999, false));
        assertTrue(p.onTick(1_000, false));           // +1 s
        assertFalse(p.onTick(2_999, false));
        assertTrue(p.onTick(3_000, false));           // +2 s
        assertFalse(p.onTick(6_999, false));
        assertTrue(p.onTick(7_000, false));           // +4 s
        assertTrue(p.onTick(15_000, false));          // +8 s
        assertFalse(p.onTick(22_999, false));
        assertTrue(p.onTick(23_000, false));          // stays at 8 s
        assertEquals(6, p.attempts());
    }

    @Test public void backoffResetsAfterTenHealthySeconds() {
        RestartPolicy p = new RestartPolicy();
        assertTrue(p.onTick(0, false));
        assertTrue(p.onTick(1_000, false));
        p.onTick(1_250, true);
        p.onTick(11_250, true);                        // up for 10 s
        assertEquals(0, p.attempts());
        assertTrue(p.onTick(11_500, false));          // immediate again
    }

    @Test public void aShortRecoveryDoesNotResetTheBackoff() {
        RestartPolicy p = new RestartPolicy();
        assertTrue(p.onTick(0, false));
        assertTrue(p.onTick(1_000, false));
        p.onTick(1_250, true);                         // up for 2 s only
        p.onTick(3_250, true);
        assertTrue(p.onTick(3_500, false));           // third restart: the backoff continues...
        assertFalse(p.onTick(7_499, false));          // ...with the 4 s step, not back at 1 s
        assertTrue(p.onTick(7_500, false));
    }
}
