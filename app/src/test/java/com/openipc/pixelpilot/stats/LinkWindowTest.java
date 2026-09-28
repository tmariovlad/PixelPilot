package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import com.openipc.xr.stats.StatsSnapshot;

import org.junit.Test;

public class LinkWindowTest {
    @Test public void htRateCodesDecodeToMcsAndStreams() {
        RxRate r = RxRate.decode(0x0E, 0, 1, 1, 0);          // HT MCS2, 1 stream
        assertEquals(2, r.mcs);
        assertEquals(1, r.nss);
        assertEquals(20, r.bwMhz);
        assertTrue(r.stbc);
        RxRate two = RxRate.decode(0x0C + 9, 1, 0, 0, 1);    // HT MCS9 = MCS1 on 2 streams, 40 MHz, short GI
        assertEquals(1, two.mcs);
        assertEquals(2, two.nss);
        assertEquals(40, two.bwMhz);
        assertTrue(two.sgi);
    }

    @Test public void vhtAndNineBitCodesDecodeToo() {
        RxRate vht = RxRate.decode(0x2C + 13, 2, 0, 1, 0);   // VHT 2SS MCS3, 80 MHz
        assertEquals(3, vht.mcs);
        assertEquals(2, vht.nss);
        assertEquals(80, vht.bwMhz);
        RxRate ht9 = RxRate.decode(0x80 + 2, 0, 0, 0, 0);    // halmac 9-bit HT MCS2
        assertEquals(2, ht9.mcs);
        assertEquals(1, ht9.nss);
        RxRate vht9 = RxRate.decode(0x100 + 11, 0, 0, 0, 0); // halmac 9-bit VHT 2SS MCS1
        assertEquals(1, vht9.mcs);
        assertEquals(2, vht9.nss);
    }

    @Test public void legacyRatesHaveNoMcs() {
        RxRate ofdm = RxRate.decode(0x0B, 0, 0, 0, 0);       // 54 Mbit/s OFDM
        assertEquals(StatsSnapshot.NA, ofdm.mcs);
        assertEquals(1, ofdm.nss);
    }

    @Test public void lossRatesOverTheWindowLikeLinkAudit() {
        LinkWindow w = new LinkWindow(2_000_000);
        // two 1 s windows: 1000 delivered each, 60 and 40 recovered by FEC, 10 and 0 lost after FEC
        w.addStats(1_000_000, 1000, 60, 10, 3, 188, 190, 38, 36);
        w.addStats(2_000_000, 1000, 40, 0, 0, 186, 188, 40, 38);
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 2_000_000).build();
        assertEquals(100.0 * (100 + 10) / 2010, s.pDataPct, 1e-9);   // (fec_rec + lost) / (delivered + lost)
        assertEquals(100.0 * 10 / 2010, s.postFecPct, 1e-9);
        assertEquals(50.0, s.fecRecPerS, 1e-9);
        assertEquals(5.0, s.holesPerS, 1e-9);
        assertEquals(3, s.decErr);
    }

    @Test public void rssiAndSnrInDbmAndDbFromTheNewestWindow() {
        LinkWindow w = new LinkWindow(2_000_000);
        w.addStats(1_000_000, 1000, 0, 0, 0, 74, 70, 50, 41);        // raw: dBm = raw - 110, dB = raw / 2
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_000_000).build();
        assertEquals(-36, s.rssiADbm);
        assertEquals(-40, s.rssiBDbm);
        assertEquals(25, s.snrADb);
        assertEquals(20, s.snrBDb);   // 41 / 2 = 20.5, rounded half down to 20 for a stable display
    }

    @Test public void rxRateShareFromTheNewestWindow() {
        LinkWindow w = new LinkWindow(2_000_000);
        w.addRxRate(new int[]{0x0E, 0, 1, 1, 0, 195, 200});
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_000_000).build();
        assertEquals(2, s.mcs);
        assertEquals(1, s.nss);
        assertEquals(1, s.stbc);
        assertEquals(97.5, s.rateSharePct, 1e-9);
    }

    @Test public void noTrafficMeansUnknownNotZero() {
        LinkWindow w = new LinkWindow(2_000_000);
        w.addRxRate(new int[]{0, 0, 0, 0, 0, 0, 0});
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 1_000_000).build();
        assertTrue(Double.isNaN(s.pDataPct));
        assertEquals(StatsSnapshot.NA, s.mcs);
        assertEquals(StatsSnapshot.NA, s.rssiADbm);
    }

    @Test public void oldWindowsDropOut() {
        LinkWindow w = new LinkWindow(2_000_000);
        w.addStats(1_000_000, 1000, 60, 10, 0, 74, 70, 50, 40);
        StatsSnapshot s = w.fill(new StatsSnapshot.Builder(), 9_000_000).build();
        assertTrue(Double.isNaN(s.postFecPct));
    }
}
