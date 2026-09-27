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


def test_lost_per_step_counts_sequence_gaps_inside_the_window():
    frames, steps, end = synth()
    # one packet per frame, arriving at the frame's first time; drop two seqs in step 1 (B) and one in a guard band
    pkts = [(f.first, k & 0xFFFF, int(f.capture * 90000 / 1e9)) for k, f in enumerate(frames)]
    in_b = [k for k, p in enumerate(pkts) if steps[1][0] + 3e9 <= p[0] < steps[1][0] + 5e9][:2]
    in_guard = [k for k, p in enumerate(pkts) if steps[2][0] - 1e9 <= p[0] < steps[2][0]][:1]
    pkts = [p for k, p in enumerate(pkts) if k not in in_b + in_guard]
    per_step, per_state, _ = analyze(frames, steps, end, 2e9, "A", pkts)
    lost = {i: r["lost"] for i, _, r in per_step}
    assert lost[1] == 2 and sum(lost.values()) == 2, lost
    assert dict(per_state)["B"]["lost"] == 2
    # lost_pct uses the same guarded window: 2 lost out of (received in step 1's window + 2)
    a, b = steps[1][0] + 2e9, steps[2][0] - 2e9
    received = sum(1 for p in pkts if a <= p[0] < b)
    row1 = next(r for i, _, r in per_step if i == 1)
    assert abs(row1["lost_pct"] - 100.0 * 2 / (received + 2)) < 1e-9, row1["lost_pct"]
    assert all(r["lost_pct"] == 0 for i, _, r in per_step if i != 1)


def test_undecoded_counts_frames_without_a_ready_mark_inside_the_window():
    frames, steps, end = synth()
    # no decoded-frame mark for 5 frames in the middle of step 3 (C) and for 1 frame inside a guard band
    mid = [k for k, f in enumerate(frames) if steps[3][0] + 5e9 <= f.first][:5]
    guard = [k for k, f in enumerate(frames) if steps[4][0] - 1e9 <= f.first][:1]
    frames = [f._replace(ready=None) if k in mid + guard else f for k, f in enumerate(frames)]
    per_step, per_state, _ = analyze(frames, steps, end, 2e9, "A")
    und = {i: r["undecoded"] for i, _, r in per_step}
    assert und[3] == 5, und
    assert sum(und.values()) == 5, und
    assert dict(per_state)["C"]["undecoded"] == 5
    assert dict(per_state)["A"]["undecoded"] == 0


def test_state_whose_steps_are_all_guard_is_skipped_not_a_crash():
    frames, steps, end = synth()
    short = steps[:2] + [(steps[2][0], "Z"), (steps[2][0] + 3e9, "A")] + steps[3:]  # "Z" lasts 3 s < 2 guards
    per_step, per_state, _ = analyze(frames, short, end, 2e9, "A")
    assert "Z" not in dict(per_state)
    assert all(lab != "Z" for _, lab, _ in per_step)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
