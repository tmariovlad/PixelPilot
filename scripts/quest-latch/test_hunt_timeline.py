"""Tests for hunt_timeline (rig step events with +-60 s of air / Quest / watchdog context on the PC clock).
Run: python3 test_hunt_timeline.py"""
import csv
import os
import tempfile
import unittest

import hunt_timeline as ht

PC_MINUS_AIR = 0.05
QUEST_MINUS_PC = -0.28


class Sources(unittest.TestCase):
    def test_runs_summary_gives_a_start_and_an_end_row(self):
        rows = ht.runs_summary(["run03 abort start 1000.5 end 1040.25\n", "junk\n"])
        self.assertEqual(rows, [(1000.5, "rig", "run03 start"), (1040.25, "rig", "run03 abort")])

    def test_air_health_keeps_ev_lines_on_the_pc_clock(self):
        lines = ["AH t=1000 up=1 boot=b seq=1 temp=40\n",
                 "EV t=1002 up=3 boot=b code=SNAP level=INFO trig=degradat file=1002_degradat.txt\n"]
        rows = ht.air_health(lines, PC_MINUS_AIR)
        self.assertEqual(len(rows), 1)
        t, src, text = rows[0]
        self.assertAlmostEqual(t, 1002.05)
        self.assertEqual(src, "air")
        self.assertIn("code=SNAP", text)
        self.assertIn("trig=degradat", text)

    def test_snapshot_names_carry_their_air_epoch_and_trigger(self):
        rows = ht.snapshots(["1002_degradat.txt", "1790780000_manual.txt", "README"], PC_MINUS_AIR)
        self.assertEqual([(round(t, 2), s, x) for t, s, x in rows],
                         [(1002.05, "snap", "1002_degradat.txt"), (1790780000.05, "snap", "1790780000_manual.txt")])

    def test_watchdog_hh_mm_ss_on_a_utc_date_with_midnight_wrap(self):
        lines = ["[wd 23:59:50] DEGRADAT [hd] Fps_1s=45 — confirmare 1/2\n",
                 "[wd 00:00:10] RESTART waybeam\n"]
        rows = ht.watchdog(lines, "2026-09-30", 0.0, PC_MINUS_AIR)
        base = 1790812800   # 2026-10-01 00:00:00 UTC
        self.assertAlmostEqual(rows[0][0], base - 10 + PC_MINUS_AIR)
        self.assertAlmostEqual(rows[1][0], base + 10 + PC_MINUS_AIR)   # next day, not 24 h earlier
        self.assertEqual(rows[0][1], "wd")
        self.assertTrue(rows[0][2].startswith("DEGRADAT"))

    def test_watchdog_local_offset(self):
        rows = ht.watchdog(["[wd 03:00:00] x\n"], "2026-10-01", 3.0, 0.0)   # air local = UTC+3
        self.assertAlmostEqual(rows[0][0], 1790812800)

    def test_quest_event_uses_its_wall_clock_and_stats_map_mono_per_boot(self):
        lines = [
            "PPXR_EVENT t_mono_ms=10000 t_wall_ms=1000010000 code=SIGNAL_LOST level=ALERT to=NO_PACKETS\n",
            "PPXR_STATS t=12000 enc50=3.9 lnk50=9.7 tot50=20.1 fps=119.0 post=0.08 n=237 rssiA=-25\n",
            # the Quest rebooted: mono restarts, a new pair gives the new offset
            "PPXR_EVENT t_mono_ms=500 t_wall_ms=1000100500 code=SESSION_ACTIVE level=INFO\n",
            "PPXR_STATS t=2500 tot50=21.0 n=10\n",
        ]
        rows = ht.quest(lines, QUEST_MINUS_PC, ("tot50", "lnk50", "n"))
        self.assertEqual([r[1] for r in rows], ["quest", "stats", "quest", "stats"])
        self.assertAlmostEqual(rows[0][0], 1000010.0 - QUEST_MINUS_PC)
        self.assertAlmostEqual(rows[1][0], 1000012.0 - QUEST_MINUS_PC)
        self.assertEqual(rows[1][2], "tot50=20.1 lnk50=9.7 n=237")
        self.assertAlmostEqual(rows[3][0], 1000102.5 - QUEST_MINUS_PC)
        self.assertIn("code=SIGNAL_LOST", rows[0][2])

    def test_stats_of_a_new_boot_wait_for_its_own_clock_pair(self):
        lines = ["PPXR_EVENT t_mono_ms=900000 t_wall_ms=1000900000 code=X level=INFO\n",
                 "PPXR_STATS t=899000 tot50=1\n",    # logged 1 s before the pair: same boot, kept
                 "PPXR_STATS t=3000 tot50=2\n"]      # mono restarted: another boot, no pair yet -> skipped
        rows = ht.quest(lines, 0.0, ("tot50",))
        self.assertEqual([r[2] for r in rows if r[1] == "stats"], ["tot50=1"])

    def test_quest_stats_before_any_clock_pair_are_skipped(self):
        self.assertEqual(ht.quest(["PPXR_STATS t=1 tot50=1\n"], 0.0, ("tot50",)), [])

    def test_quest_logcat_format_too(self):
        line = ("  1000010.100 111 222 I PPXR_EVENT: t_mono_ms=10000 t_wall_ms=1000010000 code=FREEZE_START "
                "level=WARN\n")
        rows = ht.quest([line], 0.0, ("tot50",))
        self.assertAlmostEqual(rows[0][0], 1000010.0)


