"""Tests for owd_lead (per ramp step of openipc-1f's lever_rc: when the queue signal rises vs when post-FEC loss starts,
and how fast the queue builds above the knee). Run: python3 test_owd_lead.py"""
import unittest

import owd_lead


def ramp(kbps_list, step_s=10.0, t0=100.0):
    """rc_fit-style steps: b<k> ramp steps in air uptime seconds (the last one open-ended)."""
    out = []
    for i, k in enumerate(kbps_list):
        up = t0 + i * step_s
        out.append({"label": f"b{k}", "kbps": k, "up": up, "end": up + step_s if i < len(kbps_list) - 1 else None})
    return out


def frames(steps, level_of, fps=100):
    """(t, owd_ms) at fps over every step; level_of(step, seconds into the step) gives the OWD."""
    out = []
    for i, s in enumerate(steps):
        end = s["end"] if s["end"] is not None else s["up"] + 10.0
        n = int((end - s["up"]) * fps)
        for j in range(n):
            x = j / fps
            out.append((s["up"] + x, level_of(i, x)))
    return out


class Lead(unittest.TestCase):
    def test_the_queue_signal_rises_before_the_loss_on_the_step_over_the_knee(self):
        st = ramp([8000, 12000])
        # b8000: flat 1 ms, no loss. b12000: 1 ms, then 10 ms from 0.5 s in; the first post-FEC hole at 2.5 s.
        fr = frames(st, lambda i, x: 10.0 if i == 1 and x >= 0.5 else 1.0)
        holes = [(st[1]["up"] + 2.5, st[1]["up"] + 2.5)]
        r = owd_lead.lead(st, fr, holes)
        b8, b12 = r["steps"]
        self.assertIsNone(b8["owd_cross_s"])
        self.assertIsNone(b8["loss_onset_s"])
        self.assertAlmostEqual(b12["owd_cross_s"], 0.5, places=6)
        self.assertAlmostEqual(b12["loss_onset_s"], 2.5, places=6)
        self.assertAlmostEqual(b12["lead_s"], 2.0, places=6)        # positive: the delay signal comes first
        self.assertAlmostEqual(b8["owd_med_ms"], 1.0)
        self.assertAlmostEqual(b12["owd_med_ms"], 10.0)               # after the 1 s settle
        self.assertAlmostEqual(b12["build_ms_per_mbps"], 9.0 / 4.0)  # (10 - 1) ms over 4 Mbit/s
        self.assertIsNone(b8["build_ms_per_mbps"])                   # no previous ramp step

    def test_a_single_window_spike_is_not_a_crossing(self):
        st = ramp([8000])
        fr = frames(st, lambda i, x: 10.0 if 2.0 <= x < 2.2 else 1.0)   # 200 ms: less than 2 windows of 250 ms
        self.assertIsNone(owd_lead.lead(st, fr, [])["steps"][0]["owd_cross_s"])

    def test_a_set_transient_can_be_skipped_but_the_lead_is_still_measured_from_the_set(self):
        st = ramp([8000])
        # a 0.6 s burst right after the SET (e.g. the IDR the SET triggers), then the real rise from 3 s
        fr = frames(st, lambda i, x: 10.0 if x < 0.6 or x >= 3.0 else 1.0)
        self.assertAlmostEqual(owd_lead.lead(st, fr, [])["steps"][0]["owd_cross_s"], 0.0)
        self.assertAlmostEqual(owd_lead.lead(st, fr, [], cross_skip_s=1.0)["steps"][0]["owd_cross_s"], 3.0)

    def test_only_ramp_steps_are_reported(self):
        st = ramp([8000]) + [{"label": "k105", "kbps": 8400, "up": 110.0, "end": 115.0},
                             {"label": "n1", "kbps": 8000, "up": 115.0, "end": None}]
        r = owd_lead.lead(st, frames(st[:1], lambda i, x: 1.0), [])
        self.assertEqual([s["label"] for s in r["steps"]], ["b8000"])

    def test_the_build_rate_fit_above_the_knee(self):
        st = ramp([8000, 10000, 12000, 14000])
        levels = [1.0, 1.0, 6.0, 11.0]                                   # knee at 12000: +5 ms per 2 Mbit/s after it
        fr = frames(st, lambda i, x: levels[i])
        r = owd_lead.lead(st, fr, [], knee_kbps=10000)
        self.assertAlmostEqual(r["build_ms_per_mbps_fit"], 2.5)       # over the steps >= the knee
        self.assertIsNone(owd_lead.lead(st, fr, [], knee_kbps=None)["build_ms_per_mbps_fit"])


class Clocks(unittest.TestCase):
    def test_quest_monotonic_to_air_uptime(self):
        # quest mono 1000 s; Quest REALTIME - MONOTONIC = 1.79e9 s; Quest - PC = -0.28 s; PC - air = +0.05 s;
        # SAMP0: air epoch 1.79e9 + 500 at air uptime 300 s
        off = owd_lead.compose_offset(realtime_minus_mono_s=1_790_000_000.0, quest_minus_pc_s=-0.28,
                                      pc_minus_air_s=0.05, samp0_epoch_s=1_790_000_500.0, samp0_up_s=300.0)
        quest_mono = 1000.0
        air_up = quest_mono - off
        # quest epoch 1_790_001_000; PC epoch 1_790_001_000.28; air epoch 1_790_001_000.23; air up = that - 1_790_000_200
        self.assertAlmostEqual(air_up, 800.23, places=6)


if __name__ == "__main__":
    unittest.main()
