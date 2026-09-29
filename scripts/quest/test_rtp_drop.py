"""Checks of rtp_drop.drops: which packets a replay leaves out (DROP= of rtp_play.py), for deterministic-loss tests
such as the GDR heal time (OpenIPC O118 S0, T3). Run: python3 test_rtp_drop.py"""

from rtp_drop import drops


def test_no_spec_drops_nothing():
    assert drops("", [0.0, 0.1, 0.2]) == set()


def test_explicit_indices():
    assert drops("1,4", [i / 10 for i in range(6)]) == {1, 4}


def test_k_packets_every_period_start_at_the_first_packet_at_or_after_each_boundary():
    times = [i * 0.1 for i in range(35)]          # 3.5 s at 10 packets/s
    # boundaries at 1.0, 2.0, 3.0 s -> packets 10, 20, 30 and the next one each
    assert drops("2@1.0", times) == {10, 11, 20, 21, 30, 31}


def test_boundaries_do_not_drift_with_float_sums():
    # 0.05 + 0.05 + 0.05 > 0.15 in floats: the third run must still start at the packet sent at 0.15 s
    assert drops("2@0.05", [i * 0.01 for i in range(20)]) == {5, 6, 10, 11, 15, 16}


def test_a_run_never_runs_past_the_end():
    assert drops("5@1.0", [0.0, 0.5, 1.0, 1.1]) == {2, 3}


def test_bad_specs_are_rejected():
    for bad in ("x", "2@", "@1", "0@1", "2@0"):
        try:
            drops(bad, [0.0, 1.0])
        except ValueError:
            continue
        raise AssertionError("accepted " + bad)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
