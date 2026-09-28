package com.openipc.wfbngrtl8812;

import androidx.annotation.Keep;

@Keep
public class WfbNGStats {
    public final int count_p_all;
    public final int count_p_dec_err;
    public final int count_p_dec_ok;
    public final int count_p_fec_recovered;
    public final int count_p_lost;
    public final int count_p_bad;
    public final int count_p_override;
    public final int count_p_outgoing;
    public final int avg_rssi;
    // Last-second average per receive chain (path A / path B), in the adapter's raw PHY-status units:
    // RSSI = gain_trsw byte (1 unit = 1 dB), SNR = rxsnr (1 unit = 0.5 dB).
    public final int rssi_a;
    public final int rssi_b;
    public final int snr_a;
    public final int snr_b;

    public WfbNGStats(int cntPall, int cntDecErr, int cntDecOk, int cntFecRec,
                      int cntLost, int cntBad, int cntOverride, int cntOutgoing, int avgRssi,
                      int rssiA, int rssiB, int snrA, int snrB) {
        count_p_all = cntPall;
        count_p_dec_err = cntDecErr;
        count_p_dec_ok = cntDecOk;
        count_p_fec_recovered = cntFecRec;
        count_p_lost = cntLost;
        count_p_bad = cntBad;
        count_p_override = cntOverride;
        count_p_outgoing = cntOutgoing;
        avg_rssi = avgRssi;
        rssi_a = rssiA;
        rssi_b = rssiB;
        snr_a = snrA;
        snr_b = snrB;
    }
}
