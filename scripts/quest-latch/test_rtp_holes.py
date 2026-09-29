"""Tests for rtp_holes (PPXR_RTPHOLE lines -> pre-FEC / post-FEC classes, summary, air-drop join with a circular-shift
control). Run: python3 test_rtp_holes.py"""
import unittest

import rtp_holes


def line(epoch, t_mono_ms, prev, nxt, gap, slots_lost, session=0, extra=""):
    return (f"  {epoch:.3f} 1 2 I PPXR_RTPHOLE: t_mono_ms={t_mono_ms} rtp_prev={prev} rtp_next={nxt} gap={gap} "
            f"slots_lost={slots_lost} session={session}{extra}")


PRE = line(1790640000.500, 1000, 10, 13, 2, 0)        # neighbours in contiguous wfb slots: never entered wfb_tx
POST = line(1790640001.500, 2000, 50, 54, 3, 3)       # the slots were lost on the radio
MIXED = line(1790640002.500, 3000, 90, 95, 4, 1)      # at least 3 of the 4 never entered wfb_tx
SESSION = line(1790640003.500, 4000, 99, 102, 2, 0, session=1)


class Classify(unittest.TestCase):
    def test_parse(self):
        h = rtp_holes.parse(MIXED)
        self.assertEqual((h["t_mono_ms"], h["rtp_prev"], h["rtp_next"], h["gap"], h["slots_lost"]),
                         (3000, 90, 95, 4, 1))
        self.assertEqual(h["class"], "mixed")
        self.assertIsNone(rtp_holes.parse("  1 2 3 I PPXR_FECBLK: t_mono_ms=1 blk=2"))

    def test_classes(self):
        self.assertEqual(rtp_holes.classify(2, 0, False), "pre_fec")
        self.assertEqual(rtp_holes.classify(3, 3, False), "post_fec")
        self.assertEqual(rtp_holes.classify(3, 5, False), "post_fec")    # extra lost slots: FEC-only padding
        self.assertEqual(rtp_holes.classify(4, 1, False), "mixed")
        self.assertEqual(rtp_holes.classify(2, 0, True), "unknown")      # wfb slot counter restarted in between

    def test_missing_packets_split(self):
        self.assertEqual(rtp_holes.split(4, 1, False), (3, 1))           # (pre-FEC at least, post-FEC at most)
        self.assertEqual(rtp_holes.split(3, 5, False), (0, 3))
        self.assertEqual(rtp_holes.split(2, 0, True), (0, 0))


class Summary(unittest.TestCase):
    def test_summary_counts_holes_and_packets_per_class(self):
        s = rtp_holes.summarize([PRE, POST, MIXED, SESSION, line(1790640004.0, 5000, 1, 3, 1, 0, extra=" suppressed=4")])
        self.assertEqual(s["holes"], 5)
        self.assertEqual(s["holes_by_class"], {"pre_fec": 2, "post_fec": 1, "mixed": 1, "unknown": 1})
        self.assertEqual(s["missing"], 12)
        self.assertEqual(s["missing_pre_fec"], 2 + 3 + 1)
        self.assertEqual(s["missing_post_fec"], 3 + 1)
        self.assertEqual(s["missing_unknown"], 2)
        self.assertAlmostEqual(s["pre_fec_share"], 6 / 10)               # of the packets with a known place
        self.assertEqual(s["gap_by_class"]["pre_fec"], {1: 1, 2: 1})
        self.assertEqual(s["suppressed"], 4)

    def test_tsv(self):
        rows = rtp_holes.to_tsv([PRE, POST]).splitlines()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].split("\t")[:6], ["t_mono_ms", "rtp_prev", "rtp_next", "gap", "slots_lost", "session"])
        self.assertTrue(rows[1].endswith("\tpre_fec"))


class AirJoin(unittest.TestCase):
    # 10 air seconds; the air dropped packets in air seconds 0 and 2 only (see air_drops.parse_air_log)
    AIR = [f"{5000000 + i * 1000}\tPKT\t0:2950:1:2950:1:{30 if i in (1, 3) else 0}:0\n" for i in range(11)]
    Q, A = 0.0, 5000000 - 1790640000000   # Quest wall = PC wall; air ms = PC ms + A

    def test_pre_fec_holes_in_drop_seconds_beat_the_rotations_and_post_fec_do_not(self):
        s = rtp_holes.summarize([PRE, POST, line(1790640002.2, 3000, 1, 3, 1, 0), line(1790640005.5, 6000, 5, 7, 1, 1)],
                                air=(self.AIR, self.Q, self.A))
        pre, post = s["air"]["pre_fec"], s["air"]["post_fec"]
        self.assertEqual(pre["covered"], 2)
        self.assertAlmostEqual(pre["share"], 1.0)        # both pre-FEC holes fall in air drop seconds
        self.assertLess(pre["shift_mean"], 1.0)
        self.assertEqual(post["covered"], 2)
        self.assertAlmostEqual(post["share"], 0.0)       # neither post-FEC hole does
        self.assertEqual([h["air_drop"] for h in rtp_holes.join_air([PRE, POST], self.AIR, self.Q, self.A)], ["Y", "N"])


if __name__ == "__main__":
    unittest.main()
