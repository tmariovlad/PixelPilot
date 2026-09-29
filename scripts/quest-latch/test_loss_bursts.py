"""Offline checks of loss_bursts: RTP holes after FEC as runs (length in packets, duration in ms), their histogram,
and the phase lock of the run starts to the 102.4 ms beacon period. Run: python3 test_loss_bursts.py"""

from loss_bursts import histogram, runs
from tu_pause import TU_PERIOD_S, rayleigh_z

MS = 1_000_000


def stream(n, every_ms=1.0, drop=()):
    """Packets every every_ms with 16-bit sequence numbers; drop = sequence numbers never received."""
    return [(int(i * every_ms * MS), i & 0xFFFF) for i in range(n) if i not in drop]


def test_a_run_has_its_length_and_the_time_it_spans():
    r = runs(stream(100, drop={10, 11, 12}))
    assert len(r) == 1
    start_ns, length, ms = r[0]
    assert length == 3 and start_ns == 9 * MS and abs(ms - 4.0) < 1e-9, r[0]


def test_sequence_wrap_is_not_a_run_and_separate_holes_are_separate_runs():
    pk = [(i * MS, (65530 + i) & 0xFFFF) for i in range(20)]
    assert runs(pk) == []
    r = runs(stream(100, drop={20, 50, 51}))
    assert [x[1] for x in r] == [1, 2]


def test_histogram_bins_by_length():
    h = histogram([(0, 1, 2.0), (0, 1, 2.0), (0, 3, 4.0), (0, 6, 7.0), (0, 12, 13.0)])
    assert h == {"1": 2, "2": 0, "3": 1, "4": 0, "5-8": 1, "9+": 1}, h


def test_runs_locked_to_the_beacon_period_show_a_high_rayleigh_z():
    drops = set()
    for k in range(100):                      # a 3-packet burst every 102.4 ms at 1 packet/ms
        s = int(k * TU_PERIOD_S * 1000)
        drops |= {s, s + 1, s + 2}
    r = runs(stream(10300, drop=drops))
    z = rayleigh_z([x[0] for x in r], TU_PERIOD_S)
    assert len(r) >= 95 and z > 50, (len(r), z)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
