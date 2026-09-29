"""Offline checks of step_jitter.residual_stats: per-step latency spread around the step's own median, which stays valid
when every step restarts the encoder (a new random RTP timestamp base per step). Run: python3 test_step_jitter.py"""

from step_jitter import residual_stats

MS = 1_000_000


def test_a_constant_offset_cancels_and_a_tail_shows():
    # 100 frames: latency 5 ms plus an unknown per-step constant of -80 s; 5 frames wait 6 ms longer (FEC recovery)
    lat = [-80_000 * MS + 5 * MS] * 95 + [-80_000 * MS + 11 * MS] * 5
    s = residual_stats(lat)
    assert s["p50"] == 0.0 and s["max"] == 6.0, s
    assert s["p99"] == 6.0 and s["p95"] <= 6.0, s


def test_too_few_frames_gives_nothing():
    assert residual_stats([1, 2, 3]) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
