package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.StatsSnapshot;

/**
 * A Realtek RX descriptor rate (devourer rx_pkt_attrib::data_rate) decoded into MCS / spatial streams. 7-bit codes
 * (RTL8812AU): 0x00–0x0B legacy CCK/OFDM, 0x0C + n HT MCS n, 0x2C + n VHT (devourer ieee80211_radiotap.h:188-236:
 * DESC_RATE1M 0x00, DESC_RATEMCS0 0x0C, DESC_RATEVHTSS1MCS0 0x2C). 9-bit halmac codes: HT 0x80+, VHT 0x100+,
 * HE 0x180+ (devourer RxPacket.h, data_rate). mcs is per stream (HT MCS9 = MCS1 on 2 streams); NA for legacy and HE.
 */
public final class RxRate {
    public final int mcs, nss, bwMhz;
    public final boolean stbc, ldpc, sgi;

    private RxRate(int mcs, int nss, int bwMhz, boolean stbc, boolean ldpc, boolean sgi) {
        this.mcs = mcs;
        this.nss = nss;
        this.bwMhz = bwMhz;
        this.stbc = stbc;
        this.ldpc = ldpc;
        this.sgi = sgi;
    }

    /** {@code bw} as devourer reports it: 0 = 20 MHz, 1 = 40, 2 = 80. */
    public static RxRate decode(int code, int bw, int stbc, int ldpc, int sgi) {
        int mcs = StatsSnapshot.NA, nss = 1;
        if (code >= 0x180) {
            nss = StatsSnapshot.NA;                   // HE: not decoded here
        } else if (code >= 0x100) {
            mcs = (code - 0x100) % 10;
            nss = (code - 0x100) / 10 + 1;
        } else if (code >= 0x80) {
            mcs = (code - 0x80) % 8;
            nss = (code - 0x80) / 8 + 1;
        } else if (code >= 0x2C) {
            mcs = (code - 0x2C) % 10;
            nss = (code - 0x2C) / 10 + 1;
        } else if (code >= 0x0C) {
            mcs = (code - 0x0C) % 8;
            nss = (code - 0x0C) / 8 + 1;
        }
        return new RxRate(mcs, nss, 20 << Math.max(0, Math.min(bw, 3)), stbc != 0, ldpc != 0, sgi != 0);
    }
}
