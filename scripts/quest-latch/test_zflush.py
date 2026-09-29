"""Tests for zflush (-Z analysis: PPXR_RELEASE + trace frames + the air's FRAME_FLUSH per step).
Run: python3 test_zflush.py"""
import unittest

import air_drops
import zflush
from ab_segments import Frame, RTP_HZ

P = "  1790640010.000 1 2 I PPXR_RELEASE: "
# frame 1000's tail was behind a gap: recovered in the same call as frame 4000's packets -> it waited for the next frame
WAITED = P + "t_mono_ms=5000 rec=1 n=5 frames=1000:10-12:1,4000:13-14:0"
# frame 7000's block closed with its own packets (a -Z filler close): recovered, but no next-frame packets in the call
OWN = P + "t_mono_ms=6000 rec=2 n=3 frames=7000:20-22:1"
# held behind a gap and flushed without recovery
HELD = P + "t_mono_ms=7000 rec=0 n=2 frames=9000:30-31:0 more=2 suppressed=3"


def frame(ts, first_ms, last_ms, npkts=5):
    return Frame(ts * 1e9 / RTP_HZ, first_ms * 1e6, last_ms * 1e6, npkts, None)


class Releases(unittest.TestCase):
    def test_parse(self):
        r = zflush.parse(WAITED)
        self.assertEqual((r["t_mono_ms"], r["rec"], r["n"]), (5000, 1, 5))
        self.assertEqual(r["frames"], [(1000, 10, 12, True), (4000, 13, 14, False)])
        h = zflush.parse(HELD)
        self.assertEqual((h["more"], h["suppressed"]), (2, 3))
        self.assertIsNone(zflush.parse("  1 2 3 I PPXR_RTPHOLE: t_mono_ms=1 gap=1"))

    def test_frame_flags(self):
        f = zflush.frame_flags([WAITED, OWN, HELD])
        self.assertEqual(f[1000], {"recovered": True, "waited_next": True})
        self.assertEqual(f[4000], {"recovered": True, "waited_next": False})   # released with the recovery
        self.assertEqual(f[7000], {"recovered": True, "waited_next": False})
        self.assertEqual(f[9000], {"recovered": False, "waited_next": False})

    def test_a_marker_group_last_in_the_call_did_not_wait(self):
        f = zflush.frame_flags([P + "t_mono_ms=1 rec=1 n=3 frames=100:1-1:0,200:2-3:1"])
        self.assertFalse(f[200]["waited_next"])
        self.assertFalse(f[100]["waited_next"])   # no marker of 100 in this call: its end was delivered earlier

    def test_class_of_a_frame(self):
        flags = zflush.frame_flags([WAITED, HELD])
        self.assertEqual(zflush.frame_class(frame(1000, 0, 5), flags), "recovered")
        self.assertEqual(zflush.frame_class(frame(9000, 0, 5), flags), "held")
        self.assertEqual(zflush.frame_class(frame(12345, 0, 5), flags), "clean")
        self.assertEqual(zflush.ts32(frame((1 << 32) + 1000, 0, 5)), 1000)   # the trace unwraps; the log does not


class Stats(unittest.TestCase):
    def test_distribution(self):
        s = zflush.dist([float(v) for v in range(1, 101)])
        self.assertEqual(s["n"], 100)
        self.assertAlmostEqual(s["mean"], 50.5)
        self.assertEqual((s["p95"], s["p99"]), (96.0, 100.0))    # ab_segments.pct: v[int(p * n)]
        self.assertIsNone(zflush.dist([]))

    def test_rows_split_clean_and_recovered_per_state(self):
        flags = zflush.frame_flags([WAITED, OWN])
        frames = [frame(1000, 100, 110), frame(7000, 200, 204), frame(20, 300, 301), frame(30, 1300, 1302),
                  frame(40, 2300, 2301)]
        steps, end = [(0.0, "Z"), (1000e6, "noZ")], 3000e6
        line = lambda _t: 0.0
        rows = zflush.rows(frames, flags, steps, end, 0.0, line)
        z = rows["Z"]
        self.assertEqual(z["frames"], 3)
        self.assertEqual(z["recovered"]["complete"]["n"], 2)
        self.assertAlmostEqual(z["recovered"]["complete"]["mean"], 7.0)     # (10 + 4) / 2 ms, first -> last
        self.assertEqual(z["clean"]["complete"]["n"], 1)
        self.assertAlmostEqual(z["waited_next_share"], 1 / 3)
        self.assertAlmostEqual(z["waited_next_of_recovered"], 1 / 2)
        self.assertEqual(rows["noZ"]["frames"], 2)
        self.assertIsNone(rows["noZ"]["recovered"]["complete"])


class AirFrameFlush(unittest.TestCase):
    # -Z's per-interval line (wfb-ng o117-marker-flush tx.cpp:827): ts TAB FRAME_FLUSH TAB frame_ends:blocks_closed:fillers
    AIR = ["5000000\tPKT\t0:2950:1:2950:1:0:0\n", "5000000\tFRAME_FLUSH\t90:88:300\n",
           "5001000\tPKT\t0:2950:1:2950:1:0:0\n", "5001000\tFRAME_FLUSH\t90:85:280\n",
           "5002000\tFRAME_FLUSH\t90:0:0\n"]

    def test_intervals(self):
        self.assertEqual(air_drops.parse_intervals(self.AIR, "FRAME_FLUSH"),
                         [(5000000, 5001000, ["90", "85", "280"]), (5001000, 5002000, ["90", "0", "0"])])
        self.assertEqual(air_drops.parse_air_log(self.AIR), [(5000000, 5001000, 0)])   # PKT only, unchanged

    def test_per_step_sums(self):
        iv = air_drops.parse_intervals(self.AIR, "FRAME_FLUSH")
        to_trace = lambda air_ms: (air_ms - 5000000) * 1e6          # air ms -> trace ns, for the test
        steps, end = [(0.0, "Z"), (1500e6, "noZ")], 3000e6
        s = zflush.air_per_step(iv, to_trace, steps, end, 0.0)
        self.assertEqual(s["Z"], {"intervals": 1, "frame_ends": 90, "blocks_closed": 85, "fillers": 280})
        self.assertEqual(s["noZ"], {"intervals": 1, "frame_ends": 90, "blocks_closed": 0, "fillers": 0})


if __name__ == "__main__":
    unittest.main()
