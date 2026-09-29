"""Tests for fec_blocks (PPXR_FECBLK lines -> per-block TSV + summary). Run: python3 test_fec_blocks.py"""
import unittest

import fec_blocks

P = "  1790640010.000 1 2 I PPXR_FECBLK: "
OUTAGE = P + ("t_mono_ms=5000 blk=10 k=4 n=8 got=11000000 span_us=300 gap_max_us=4000 "
              "frags=0:0:74:70,1:300:72:68 fcs=0 reason=flush next=11")
SCATTER = P + ("t_mono_ms=65000 blk=900 k=4 n=8 got=10101010 span_us=2400 gap_max_us=600 "
               "frags=0:0:60:58,2:700:61:59,4:1500:59:57,6:2400:60:58 fcs=3 reason=flush next=901")
RING = P + "t_mono_ms=66000 blk=950 k=4 n=8 got=00010000 span_us=0 gap_max_us=9000 frags=3:0:50:48 fcs=- reason=ring"


class Parse(unittest.TestCase):
    def test_a_block_line(self):
        b = fec_blocks.parse(OUTAGE)
        self.assertEqual(b["blk"], 10)
        self.assertEqual(b["got"], "11000000")
        self.assertEqual(b["missing"], 6)
        self.assertEqual(b["missing_data"], [2, 3])        # data fragments (< k) that never arrived
        self.assertEqual(b["where"], "tail")               # the hole is after the last fragment received
        self.assertEqual(b["rssi_a_dbm"], -37.0)           # mean of 74, 72 raw - 110 (devourer LinkHealth.cpp:8)
        self.assertEqual(b["rssi_b_dbm"], -41.0)
        self.assertEqual(b["fcs"], 0)
        self.assertIsNone(fec_blocks.parse("  1 2 3 I pixelpilot: tunnel window"))

    def test_hole_positions(self):
        self.assertEqual(fec_blocks.parse(SCATTER)["where"], "scattered")
        self.assertEqual(fec_blocks.parse(RING)["where"], "head+tail")
        self.assertIsNone(fec_blocks.parse(RING)["fcs"])   # keep_corrupted off: unknown, not zero


class Summary(unittest.TestCase):
    def test_summary_classifies_outages_fcs_and_scatter(self):
        s = fec_blocks.summarize([OUTAGE, SCATTER, RING])
        self.assertEqual(s["blocks"], 3)
        self.assertAlmostEqual(s["per_min"], 3 * 60 / 61.0)   # 5 s .. 66 s
        self.assertEqual(s["outage"], 2)                      # gap_max >= 2 ms
        self.assertEqual(s["with_fcs"], 1)
        self.assertEqual(s["fcs_known"], 2)
        self.assertEqual(s["where"], {"tail": 1, "scattered": 1, "head+tail": 1})
        self.assertEqual(s["reason"], {"flush": 2, "ring": 1})
        self.assertEqual(s["gap_max_us_p50"], 4000)

    def test_suppressed_lines_are_counted(self):
        s = fec_blocks.summarize([OUTAGE + " suppressed=7"])
        self.assertEqual(s["suppressed"], 7)

    def test_tsv_has_one_row_per_block(self):
        rows = fec_blocks.to_tsv([OUTAGE, SCATTER]).splitlines()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("t_mono_ms\tblk\tk\tn\tgot\tmissing\tmissing_data\twhere"))


class AirDropJoin(unittest.TestCase):
    # air /tmp/wfbtx.log: "<air get_time_ms>\tPKT\tfec_timeouts:incoming:b_in:injected:b_inj:dropped:truncated"
    # (wfb-ng tx.cpp:729-730); the counters are per log interval, so a line covers (previous ts, ts].
    AIR = ["5000000\tPKT\t0:2900:3900000:2900:3900000:0:0\n",
           "5001000\tPKT\t0:2950:3960000:2900:3900000:50:0\n",
           "5002000\tPKT\t0:2950:3960000:2950:3960000:0:0\n",
           "5002000\tTX_ANT\t1\t2900:0:0:0:0\n"]

    def test_each_block_is_marked_by_the_air_second_it_falls_in(self):
        # Quest wall (logcat epoch) - quest_minus_pc = PC wall; + air_minus_pc = air get_time_ms
        q_minus_pc_ms, air_minus_pc_ms = 500.0, 5000000 - 1790640000000
        in_drop = ("  1790640000.900 1 2 I PPXR_FECBLK: t_mono_ms=1 blk=1 k=4 n=8 got=11000000 span_us=0 "
                   "gap_max_us=0 frags=0:0:74:70 fcs=0 reason=flush next=2")
        clean = in_drop.replace("1790640000.900", "1790640001.700").replace("blk=1 ", "blk=5 ")
        outside = in_drop.replace("1790640000.900", "1790640009.000").replace("blk=1 ", "blk=9 ")
        marks = fec_blocks.join_air([in_drop, clean, outside], self.AIR, q_minus_pc_ms, air_minus_pc_ms)
        self.assertEqual([m["air_drop"] for m in marks], ["Y", "N", "?"])
        s = fec_blocks.summarize([in_drop, clean, outside], air=(self.AIR, q_minus_pc_ms, air_minus_pc_ms))
        self.assertEqual((s["air_drop_Y"], s["air_drop_N"], s["air_drop_unknown"]), (1, 1, 1))
        self.assertAlmostEqual(s["air_drop_share"], 0.5)     # of the blocks the air log covers


if __name__ == "__main__":
    unittest.main()
