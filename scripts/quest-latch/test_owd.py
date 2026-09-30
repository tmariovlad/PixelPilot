"""Tests for owd (relative one-way delay per frame: floor per window, payload effect, loss-locked profile).
Run: python3 test_owd.py"""
import unittest

import owd
from ab_segments import Frame

MS = 1_000_000


class RunningMin(unittest.TestCase):
    def test_value_minus_the_trailing_minimum(self):
        t = [0, 1 * MS, 2 * MS, 3 * MS, 4 * MS]
        v = [5.0, 3.0, 4.0, 9.0, 6.0]
        self.assertEqual(owd.relative(t, v, 2 * MS), [0.0, 0.0, 1.0, 5.0, 0.0])   # min over (t - 2 ms, t]: at 3 ms the 3.0 at 1 ms has left

    def test_an_old_minimum_leaves_the_window(self):
        t = [0, 10 * MS, 20 * MS]
        v = [1.0, 5.0, 6.0]
        self.assertEqual(owd.relative(t, v, 15 * MS), [0.0, 4.0, 1.0])   # at 20 ms the 1.0 at 0 ms has left


class Windows(unittest.TestCase):
    def test_p50_p90_per_window_and_their_spread(self):
        t = [i * MS for i in range(1000)]                   # 1 s of frames, one per ms
        v = [float(i % 10) for i in range(1000)]            # 0..9 in every window
        w = owd.windows(t, v, 250 * MS, min_n=10)
        self.assertEqual(len(w), 4)
        self.assertEqual((w[0]["p50"], w[0]["p90"]), (5.0, 9.0))   # ab_segments.pct: v[int(p * n)]
        s = owd.window_summary(w)
        self.assertEqual(s["windows"], 4)
        self.assertEqual(s["p90_median"], 9.0)

    def test_sparse_windows_are_skipped(self):
        self.assertEqual(owd.windows([0, 1, 2], [1.0, 2.0, 3.0], 250 * MS, min_n=10), [])


class LossBursts(unittest.TestCase):
    def test_onset_is_the_packet_after_the_gap_and_close_holes_merge(self):
        pkts = [(0, 1, 0), (1 * MS, 2, 0), (2 * MS, 5, 0), (3 * MS, 6, 0), (30 * MS, 8, 0), (500 * MS, 12, 0)]
        b = owd.loss_bursts(pkts, merge_ns=100 * MS)
        self.assertEqual(b, [(2 * MS, 3), (500 * MS, 3)])   # (onset, packets lost): 3,4 + 7 merged; 9,10,11

    def test_wrap_and_reorder_are_not_holes(self):
        pkts = [(0, 65534, 0), (1, 65535, 0), (2, 0, 0), (3, 2, 0), (4, 1, 0), (5, 3, 0)]
        self.assertEqual(owd.loss_bursts(pkts, merge_ns=0), [])


class Locked(unittest.TestCase):
    def test_profile_before_the_onsets_and_the_shift_control(self):
        # delay 0 except a 1 ms rise in the 100 ms before each onset
        onsets = [1000 * MS, 3000 * MS]
        t = [i * 10 * MS for i in range(500)]
        v = [1.0 if any(o - 100 * MS <= x < o for o in onsets) else 0.0 for x in t]
        bins = [(-200 * MS, -100 * MS), (-100 * MS, 0)]
        prof = owd.locked(t, v, onsets, bins)
        self.assertEqual(prof, [0.0, 1.0])
        ctl = owd.locked_control(t, v, onsets, bins, shifts=[1370 * MS, 2210 * MS])
        self.assertLess(ctl[1]["mean"], 1.0)                  # onsets moved away from the rise: it vanishes


class Drift(unittest.TestCase):
    def test_drift_is_the_median_of_per_step_slopes_so_an_rtp_base_jump_between_steps_does_not_count(self):
        # two steps, each 10 s of frames with OWD rising 0.07 ms/s; the second step's RTP base jumped by -500 ms
        rows = [{"t": int(s * 1e9), "first": 0.07 * s} for s in range(10)]
        rows += [{"t": int(s * 1e9), "first": 0.07 * s - 500.0} for s in range(10, 20)]
        step_idx = [0] * 10 + [1] * 10
        self.assertAlmostEqual(owd.drift(rows, step_idx), 0.07)