class Timeline(unittest.TestCase):
    def test_each_event_gets_the_rows_within_its_context_in_time_order(self):
        ev = ht.fls.Event("hd", 1000.0, 1030.0, 12, 71.0, 46.0)
        rows = [(930.0, "air", "too early"), (945.0, "wd", "DEGRADAT"), (1010.0, "quest", "x"),
                (990.0, "snap", "990_degradat.txt"), (1089.0, "stats", "late in"), (1091.0, "air", "too late")]
        blocks = ht.timeline([ev], rows, 60.0)
        self.assertEqual(len(blocks), 1)
        got = [r[2] for r in blocks[0][1]]
        self.assertEqual(got, ["DEGRADAT", "990_degradat.txt", "x", "late in"])

    def test_render_marks_the_event_and_times_relative_to_its_start(self):
        ev = ht.fls.Event("hd", 1000.0, 1030.0, 12, 71.0, 46.0)
        text = ht.render([(ev, [(955.5, "wd", "DEGRADAT [hd]")])], 60.0)
        self.assertIn("STEP hd", text)
        self.assertIn("-44.5", text)
        self.assertIn("DEGRADAT [hd]", text)
        self.assertIn(">>> step start", text)


class Cli(unittest.TestCase):
    def test_end_to_end_on_synthetic_files(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "per_flash.csv")
            with open(pf, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["run", "id", "pc_epoch", "result", "first_us", "full_us", "step"])
                for i in range(60):   # 1.5 s apart; from flash 20 on, +25 ms (the 71 ms state)
                    w.writerow(["01", i, f"{1000 + 1.5 * i:.3f}", "ok", 46000 + (25000 if i >= 20 else 0), "", "hd"])
            ah = os.path.join(d, "air_health.log")
            with open(ah, "w") as fh:
                fh.write("EV t=1025 up=1 boot=b code=SNAP level=INFO trig=degradat\n")
            out = ht.run([pf], fixed="hd=46", runs=None, air_health_log=ah, snap_names=[], quest_logs=[],
                         wd_log=None, wd_date=None, wd_utc_offset_h=0.0, pc_minus_air_s=0.0,
                         quest_minus_pc_s=0.0, ctx_s=60.0, stats_keys=ht.STATS_KEYS)
        self.assertIn("STEP hd", out)
        self.assertIn("code=SNAP", out)


if __name__ == "__main__":
    unittest.main()
