"""Tests for zslot (one table per arm for a -Z x payload slot, from ab_fit + ab_segments + zflush).
Run: python3 test_zslot.py"""
import unittest

import zslot


class Fits(unittest.TestCase):
    STEPS = None

    def setUp(self):
        ab_fit = zslot.load_ab_fit()
        # ABBA-ABBA, 60 s blocks, 1 sample/2 s: B is +0.5 ms, plus a slow linear drift of 0.1 ms/min
        self.steps = [ab_fit.Step(lab, 60.0 * i, 60.0 * (i + 1)) for i, lab in enumerate("ABBAABBA")]
        self.rows = []
        for i, s in enumerate(self.steps):
            for k in range(30):
                t = s.start + 2 * k
                noise = 0.01 * ((k * 7) % 5 - 2)
                self.rows.append((t, 5.0 + 0.1 * t / 60 + (0.5 if s.label == "B" else 0.0) + noise, i))

    def test_linear_and_quadratic_effects_per_arm(self):
        f = zslot.fits(self.rows, self.steps, "A")
        b, se = f["B"]["lin"]
        self.assertAlmostEqual(b, 0.5, delta=3 * se)
        self.assertLess(se, 0.02)
        self.assertIn("quad", f["B"])
        self.assertFalse(f["B"]["disagree"])
        self.assertNotIn("A", f)    # the reference has no effect row

    def test_arm_means_use_only_the_rows_of_that_arm(self):
        m = zslot.arm_means(self.rows, self.steps)
        self.assertAlmostEqual(m["B"] - m["A"], 0.5, delta=0.05)


class Disagree(unittest.TestCase):
    def test_models_disagree_when_apart_by_more_than_the_larger_se(self):
        self.assertTrue(zslot.disagree((-0.628, 0.080), (-0.781, 0.078)))    # HDP p3900 lnk50
        self.assertTrue(zslot.disagree((-0.324, 0.080), (-0.426, 0.076)))    # HDP p3000 lnk50: 0.102 apart
        self.assertFalse(zslot.disagree((0.724, 0.285), (0.550, 0.286)))     # HDP p3000 lnk95: 0.174 < 0.286

    def test_equal_or_close_models_agree(self):
        self.assertFalse(zslot.disagree((1.0, 0.1), (1.05, 0.1)))
        # the larger SE decides: 0.08 apart is within 0.1 though beyond 0.05
        self.assertFalse(zslot.disagree((0.0, 0.1), (0.08, 0.05)))


class Recovered(unittest.TestCase):
    # the shape zflush.rows returns for one state
    ROW = {"frames": 100,
           "clean": {"complete": None, "capture_last": {"n": 80, "mean": 0.5, "p95": 1.0, "p99": 1.5}},
           "recovered": {"complete": None, "capture_last": {"n": 15, "mean": 4.0, "p95": 9.5, "p99": 10.0}},
           "held": {"complete": None, "capture_last": {"n": 5, "mean": 5.0, "p95": 12.0, "p99": 13.0}},
           "waited_next_share": 0.05, "waited_next_of_recovered": 0.3}

    def test_share_wait_and_waited_next_of_the_recovered_frames(self):
        r = zslot.recovered(self.ROW)
        self.assertAlmostEqual(r["share"], 0.15)
        self.assertEqual((r["wait_mean"], r["wait_p95"], r["waited_next"]), (4.0, 9.5, 0.3))
        self.assertEqual(r["held"], 5)

    def test_no_recovered_frames(self):
        row = dict(self.ROW, recovered={"complete": None, "capture_last": None}, waited_next_of_recovered=None)
        r = zslot.recovered(row)
        self.assertEqual(r["share"], 0.0)
        self.assertIsNone(r["wait_mean"])


class Flush(unittest.TestCase):
    def test_fillers_per_second_over_the_summed_interval_time(self):
        self.assertAlmostEqual(zslot.flush_rate({"intervals": 2, "ms": 4000, "fillers": 560}), 140.0)

    def test_no_interval_time_is_no_rate(self):
        self.assertIsNone(zslot.flush_rate({"intervals": 0, "ms": 0, "fillers": 0}))
        self.assertIsNone(zslot.flush_rate(None))


class Render(unittest.TestCase):
    def test_linear_before_quadratic_and_a_flag_on_disagreeing_rows(self):
        arms = ["p2400", "p3900"]
        fits = {"lnk50": {"p3900": {"lin": (-0.628, 0.080), "quad": (-0.781, 0.078), "disagree": True}}}
        text = zslot.render_fits(fits, arms, "p2400")
        line = next(l for l in text.splitlines() if l.startswith("lnk50"))
        self.assertLess(line.index("-0.628"), line.index("-0.781"))
        self.assertIn("*", line)


if __name__ == "__main__":
    unittest.main()
