"""Offline checks of tu_pause: pause gaps between consecutive RTP arrivals, their phase lock to 102.4 ms, and the
latency modulation folded at that period. Run: python3 test_tu_pause.py"""

from tu_pause import TU_PERIOD_S, fold_amplitude, pause_gaps, rayleigh_z

S = 1e9


def synth_arrivals(seconds, pause_ms, rate_hz=2000.0):
    """Packets every 1/rate s; with pause_ms > 0 nothing arrives during the first pause_ms of each 102.4 ms cycle."""
    t, out = 0.0, []
    while t < seconds:
        if pause_ms <= 0 or (t % TU_PERIOD_S) >= pause_ms / 1000:
            out.append(t * S)
        t += 1.0 / rate_hz
    return out


def test_pause_gaps_found_only_with_a_pause():
    with_pause = pause_gaps(synth_arrivals(10, 3.7), 3.0, 6.0)
    without = pause_gaps(synth_arrivals(10, 0), 3.0, 6.0)
    assert 95 <= len(with_pause) <= 99, len(with_pause)   # ~9.77 cycles/s x 10 s
    assert without == []


def test_rayleigh_locks_on_the_pause_and_not_on_random_times():
    import random
    rnd = random.Random(1)
    locked = [k * TU_PERIOD_S * S + rnd.uniform(-1e5, 1e5) for k in range(200)]
    rand = [rnd.uniform(0, 20) * S for _ in range(200)]
    assert rayleigh_z(locked, TU_PERIOD_S) > 150
    assert rayleigh_z(rand, TU_PERIOD_S) < 10


def test_fold_amplitude_sees_a_latency_bump_at_one_phase():
    # frames every 6 ms; latency +3 ms for frames in the first 20 ms of each 102.4 ms cycle, else 0
    pts = []
    t = 0.0
    while t < 30:
        lat = 3.0 if (t % TU_PERIOD_S) < 0.020 else 0.0
        pts.append((t * S, lat))
        t += 0.006
    amp = fold_amplitude(pts, TU_PERIOD_S, bins=16)
    flat = fold_amplitude([(t0, 0.5) for t0, _ in pts], TU_PERIOD_S, bins=16)
    assert amp > 2.0, amp
    assert flat < 0.01, flat



def test_a_gap_with_a_missing_packet_is_loss_not_a_pause():
    t = [0, 1e6, 5e6, 6e6, 10e6]          # gaps: 1, 4, 1, 4 ms
    seqs = [1, 2, 3, 4, 6]                  # the last 4 ms gap skips seq 5
    assert pause_gaps(t, 3.0, 4.6, seqs) == [1e6]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
