"""Tests for owd_crosscheck (the app's PPXR_STATS owd vs owd.py's LiveBase on the same capture).
Run: python3 test_owd_crosscheck.py"""
import unittest

import owd_crosscheck as oc

P = "  1790790000.000 1 2 I PPXR_STATS: "


class Parse(unittest.TestCase):
    def test_the_owd_fields_of_a_stats_line(self):
        rows = oc.parse_stats([P + "t=5000 enc50=1.00 owd50=0.40 owd95=1.20 owdw=60 owdu50=0.50 owdu95=1.30 owdd=0.071",
                               P + "t=5500 owd50=- owd95=- owdu50=- owdu95=- owdd=0.070",
                               "  1 2 3 I pixelpilot: other"])
        self.assertEqual(rows[0], {"t_ms": 5000, "owd50": 0.40, "owd95": 1.20, "owdu50": 0.50, "owdu95": 1.30,
                                   "owdd": 0.071})
        self.assertIsNone(rows[1]["owd50"])                  # "-" = no frames in the window


class Quantile(unittest.TestCase):
    def test_linear_interpolation_as_the_apps_segment(self):
        v = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(oc.quantile(v, 0.5), 2.5)     # Segment.quantile: pos = q * (n - 1)
        self.assertAlmostEqual(oc.quantile(v, 0.95), 3.85)
        self.assertIsNone(oc.quantile([], 0.5))


class Compare(unittest.TestCase):
    def setUp(self):
        # 100 frames over 1 s (trace clock, ns); the offline signal is simply i / 100 ms
        self.t = [i * 10_000_000 for i in range(100)]
        self.rel = [i / 100 for i in range(100)]

    def test_identical_values_give_zero_differences(self):
        # a stats line at monotonic 990 ms = trace 990 ms (offset 0), window 0.5 s: frames 50..99
        w = [self.rel[i] for i in range(50, 100)]
        row = {"t_ms": 990, "owd50": oc.quantile(sorted(w), 0.5), "owd95": oc.quantile(sorted(w), 0.95),
               "owdu50": oc.quantile(sorted(w), 0.5), "owdu95": oc.quantile(sorted(w), 0.95), "owdd": 0.07}
        out = oc.compare([row], self.t, self.rel, self.rel, [0.07] * 100, mono_minus_trace_ns=0, window_ns=500e6)
        self.assertEqual(len(out), 1)
        for k in ("owd50", "owd95", "owdu50", "owdu95", "owdd"):
            self.assertAlmostEqual(out[0]["d_" + k], 0.0, places=9)
        self.assertEqual(out[0]["n"], 50)

    def test_the_monotonic_offset_moves_the_window(self):
        w = [self.rel[i] for i in range(50, 100)]
        row = {"t_ms": 991, "owd50": oc.quantile(sorted(w), 0.5), "owd95": None, "owdu50": None, "owdu95": None,
               "owdd": None}
        # monotonic runs 1 ms ahead of the trace clock: 991 ms mono = 990 ms trace, the same window as above
        out = oc.compare([row], self.t, self.rel, self.rel, [0.07] * 100, mono_minus_trace_ns=1e6, window_ns=500e6)
        self.assertAlmostEqual(out[0]["d_owd50"], 0.0, places=9)
        self.assertIsNone(out[0]["d_owd95"])                 # the app printed "-": nothing to compare

    def test_summary(self):
        rows = [{"d_owd50": d, "d_owdu95": -d} for d in (0.0, 0.1, 0.2, 1.0)]
        s = oc.summarize(rows)
        self.assertEqual(s["owd50"]["n"], 4)
        self.assertAlmostEqual(s["owd50"]["median_abs"], 0.15)
        self.assertAlmostEqual(s["owd50"]["max_abs"], 1.0)
        self.assertAlmostEqual(s["owdu95"]["within_0.5ms"], 0.75)


if __name__ == "__main__":
    unittest.main()
