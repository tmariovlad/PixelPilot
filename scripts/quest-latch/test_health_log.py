"""Tests for health_log (PPXR_EVENT / PPXR_HEALTH -> timeline + summary). Run: python3 test_health_log.py"""
import unittest

import health_log

# the same lines as they appear in files/ppxr_health.log ("TAG line") and in a logcat -v epoch capture
FILE = [
    "PPXR_EVENT t_mono_ms=10000 t_wall_ms=1790640010000 code=SIGNAL_LOST level=ALERT to=VIDEO_STALLED cause=freeze",
    "PPXR_EVENT t_mono_ms=11000 t_wall_ms=1790640011000 code=SIGNAL_OK level=INFO was=VIDEO_STALLED dur_ms=1000 cause=freeze",
    "PPXR_EVENT t_mono_ms=20000 t_wall_ms=1790640020000 code=SIGNAL_LOST level=WARN to=HOLD cause=freeze",
    "PPXR_EVENT t_mono_ms=20500 t_wall_ms=1790640020500 code=SIGNAL_OK level=INFO was=HOLD dur_ms=500 cause=freeze",
    "PPXR_EVENT t_mono_ms=30000 t_wall_ms=1790640030000 code=FREEZE_END level=INFO dur_ms=6000 slices=40",
    "PPXR_EVENT t_mono_ms=40000 t_wall_ms=1790640040000 code=IDR_FAILED level=WARN ok=1 failed=3 connect_timeout=2 refused=1",
    "PPXR_HEALTH t_mono_ms=40000 t_wall_ms=1790640040000 code=HEALTH level=INFO win_s=10 fps=150.0 frozen_pct=20.0",
    "PPXR_EVENT t_mono_ms=50000 t_wall_ms=1790640050000 code=SESSION_INACTIVE level=ALERT",
    "PPXR_EVENT t_mono_ms=53000 t_wall_ms=1790640053000 code=SESSION_ACTIVE level=INFO off_ms=3000",
    "PPXR_HEALTH t_mono_ms=70000 t_wall_ms=1790640070000 code=HEALTH level=INFO win_s=10 fps=130.0 frozen_pct=10.0",
]
LOGCAT = "  1790640010.000 111 222 I PPXR_EVENT: t_mono_ms=10000 t_wall_ms=1790640010000 code=SIGNAL_LOST level=ALERT to=X"


class Parse(unittest.TestCase):
    def test_file_and_logcat_lines_parse_the_same(self):
        tag, kv = health_log.parse(FILE[0])
        self.assertEqual(tag, "PPXR_EVENT")
        self.assertEqual(kv["code"], "SIGNAL_LOST")
        self.assertEqual(kv["cause"], "freeze")
        tag2, kv2 = health_log.parse(LOGCAT)
        self.assertEqual((tag2, kv2["t_mono_ms"], kv2["to"]), ("PPXR_EVENT", "10000", "X"))
        self.assertIsNone(health_log.parse("PPXR_STATS t=1 enc50=4"))
        self.assertIsNone(health_log.parse("  1790640010.000 111 222 I pixelpilot: tunnel window"))

    def test_timeline_is_one_row_per_line_in_time_order(self):
        rows = health_log.timeline([FILE[1], FILE[0]]).splitlines()
        self.assertEqual(rows[0].split("\t"), ["t_mono_ms", "t_wall_ms", "tag", "code", "level", "detail"])
        self.assertTrue(rows[1].startswith("10000\t1790640010000\tPPXR_EVENT\tSIGNAL_LOST\tALERT\tto=VIDEO_STALLED"))
        self.assertEqual(len(rows), 3)


class Summary(unittest.TestCase):
    def test_summary_counts_stalls_causes_freeze_session_and_idr_reasons(self):
        s = health_log.summarize(FILE)
        self.assertEqual(s["duration_s"], 60.0)                 # 10 s .. 70 s
        self.assertEqual(s["signal_lost"], 2)
        self.assertEqual(s["alerts"], 2)                         # the stall and the session
        self.assertAlmostEqual(s["stalls_per_min"], 2.0)
        self.assertEqual(s["causes"], {"freeze": 2})
        self.assertEqual(s["lost_ms"], 1500)
        self.assertEqual(s["by_kind"], {"VIDEO_STALLED": 1, "HOLD": 1})
        self.assertAlmostEqual(s["freeze_pct"], 10.0)           # 6 s of 60 s
        self.assertEqual(s["session_off_ms"], 3000)
        self.assertEqual(s["idr_fail_reasons"], {"connect_timeout": 2, "refused": 1})
        self.assertAlmostEqual(s["health_fps_mean"], 140.0)
        self.assertAlmostEqual(s["health_frozen_pct_mean"], 15.0)

    def test_menu_switch_gaps_are_counted_apart_from_stalls(self):
        lines = [
            "PPXR_EVENT t_mono_ms=1000 t_wall_ms=1790640001000 code=SWITCH_GAP level=INFO",
            "PPXR_EVENT t_mono_ms=4200 t_wall_ms=1790640004200 code=SWITCH_END level=INFO dur_ms=3200",
            "PPXR_EVENT t_mono_ms=9000 t_wall_ms=1790640009000 code=SWITCH_GAP level=INFO",
            "PPXR_EVENT t_mono_ms=12500 t_wall_ms=1790640012500 code=SWITCH_END level=INFO dur_ms=3500 to=VIDEO_STALLED",
            "PPXR_EVENT t_mono_ms=12500 t_wall_ms=1790640012500 code=SIGNAL_LOST level=ALERT to=VIDEO_STALLED cause=stall",
            "PPXR_EVENT t_mono_ms=13500 t_wall_ms=1790640013500 code=SIGNAL_OK level=INFO was=VIDEO_STALLED dur_ms=1000 cause=stall",
        ]
        s = health_log.summarize(lines)
        self.assertEqual(s["switch_gaps"], 2)
        self.assertEqual(s["switch_ms"], 6700)
        self.assertEqual(s["switch_ended_without_video"], 1)
        self.assertEqual(s["signal_lost"], 1)                   # the stall after the second switch, not the gaps
        self.assertEqual(s["lost_ms"], 1000)

    def test_idr_handshake_sums_attempts_and_late_wins_over_both_codes(self):
        # the connect race's fields (IdrRequester, 2026-09-29): SYNs started, requests won by attempt >= 2, and each
        # line's mean connect time; lines from older builds carry none of them
        lines = FILE + [
            "PPXR_EVENT t_mono_ms=41000 t_wall_ms=1790640041000 code=IDR level=INFO ok=3 failed=0 attempts=4 late=1 connected=3 connect_ms=60",
            "PPXR_EVENT t_mono_ms=42000 t_wall_ms=1790640042000 code=IDR_FAILED level=WARN ok=1 failed=1 connect_timeout=1 attempts=8 late=0 connected=1 connect_ms=20",
        ]
        s = health_log.summarize(lines)
        self.assertEqual(s["idr_attempts"], 12)
        self.assertEqual(s["idr_won_late"], 1)
        self.assertAlmostEqual(s["idr_connect_ms_mean"], 50.0)   # per request: (3*60 + 1*20) / 4
        self.assertEqual(health_log.summarize(FILE)["idr_attempts"], 0)

    def test_empty_input(self):
        s = health_log.summarize([])
        self.assertEqual(s["signal_lost"], 0)
        self.assertEqual(s["duration_s"], 0.0)


if __name__ == "__main__":
    unittest.main()
