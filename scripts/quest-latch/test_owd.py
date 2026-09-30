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
