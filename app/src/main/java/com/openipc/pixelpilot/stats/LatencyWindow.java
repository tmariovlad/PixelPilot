package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.Segment;
import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Pairs the air's sidecar frames with the Quest's frames by (ssrc, RTP timestamp) and turns the last {@code windowUs}
 * into per-segment latency (StatsSnapshot):
 *   encode    = frame_ready − capture              (air clock only)
 *   airSend   = last_pkt_send − frame_ready        (air clock only)
 *   link      = complete on the Quest − last_pkt_send, the air time mapped onto the Quest's clock (ClockSync)
 *   decode    = decoded − complete                  (Quest clock only)
 *   toDisplay = decoded → next predicted display    (estimate, DisplayEstimate)
 *   total     = the per-frame sum, only for frames where all five are known.
 * encode/airSend use every air frame in the window (no match needed); the rest need a matched pair. Either side may
 * arrive first. All times are CLOCK_MONOTONIC (SidecarProtocol). Thread-safe.
 */
public final class LatencyWindow {
    private static final int MAX_PENDING = 2048;

    private static final class Air {
        final SidecarProtocol.Frame f;
        final long recvUs;

        Air(SidecarProtocol.Frame f, long recvUs) {
            this.f = f;
            this.recvUs = recvUs;
        }
    }

    private static final class Pair {
        final SidecarProtocol.Frame air;
        final QuestFrame quest;

        Pair(SidecarProtocol.Frame air, QuestFrame quest) {
            this.air = air;
            this.quest = quest;
        }
    }

    private final long windowUs;
    private final ArrayDeque<Air> airRecent = new ArrayDeque<>();
    private final Map<Long, Air> airPending = new HashMap<>();
    private final Map<Long, QuestFrame> questPending = new HashMap<>();
    private final ArrayDeque<Pair> matched = new ArrayDeque<>();

    public LatencyWindow(long windowUs) {
        this.windowUs = windowUs;
    }

    private static long key(long ssrc, long rtpTs) {
        return (ssrc << 32) | (rtpTs & 0xFFFFFFFFL);
    }

    public synchronized void addAir(SidecarProtocol.Frame f, long questRecvUs) {
        Air a = new Air(f, questRecvUs);
        airRecent.addLast(a);
        QuestFrame q = questPending.remove(key(f.ssrc, f.rtpTs));
        if (q != null) matched.addLast(new Pair(f, q));
        else if (airPending.size() < MAX_PENDING) airPending.put(key(f.ssrc, f.rtpTs), a);
    }

    public synchronized void addQuest(QuestFrame q) {
        Air a = airPending.remove(key(q.ssrc, q.rtpTs));
        if (a != null) matched.addLast(new Pair(a.f, q));
        else if (questPending.size() < MAX_PENDING) questPending.put(key(q.ssrc, q.rtpTs), q);
    }

    private void prune(long nowUs) {
        long from = nowUs - windowUs;
        while (!airRecent.isEmpty() && airRecent.peekFirst().recvUs < from) airRecent.removeFirst();
        while (!matched.isEmpty() && matched.peekFirst().quest.decodedNs / 1000 < from) matched.removeFirst();
        airPending.values().removeIf(a -> a.recvUs < from);
        questPending.values().removeIf(q -> q.decodedNs / 1000 < from);
    }

    private static double ms(long us) {
        return us / 1000.0;
    }

    /** Fills the latency and air-side fields of {@code b} from the window ending at {@code nowUs}. */
    public synchronized StatsSnapshot.Builder fill(StatsSnapshot.Builder b, long nowUs, ClockSync clock,
                                                   DisplayEstimate display) {
        prune(nowUs);
        int nAir = airRecent.size();
        double[] encode = new double[nAir], airSend = new double[nAir];
        List<Double> kbit = new ArrayList<>(), pkts = new ArrayList<>();
        int idrs = 0;
        long newestRecv = Long.MIN_VALUE;
        int i = 0;
        for (Air a : airRecent) {
            SidecarProtocol.Frame f = a.f;
            encode[i] = f.captureUs > 0 ? ms(f.frameReadyUs - f.captureUs) : Double.NaN;
            airSend[i] = ms(f.lastPktSendUs - f.frameReadyUs);
            pkts.add((double) f.seqCount);
            if (f.hasEncInfo) {
                kbit.add(f.frameSizeBytes * 8 / 1000.0);
                if (f.frameType == SidecarProtocol.FRAME_TYPE_IDR) idrs++;
            }
            newestRecv = Math.max(newestRecv, a.recvUs);
            i++;
        }
        boolean synced = clock != null && clock.synced();
        int nPair = matched.size();
        double[] link = new double[nPair], decode = new double[nPair], toDisplay = new double[nPair],
                total = new double[nPair];
        i = 0;
        for (Iterator<Pair> it = matched.iterator(); it.hasNext(); i++) {
            Pair p = it.next();
            SidecarProtocol.Frame f = p.air;
            QuestFrame q = p.quest;
            double enc = f.captureUs > 0 ? ms(f.frameReadyUs - f.captureUs) : Double.NaN;
            double send = ms(f.lastPktSendUs - f.frameReadyUs);
            link[i] = synced ? ms(q.completeNs / 1000 - clock.airToQuestUs(f.lastPktSendUs)) : Double.NaN;
            decode[i] = (q.decodedNs - q.completeNs) / 1e6;
            long toDisp = display == null ? -1 : display.nsToDisplay(q.decodedNs);
            toDisplay[i] = toDisp < 0 ? Double.NaN : toDisp / 1e6;
            total[i] = enc + send + link[i] + decode[i] + toDisplay[i];   // NaN if any part is unknown
        }
        double windowS = windowUs / 1e6;
        return b.encode(Segment.of(encode))
                .airSend(Segment.of(airSend))
                .link(Segment.of(link))
                .decode(Segment.of(decode))
                .toDisplay(Segment.of(toDisplay))
                .total(Segment.of(total))
                .matching(nPair, synced, synced ? clock.rttUs() / 1000.0 : Double.NaN,
                        newestRecv == Long.MIN_VALUE ? Double.NaN : ms(nowUs - newestRecv))
                .air(median(kbit), median(pkts), kbit.isEmpty() ? Double.NaN : idrs / windowS, StatsSnapshot.NA);
    }

    private static double median(List<Double> v) {
        double[] a = new double[v.size()];
        for (int k = 0; k < a.length; k++) a[k] = v.get(k);
        return Segment.of(a).p50Ms;
    }
}