class LiveBase(unittest.TestCase):
    """The live reference (live_rel): a long drift-corrected minimum, as the app's port must compute it."""

    @staticmethod
    def series(seconds, fps=10, drift=0.07, queue=None):
        """Frames at fps: OWD = 5 + drift * t (+ queue_ms inside [q0, q1) s)."""
        t, v = [], []
        for i in range(seconds * fps):
            x = i / fps
            q = queue[2] if queue and queue[0] <= x < queue[1] else 0.0
            t.append(int(x * 1e9))
            v.append(5.0 + drift * x + q)
        return t, v

    def test_theil_sen_ignores_a_lifted_minority(self):
        xs = list(range(10))
        ys = [0.07 * x for x in xs]
        ys[4] += 30.0
        ys[5] += 30.0                      # a standing queue lifting 2 of 10 block minima
        self.assertAlmostEqual(owd.theil_sen(xs, ys), 0.07)

    def test_pure_drift_reads_zero_once_the_drift_is_known(self):
        t, v = self.series(400)
        rel = owd.live_rel(t, v, prior=0.07)
        self.assertLess(max(rel), 1e-9)                         # a plain 60 s minimum would read 0.07 * 60 = 4.2 ms

    def test_the_drift_is_learnt_from_the_blocks(self):
        t, v = self.series(400, drift=0.05)
        rel = owd.live_rel(t, v, prior=0.0)                     # wrong prior: 60 s x 0.05 = 3 ms until learnt
        self.assertGreater(max(rel[:500]), 1.0)
        self.assertLess(max(rel[-500:]), 1e-6)                  # after 6 blocks the estimate is exact

    def test_a_standing_queue_is_seen_for_the_whole_window(self):
        t, v = self.series(400, queue=(200, 250, 50.0))         # +50 ms for 50 s, inside the 60 s base window
        rel = owd.live_rel(t, v, prior=0.07)
        during = [r for x, r in zip(t, rel) if 210e9 <= x < 250e9]
        self.assertAlmostEqual(min(during), 50.0, places=6)
        plain = owd.relative(t, v, 2e9)
        self.assertLess(max(p for x, p in zip(t, plain) if 210e9 <= x < 250e9), 1.0)   # a 2 s minimum hides it

    def test_a_queue_longer_than_the_window_is_kept_by_an_unbounded_base_without_biasing_the_drift(self):
        # +50 ms standing for 150 s: half of the 300 s drift horizon. The drift must not learn it (blocks lifted
        # above the current line are left out of the fit), so the unbounded base reads the full 50 ms.
        t, v = self.series(400, queue=(100, 250, 50.0))
        rel = owd.live_rel(t, v, window_s=float("inf"), prior=0.07)
        during = [r for x, r in zip(t, rel) if 120e9 <= x < 250e9]
        self.assertAlmostEqual(min(during), 50.0, places=6)
        self.assertAlmostEqual(max(during), 50.0, places=6)

    def test_the_unbounded_base_keeps_a_bounded_state(self):
        # hours of frames since the last reset must not pile up: the unbounded base keeps only the lower convex hull
        # of (t, v), on which min(v - d t) lies for every d, so a drift update needs no history
        base = owd.LiveBase(window_s=float("inf"), prior=0.0)   # a wrong prior: keys trend upward until learnt
        for i in range(100_000):
            base.push(int(i * 1e7), 5.0 + 0.07 * i / 100 + ((i * 37) % 11) / 10.0)
        self.assertLess(base.stored(), 200)

    def test_an_rtp_base_jump_resets_the_base(self):
        t, v = self.series(300)
        v = [x if i < 1500 else x + 5000.0 for i, x in enumerate(v)]   # waybeam restart: +5 s RTP base jump
        rel = owd.live_rel(t, v, prior=0.07)
        self.assertLess(max(rel[1500:]), 1e-9)                  # without the reset: 5000 ms for 60 s


class Vectors(unittest.TestCase):
    def test_the_committed_synthetic_vectors_match_the_reference(self):
        # testdata/owd/synthetic.csv is what the app's port is checked against: it must stay the reference's output
        import math
        import os
        import owd_vectors
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "owd", "synthetic.csv")
        rows = [l.split(",") for l in open(path, encoding="utf-8") if not l.startswith("#")][1:]
        t, v = owd_vectors.synthetic()
        w60, winf = owd.live_rel(t, v, window_s=60.0), owd.live_rel(t, v, window_s=math.inf)
        self.assertEqual(len(rows), len(t))
        for r, a, b, c, d in zip(rows, t, v, w60, winf):
            self.assertEqual(int(r[0]), a)
            for got, want in zip(map(float, r[1:]), (b, c, d)):
                self.assertAlmostEqual(got, want, places=8)


class Frames(unittest.TestCase):
    def test_owd_first_and_last_and_the_size_slope(self):
        fr = [Frame(capture=i * 10 * MS, first=i * 10 * MS + 5 * MS, last=i * 10 * MS + 5 * MS + n * MS,
                    npkts=n, ready=None) for i, n in enumerate([2, 4, 6, 8])]
        rows = owd.per_frame(fr)
        self.assertEqual([r["first"] for r in rows], [5.0] * 4)          # ms, arbitrary offset
        self.assertEqual([r["last"] for r in rows], [7.0, 9.0, 11.0, 13.0])
        self.assertAlmostEqual(owd.slope([r["npkts"] for r in rows], [r["last"] for r in rows]), 1.0)
        self.assertAlmostEqual(owd.slope([r["npkts"] for r in rows], [r["first"] for r in rows]), 0.0)


if __name__ == "__main__":
    unittest.main()
