package com.openipc.wfbngrtl8812;

import static org.junit.Assert.assertEquals;

import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.Test;

public class WfbStatsTraceTest {
    @Test
    public void emitsOneCounterPerStatWithTheIntervalValues() {
        Map<String, Long> got = new LinkedHashMap<>();
        // all, dec_err, dec_ok, fec_recovered, lost, bad, override, outgoing, avg_rssi,
        // rssi_a, rssi_b, snr_a, snr_b (distinct per chain, so a swapped chain fails)
        WfbNGStats s = new WfbNGStats(412, 3, 409, 17, 2, 0, 0, 0, 71, 57, 44, 38, 21);

        WfbStatsTrace.emit(s, got::put);

        Map<String, Long> want = new LinkedHashMap<>();
        want.put("ppxr_wfb_p_all", 412L);
        want.put("ppxr_wfb_dec_err", 3L);
        want.put("ppxr_wfb_fec_rec", 17L);
        want.put("ppxr_wfb_lost", 2L);
        want.put("ppxr_wfb_rssi", 71L);
        want.put("ppxr_wfb_rssi_a", 57L);
        want.put("ppxr_wfb_rssi_b", 44L);
        want.put("ppxr_wfb_snr_a", 38L);
        want.put("ppxr_wfb_snr_b", 21L);
        assertEquals(want, got);
    }
}
