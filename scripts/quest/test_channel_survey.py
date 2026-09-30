"""Tests for channel_survey (PPXR_SURVEY lines -> per-channel table + bar graph). Run: python3 test_channel_survey.py"""
import json
import unittest

import channel_survey

P = "  1790790000.000 1 2 I PPXR_SURVEY: "


def dwell(chan, round_, oth_us, own_us, busy, rssi_max, frames=10):
    d = {"ev": "survey.dwell", "v": 1, "seq": 0, "chan": f"5:{chan}/20", "round": round_, "observe_ms": 1000,
         "nhm_busy": busy, "frames": frames, "rssi_max": rssi_max, "dvr_air_us": own_us, "oth_air_us": oth_us}
    return P + json.dumps(d, separators=(",", ":"))


LINES = [
    P + '{"ev":"survey.start","plan":"0x0000abcd","channels":3,"rounds":2,"dwell_ms":1000,"link":165}',
    dwell(149, 0, 10_000, 0, 5, 50), dwell(149, 1, 30_000, 0, 7, 55),
    dwell(157, 0, 400_000, 0, 60, 70), dwell(157, 1, 380_000, 0, 58, 72),
    dwell(165, 0, 5_000, 500_000, 40, 80, frames=0), dwell(165, 1, 5_000, 480_000, 42, 81, frames=0),
    P + '{"ev":"channel.ranking","t":1,"gen":"a","n":3,"c0":"5:149/20 q=1 score=0.96 occ=0.02 rej=0",'
        '"c1":"5:165/20 q=1 score=0.95 occ=0.01 rej=0","c2":"5:157/20 q=0 score=0.40 occ=0.39 rej=1"}',
    P + '{"ev":"survey.result","recommended":149,"link":165,"dwells":6,"aborted":0}',
    "  1790790001.000 1 2 I pixelpilot: unrelated",
]


class Parse(unittest.TestCase):
    def test_the_run_is_split_into_its_events(self):
        run = channel_survey.parse(LINES)
        self.assertEqual(run["start"]["link"], 165)
        self.assertEqual(len(run["dwells"]), 6)
        self.assertEqual(run["result"]["recommended"], 149)
        self.assertEqual([r["chan"] for r in run["ranking"]], [149, 165, 157])
        self.assertEqual(run["ranking"][2], {"chan": 157, "qualified": False, "score": 0.40, "occ": 0.39, "rej": 1})

    def test_per_channel_means_and_the_strongest_foreign_signal(self):
        ch = channel_survey.per_channel(channel_survey.parse(LINES)["dwells"])
        self.assertAlmostEqual(ch[149]["foreign_pct"], 2.0)      # (1 % + 3 %) / 2
        self.assertAlmostEqual(ch[157]["foreign_pct"], 39.0)
        self.assertAlmostEqual(ch[165]["own_pct"], 49.0)         # our link's own video: shown, not counted as busy
        self.assertAlmostEqual(ch[157]["nhm_busy"], 59.0)
        self.assertEqual(ch[157]["rssi_max_dbm"], -38)           # raw 72 - 110
        self.assertIsNone(ch[165]["rssi_max_dbm"])               # no frames decoded there: no RSSI
        self.assertEqual(ch[149]["dwells"], 2)


class Chart(unittest.TestCase):
    def test_one_bar_per_channel_with_the_link_and_the_recommendation_marked(self):
        run = channel_survey.parse(LINES)
        rows = channel_survey.chart(channel_survey.per_channel(run["dwells"]), run)
        self.assertEqual(len(rows), 3)
        r157 = next(r for r in rows if r.startswith("157"))
        self.assertIn("39%", r157)
        self.assertIn("NHM 59%", r157)
        self.assertIn("not qualified", r157)
        self.assertIn("<- recommended", next(r for r in rows if r.startswith("149")))
        self.assertIn("(link, own video 49%)", next(r for r in rows if r.startswith("165")))


if __name__ == "__main__":
    unittest.main()
