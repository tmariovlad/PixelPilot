"""Offline checks of latency_bins: capture -> last-packet latency on a drift line, in time bins within each step, and
its slope (does a queue build up during a step?). Run: python3 test_latency_bins.py"""

from ab_segments import Frame
from latency_bins import bins_and_slope

MS = 1_000_000
S = 1_000_000_000


def frame(t_s, lat_ms):
    """A frame whose last packet arrives at t_s, lat_ms above a zero drift line (capture = arrival - latency)."""
    last = int(t_s * S)
    return Frame(last - int(lat_ms * MS), last - 2 * MS, last, 16, None)


def test_a_queue_that_grows_shows_rising_bins_and_a_positive_slope():
    # 40 s at 10 fps; latency grows 0.5 ms per second from 5 ms
    fs = [frame(100 + i / 10, 5 + 0.5 * (i / 10)) for i in range(400)]
    bins, slope = bins_and_slope(fs, lambda t: 0, lo_ns=100 * S, hi_ns=140 * S, bin_s=10)
    assert [round(b, 1) for b in bins] == [7.5, 12.5, 17.5, 22.5], bins
    assert abs(slope - 0.5) < 1e-6, slope


def test_a_flat_step_has_flat_bins_and_no_slope():
    fs = [frame(100 + i / 10, 5.0) for i in range(300)]
    bins, slope = bins_and_slope(fs, lambda t: 0, lo_ns=100 * S, hi_ns=130 * S, bin_s=10)
    assert bins == [5.0, 5.0, 5.0] and abs(slope) < 1e-9, (bins, slope)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
