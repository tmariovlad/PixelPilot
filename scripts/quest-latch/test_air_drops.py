"""Tests for air_drops (the air's wfb_tx per-second PKT log -> drop intervals, time mapping, circular-shift control).
Run: python3 test_air_drops.py"""
import unittest

import air_drops

# air /tmp/wfbtx.log: "<air get_time_ms>\tPKT\tfec_timeouts:incoming:b_in:injected:b_inj:dropped:truncated"
# (wfb-ng tx.cpp:729-730); the counters are per log interval, so a line covers (previous ts, ts].
AIR = ["5000000\tPKT\t0:2900:3900000:2900:3900000:0:0\n",
       "5001000\tPKT\t0:2950:3960000:2900:3900000:50:0\n",
       "5002000\tPKT\t0:2950:3960000:2950:3960000:0:0\n",
       "5002000\tTX_ANT\t1\t2900:0:0:0:0\n"]


class Intervals(unittest.TestCase):
    def test_air_log_intervals(self):
        self.assertEqual(air_drops.parse_air_log(AIR), [(5000000, 5001000, 50), (5001000, 5002000, 0)])

    def test_mark_by_the_interval_a_time_falls_in(self):
        iv = air_drops.parse_air_log(AIR)
        self.assertEqual(air_drops.mark(5000500, iv), "Y")
        self.assertEqual(air_drops.mark(5001000, iv), "Y")    # (start, end]
        self.assertEqual(air_drops.mark(5001001, iv), "N")
        self.assertEqual(air_drops.mark(4999999, iv), "?")
        self.assertEqual(air_drops.mark(5002001, iv), "?")

    def test_capture_epoch_to_air_time(self):
        # Quest wall (logcat epoch) - quest_minus_pc = PC wall; + air_minus_pc = air get_time_ms
        self.assertEqual(air_drops.epoch_ms("  1790640000.900 1 2 I TAG: x"), 1790640000900.0)
        self.assertIsNone(air_drops.epoch_ms("--------- beginning of main"))
        self.assertEqual(air_drops.to_air_ms(1790640000900.0, 500.0, 5000000 - 1790640000000), 5000400.0)


class ShiftControl(unittest.TestCase):
    def test_rotation_moves_the_drop_values_and_keeps_the_bounds(self):
        iv = [(0, 1, 5), (1, 2, 0), (2, 3, 0)]
        self.assertEqual(air_drops.rotated(iv, 1), [(0, 1, 0), (1, 2, 0), (2, 3, 5)])
        self.assertEqual(air_drops.rotated(iv, 3), iv)

    def test_events_locked_to_the_drop_seconds_beat_every_rotation(self):
        # 10 one-second intervals, drops in seconds 2 and 6 (not rotation-symmetric); 4 events all inside them
        iv = [(i * 1000, (i + 1) * 1000, 9 if i in (2, 6) else 0) for i in range(10)]
        c = air_drops.shift_control([2500, 2600, 6100, 6900], iv)
        self.assertEqual(c["covered"], 4)
        self.assertAlmostEqual(c["share"], 1.0)
        # of the 9 non-zero rotations, shift 4 puts a drop on second 2 and shift 6 one on second 6: 0.5 each, rest 0
        self.assertAlmostEqual(c["shift_mean"], 1 / 9)
        self.assertAlmostEqual(c["shift_max"], 0.5)
        self.assertAlmostEqual(c["p_value"], 1 / 10)          # (1 + rotations >= real) / intervals

    def test_events_unrelated_to_the_drops_sit_at_the_rotation_baseline(self):
        iv = [(i * 1000, (i + 1) * 1000, 9 if i in (2, 6) else 0) for i in range(10)]
        c = air_drops.shift_control([500 + i * 1000 for i in range(10)], iv)   # one event per second
        self.assertAlmostEqual(c["share"], 0.2)
        self.assertAlmostEqual(c["shift_mean"], 0.2)
        self.assertAlmostEqual(c["p_value"], 1.0)

    def test_nothing_covered_gives_no_verdict(self):
        c = air_drops.shift_control([1], [(5, 6, 1)])
        self.assertEqual(c["covered"], 0)
        self.assertIsNone(c["share"])


if __name__ == "__main__":
    unittest.main()
