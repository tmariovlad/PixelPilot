"""Tests for stats_log (PPXR_STATS logcat lines -> TSV). Run: python3 test_stats_log.py"""
import unittest

import stats_log

L1 = "         1790640000.250 11071 11186 I PPXR_STATS: t=5000 enc50=4.50 enc95=- n=12 sync=1 mcs=2"
L2 = "         1790640002.250 11071 11186 I PPXR_STATS: t=7000 enc50=4.10 enc95=5.00 n=10 sync=1 mcs=2 extra=9"
NOISE = "         1790640001.000 11071 11200 I pixelpilot: tunnel window: pkts 2 lost 0"


class Parse(unittest.TestCase):
    def test_a_stats_line_gives_its_epoch_and_pairs(self):
        epoch, kv = stats_log.parse_line(L1)
        self.assertEqual(epoch, "1790640000.250")
        self.assertEqual(kv, {"t": "5000", "enc50": "4.50", "enc95": "", "n": "12", "sync": "1", "mcs": "2"})

    def test_other_lines_are_skipped(self):
        self.assertIsNone(stats_log.parse_line(NOISE))
        self.assertIsNone(stats_log.parse_line(""))

    def test_tsv_keeps_first_seen_key_order_and_adds_late_keys_at_the_end(self):
        rows = stats_log.to_tsv([L1, NOISE, L2]).splitlines()
        self.assertEqual(rows[0].split("\t"), ["epoch", "t", "enc50", "enc95", "n", "sync", "mcs", "extra"])
        self.assertEqual(rows[1].split("\t"), ["1790640000.250", "5000", "4.50", "", "12", "1", "2", ""])
        self.assertEqual(rows[2].split("\t")[-1], "9")
        self.assertEqual(len(rows), 3)

    def test_no_stats_lines_gives_only_a_header(self):
        self.assertEqual(stats_log.to_tsv([NOISE]), "epoch\n")


if __name__ == "__main__":
    unittest.main()
