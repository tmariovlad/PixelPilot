"""Offline check of ab_segments.analyze: a synthetic 167 fps stream with a known per-state delay step, clock drift and
jitter must come back as the injected deltas. Run: python3 test_ab_segments.py"""
import random

from ab_segments import Frame, analyze, fit_offset, frames_from_packets

FPS, STEP_S, DRIFT_PPM = 167.0, 12.0, 96.0
PLAN = ["A", "B", "A", "C", "A", "B", "A", "C", "A"]
EXTRA_MS = {"A": 0.0, "B": -1.5, "C": 2.0}  # injected capture -> frame-complete change per state
PKTS = {"A": 5, "B": 3, "C": 7}


def synth(seed=1):
    rnd = random.Random(seed)
    start = 1_000e9  # trace clock
    steps = [(start + i * STEP_S * 1e9, lab) for i, lab in enumerate(PLAN)]
    end = start + len(PLAN) * STEP_S * 1e9
    frames = []
    k = 0
    while True:
        cap = k / FPS * 1e9  # air capture clock
        t = start + cap
        if t >= end:
            break
        lab = PLAN[int((t - start) // (STEP_S * 1e9))]
        base = 7e6 + 3e6 + DRIFT_PPM * 1e-6 * (t - start)  # arbitrary constant + drift
        n = PKTS[lab]
        first = t + base + rnd.uniform(0, 1.5e6)
        last = first + n * 0.7e6 + EXTRA_MS[lab] * 1e6 - (n * 0.7e6 - PKTS["A"] * 0.7e6)
        frames.append(Frame(cap, first, last, n, last + 1.5e6))
        k += 1
    return frames, steps, end


def test_recovers_injected_deltas():
    frames, steps, end = synth()
    _, per_state, slope = analyze(frames, steps, end, 2e9, "A")
    s = dict(per_state)
    assert abs(slope * 1e6 - DRIFT_PPM) < 5, slope
    for lab in ("B", "C"):
        got = s[lab]["last_ms"] - s["A"]["last_ms"]
        assert abs(got - EXTRA_MS[lab]) < 0.1, (lab, got)
        assert abs((s[lab]["decoded_ms"] - s["A"]["decoded_ms"]) - EXTRA_MS[lab]) < 0.1
        assert abs(s[lab]["pkt_per_frame"] - PKTS[lab]) < 1e-9
        assert abs(s[lab]["fps"] - FPS) < 1.0, s[lab]["fps"]


def test_guard_drops_switch_frames():
    frames, steps, end = synth()
    per_step, _, _ = analyze(frames, steps, end, 2e9, "A")
    kept = sum(s["frames"] for _, _, s in per_step)
    expected = len(PLAN) * (STEP_S - 4) * FPS  # 2 s guard on each side of every switch
    assert abs(kept - expected) < len(PLAN) * 3, (kept, expected)


def test_frames_from_packets_groups_and_counts_loss():
    pkts = [(10, 1, 900), (11, 2, 900), (20, 4, 1800), (21, 5, 1800)]  # seq 3 lost
    frames, lost = frames_from_packets(pkts, [15, 30])
    assert lost == 1
    assert [(f.first, f.last, f.npkts, f.ready) for f in frames] == [(10, 11, 2, 15), (20, 21, 2, 30)]


def test_fit_offset_finds_step_misalignment():
    frames, steps, end = synth()
    skewed = [(t - 0.73e9, lab) for t, lab in steps]  # the air step log is 0.73 s early vs the trace
    assert abs(fit_offset(frames, skewed, end - 0.73e9) - 0.73) <= 0.02


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
