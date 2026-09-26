"""Offline check of the phase-lock controller in rtp_pace.py: a 120 Hz latch grid, a source at 60 fps
with a clock offset, jittery transport and reports that arrive late. Run: python3 test_rtp_pace.py"""
import math
import random

from rtp_pace import PhaseLock, wrap

LATCH_P = 1 / 120


def simulate(lock, seconds=30, ppm=80, jitter_s=0.0005, target_s=0.001, start_phase_s=0.005, seed=1):
    rnd = random.Random(seed)
    fps, t, u = 60.0, start_phase_s, 0.0
    period = (1 / fps) * (1 + ppm * 1e-6)   # source clock runs slow by `ppm` vs the headset
    pending, window, waits, next_report = [], [], [], 0.25
    while t < seconds:
        ready = t + 0.004 + abs(rnd.gauss(0, jitter_s))          # transport + decode
        wait = (-ready) % LATCH_P                                 # until the next latch (grid at k*P)
        window.append(wait)
        if t >= next_report:                                      # headset reports the circular mean
            c = sum(math.cos(2 * math.pi * w / LATCH_P) for w in window)
            s = sum(math.sin(2 * math.pi * w / LATCH_P) for w in window)
            mean = (math.atan2(s, c) % (2 * math.pi)) / (2 * math.pi) * LATCH_P
            pending.append((t + 0.15, mean))                      # report reaches the source later
            window, next_report = [], next_report + 0.25
        while pending and pending[0][0] <= t:
            _, mean = pending.pop(0)
            if lock:
                u = lock.update(wrap(mean - target_s, LATCH_P))
        if t > seconds - 10:
            waits.append(wait)
        t += period + u
    return waits


def test_lock_converges_to_target_and_beats_free_running():
    locked = simulate(PhaseLock(60))
    mean_locked = sum(locked) / len(locked)          # linear mean = the latency actually paid
    misses = sum(w > 0.004 for w in locked) / len(locked)
    assert abs(mean_locked - 0.001) < 0.0008, mean_locked
    # 0.5 ms jitter against a 1 ms margin: a few % of frames miss the latch and wait a full period.
    assert misses < 0.08, misses
    # Free-running, averaged over start phases: ~P/2.
    free = [w for k in range(8) for w in simulate(None, start_phase_s=k * LATCH_P / 8, seed=k)]
    assert sum(free) / len(free) > 3 * mean_locked


def test_wrap_is_centered():
    assert abs(wrap(0.0081, LATCH_P) - (0.0081 - LATCH_P)) < 1e-12
    assert abs(wrap(0.001, LATCH_P) - 0.001) < 1e-12


if __name__ == "__main__":
    test_wrap_is_centered()
    test_lock_converges_to_target_and_beats_free_running()
    print("ok")
