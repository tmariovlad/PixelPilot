package com.openipc.pixelpilot.stats;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * The live reference signal of docs/xr/stats-backend.md §7.2: a port, method for method, of
 * scripts/quest-latch/owd.py LiveBase (pixelpilot-xr-36), and it must match that on the vectors in
 * scripts/quest-latch/testdata/owd/ (LiveBaseTest). Causal, one frame at a time:
 * rel = (v − d·t) − min over the trailing window of (v − d·t), with d the air/Quest clock drift in ms per s.
 * d = Theil-Sen slope of the per-block minima of v over the last horizon, once minBlocks blocks are complete, else
 * the prior; it changes only when a block completes, and then the window's minimum is rebuilt. After that bootstrap a
 * block joins the fit only if its minimum lies within acceptMs of the current line (median intercept): a standing
 * queue lifts minima above the line and must not be learnt as drift. A step of more than jumpMs between consecutive
 * frames (the RTP base moved: a waybeam restart) clears everything, drift back to the prior.
 * t in ns, v and rel in ms. Not thread-safe.
 */
final class LiveBase {
    static final double BLOCK_S = 10.0, HORIZON_S = 300.0, PRIOR = 0.07, JUMP_MS = 1000.0, ACCEPT_MS = 2.0;
    static final int MIN_BLOCKS = 6;

    private final double winNs, blkNs;
    private double d;
    private final TreeMap<Long, Double> blocks = new TreeMap<>();   // block index -> minimum v in it
    private final ArrayDeque<double[]> raw = new ArrayDeque<>();     // {t, v} in the window, for a rebuild
    private final ArrayDeque<double[]> dq = new ArrayDeque<>();      // {t, v − d·t_s}, increasing keys
    private Long curBlock;
    private Double curMin, prevV;

    /** windowS: the trailing window of the minimum, in s (Double.POSITIVE_INFINITY = since the last reset). */
    LiveBase(double windowS) {
        this.winNs = windowS * 1e9;
        this.blkNs = BLOCK_S * 1e9;
        reset();
    }

    double drift() {
        return d;
    }

    void reset() {
        d = PRIOR;
        blocks.clear();
        raw.clear();
        dq.clear();
        curBlock = null;
        curMin = null;
        prevV = null;
    }

    private double key(double t, double v) {
        return v - d * t / 1e9;
    }

    private double appendKey(double t, double v) {
        double k = key(t, v);
        while (!dq.isEmpty() && dq.peekLast()[1] >= k) dq.pollLast();
        dq.addLast(new double[]{t, k});
        return k;
    }

    /** Whether block minimum y at x (s) lies within ACCEPT_MS above the current fit (always, during bootstrap). */
    private boolean onLine(double x, double y) {
        if (blocks.size() < MIN_BLOCKS) return true;
        double[] a = new double[blocks.size()];
        int i = 0;
        for (Map.Entry<Long, Double> e : blocks.entrySet()) a[i++] = e.getValue() - d * e.getKey() * BLOCK_S;
        Arrays.sort(a);
        return y - (a[a.length / 2] + d * x) <= ACCEPT_MS;
    }

    private void completeBlock(long b) {
        if (onLine(curBlock * BLOCK_S, curMin)) blocks.put(curBlock, curMin);
        for (Iterator<Long> it = blocks.keySet().iterator(); it.hasNext(); ) {
            if ((b - it.next()) * BLOCK_S > HORIZON_S) it.remove();
        }
        if (blocks.size() < MIN_BLOCKS) return;
        double[] xs = new double[blocks.size()], ys = new double[blocks.size()];
        int i = 0;
        for (Map.Entry<Long, Double> e : blocks.entrySet()) {
            xs[i] = e.getKey() * BLOCK_S;
            ys[i++] = e.getValue();
        }
        double nd = theilSen(xs, ys);
        if (nd != d) {
            d = nd;
            dq.clear();
            for (double[] r : raw) appendKey(r[0], r[1]);
        }
    }

    double push(long tNs, double v) {
        if (prevV != null && Math.abs(v - prevV) > JUMP_MS) reset();
        prevV = v;
        double t = tNs;
        long b = (long) Math.floor(t / blkNs);
        if (curBlock != null && b != curBlock) {
            completeBlock(b);
            curMin = null;
        }
        curBlock = b;
        curMin = curMin == null ? v : Math.min(curMin, v);
        raw.addLast(new double[]{t, v});
        while (raw.peekFirst()[0] <= t - winNs) raw.pollFirst();
        double k = appendKey(t, v);
        while (dq.peekFirst()[0] <= t - winNs) dq.pollFirst();
        return k - dq.peekFirst()[1];
    }

    /** Median of the pairwise slopes (owd.theil_sen): robust to a minority (< ~29 %) of lifted points. */
    static double theilSen(double[] xs, double[] ys) {
        List<Double> s = new ArrayList<>();
        for (int i = 0; i < xs.length; i++)
            for (int j = i + 1; j < xs.length; j++)
                if (xs[j] != xs[i]) s.add((ys[j] - ys[i]) / (xs[j] - xs[i]));
        if (s.isEmpty()) return 0.0;
        s.sort(null);
        int m = s.size() / 2;
        return s.size() % 2 == 1 ? s.get(m) : (s.get(m - 1) + s.get(m)) / 2;
    }
}
