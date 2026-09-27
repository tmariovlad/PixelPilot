"""Offline check of ab_timeline: per-second buckets on the REALTIME clock. Run: python3 test_ab_timeline.py"""
from ab_timeline import per_second, rows

S = 1e9
OFF = 1_000 * S  # trace clock + OFF = realtime


def test_per_second_count_sum_mean():
    series = [(0.1 * S, 2), (0.9 * S, 4), (1.5 * S, 6)]
    assert per_second(series, OFF, "count") == {1000: 2, 1001: 1}
    assert per_second(series, OFF, "sum") == {1000: 6, 1001: 6}
    assert per_second(series, OFF, "mean") == {1000: 3.0, 1001: 6.0}


def test_rows_fill_gaps_with_none():
    rtp = [(0.5 * S, 1), (2.5 * S, 1), (2.6 * S, 1)]  # nothing in second 1001: a dead link
    out = dict(rows(rtp, [], {}, OFF))
    assert out[1000]["rtp"] == 1
    assert out[1001]["rtp"] is None
    assert out[1002]["rtp"] == 2
    assert out[1002]["wfb_rx"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
