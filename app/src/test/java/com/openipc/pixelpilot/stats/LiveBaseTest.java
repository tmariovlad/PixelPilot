package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;

import org.junit.Test;

/**
 * The app's LiveBase must equal the reference, scripts/quest-latch/owd.py LiveBase, frame by frame on its vectors in
 * scripts/quest-latch/testdata/owd/ (generator owd_vectors.py, pixelpilot-xr-36; spec docs/xr/stats-backend.md §7.2):
 * one algorithm, offline and live.
 */
public class LiveBaseTest {
    private static final double TOL_MS = 1e-6;

    private static File vectors(String name) {
        for (File d = new File(System.getProperty("user.dir")).getAbsoluteFile(); d != null; d = d.getParentFile()) {
            File f = new File(d, "scripts/quest-latch/testdata/owd/" + name);
            if (f.isFile()) return f;
        }
        throw new AssertionError("vector file not found: " + name);
    }

    /** Replays a vector file through a 60 s and an unbounded LiveBase; returns the number of frames compared. */
    private static int replay(String name) throws IOException {
        LiveBase w60 = new LiveBase(60.0), winf = new LiveBase(Double.POSITIVE_INFINITY);
        int n = 0;
        try (BufferedReader r = new BufferedReader(new FileReader(vectors(name)))) {
            for (String line; (line = r.readLine()) != null; ) {
                if (line.startsWith("#") || line.startsWith("t_ns")) continue;
                String[] c = line.split(",");
                long t = Long.parseLong(c[0]);
                double v = Double.parseDouble(c[1]);
                assertEquals("w60 at t=" + t, Double.parseDouble(c[2]), w60.push(t, v), TOL_MS);
                assertEquals("winf at t=" + t, Double.parseDouble(c[3]), winf.push(t, v), TOL_MS);
                n++;
            }
        }
        return n;
    }

    @Test public void matchesTheReferenceOnTheSyntheticVectors() throws IOException {
        // drift 0.06 (not the prior), ripple, +50 ms standing 250-400 s, a +5000 ms jump at 500 s
        assertEquals(6000, replay("synthetic.csv"));
    }

    @Test public void matchesTheReferenceOnRealFramesFromG56() throws IOException {
        // clean m7b25f46, then m6b25f46 over capacity (+55 ms standing queue)
        assertTrue(replay("g56_m6.csv") > 10_000);
    }

    @Test public void theUnboundedBaseKeepsABoundedState() {
        // test_owd.py test_the_unbounded_base_keeps_a_bounded_state: hours of frames since the last reset must not pile
        // up. The unbounded base keeps only the lower convex hull of (t, v), on which min(v − d·t) lies for every d.
        LiveBase base = new LiveBase(Double.POSITIVE_INFINITY, 0.0);   // a wrong prior: keys trend upward until learnt
        for (int i = 0; i < 100_000; i++) {
            base.push((long) (i * 1e7), 5.0 + 0.07 * i / 100 + ((i * 37) % 11) / 10.0);
        }
        assertTrue("stored " + base.stored(), base.stored() < 200);
    }

    @Test public void theilSenIsTheMedianPairwiseSlope() {
        // one lifted point of five: 4 of the 10 pairwise slopes use it, the median stays the line's
        assertEquals(1.0, LiveBase.theilSen(new double[]{0, 1, 2, 3, 4}, new double[]{0, 1, 2, 3, 100}), 1e-12);
        assertEquals(0.0, LiveBase.theilSen(new double[]{5}, new double[]{1}), 0.0);
    }
}
