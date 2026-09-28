package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayDeque;

/**
 * The link fields of the Stats page over the last {@code windowUs}, from the wfb video stats windows
 * (WfbNGStats, one per native stats callback) and the RX rate (WfbNgLink.takeRxRate()).
 *
 * Loss follows scripts/quest-latch/link_audit.py p_data(): pre-FEC data loss = (fec_recovered + lost) / (delivered +
 * lost), post-FEC = lost / (delivered + lost), where wfb's delivered (outgoing) and lost packets stand in for the RTP
 * packets received and missing. holes/s = packets lost after FEC per second.
 * RSSI and SNR come from devourer's raw PHY-status values, converted as devourer does (src/LinkHealth.cpp:8-9):
 * dBm = raw − 110, dB = raw / 2 (half-dB steps). They and the rate are the newest window's, not averages; decErr is
 * the decrypt errors summed over the window.
 * Thread-safe.
 */
public final class LinkWindow {
    private static final class Sample {
        final long atUs;
        final long delivered;
        final long fecRec;
        final long lost;
        final int decErr;

        Sample(long atUs, long delivered, long fecRec, long lost, int decErr) {
            this.atUs = atUs;
            this.delivered = delivered;
            this.fecRec = fecRec;
            this.lost = lost;
            this.decErr = decErr;
        }
    }

    private final long windowUs;
    private final ArrayDeque<Sample> samples = new ArrayDeque<>();
    private int rssiA = StatsSnapshot.NA, rssiB = StatsSnapshot.NA, snrA = StatsSnapshot.NA, snrB = StatsSnapshot.NA;
    private RxRate rate;
    private double rateShare = Double.NaN;

    public LinkWindow(long windowUs) {
        this.windowUs = windowUs;
    }

    /** One wfb video stats window (WfbNGStats: count_p_outgoing, count_p_fec_recovered, count_p_lost, ...). */
    public synchronized void addStats(long nowUs, long delivered, long fecRecovered, long lost, int decErr,
                                      int rssiARaw, int rssiBRaw, int snrARaw, int snrBRaw) {
        samples.addLast(new Sample(nowUs, delivered, fecRecovered, lost, decErr));
        if (delivered + lost > 0) {
            rssiA = rssiARaw - 110;
            rssiB = rssiBRaw - 110;
            snrA = (int) Math.floor(snrARaw / 2.0);
            snrB = (int) Math.floor(snrBRaw / 2.0);
        }
    }

    /** WfbNgLink.takeRxRate(): {rate code, bw, stbc, ldpc, sgi, packets at that rate, packets in the window}. */
    public synchronized void addRxRate(int[] r) {
        if (r == null || r.length < 7 || r[6] <= 0) return;
        rate = RxRate.decode(r[0], r[1], r[2], r[3], r[4]);
        rateShare = 100.0 * r[5] / r[6];
    }

    public synchronized StatsSnapshot.Builder fill(StatsSnapshot.Builder b, long nowUs) {
        while (!samples.isEmpty() && samples.peekFirst().atUs < nowUs - windowUs) samples.removeFirst();
        long delivered = 0;
        long fec = 0;
        long lost = 0;
        int decErr = 0;
        for (Sample s : samples) {
            delivered += s.delivered;
            fec += s.fecRec;
            lost += s.lost;
            decErr += s.decErr;
        }
        long expected = delivered + lost;
        double windowS = windowUs / 1e6;
        if (expected > 0) {
            b.loss(100.0 * (fec + lost) / expected, 100.0 * lost / expected, fec / windowS, lost / windowS);
            b.rssi(rssiA, rssiB).snr(snrA, snrB);
        }
        if (rate != null) b.rate(rate.mcs, rate.nss, rate.bwMhz, rate.sgi, rate.stbc, rate.ldpc, rateShare);
        return b.decErr(samples.isEmpty() ? StatsSnapshot.NA : decErr);   // decrypt errors in the window
    }
}
