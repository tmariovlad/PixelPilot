"""Offline checks of gap_hold.py (no perfetto needed). Run: python3 test_gap_hold.py"""
from gap_hold import frame_delays, loss_text, packet_loss, summary

MS = 1_000_000


def test_frames_after_a_gap_are_flagged_within_the_hold_window():
    # one packet per frame, 5 ms apart; seq 3 is lost
    seqs = [1, 2, 4, 5, 6, 7, 8, 9, 10, 11]
    pkts = [(i * 5 * MS, s, 1000 * i) for i, s in enumerate(seqs)]
    ready = [t + 2 * MS for t, _, _ in pkts]
    d, gaps = frame_delays(pkts, ready, hold_pkts=3)
    assert gaps == 1
    flags = [a for _, _, a in d]
    assert flags == [False, False, True, True, True, False, False, False, False, False]
    assert all(abs(x - 2.0) < 1e-9 for _, x, _ in d)


def test_multi_packet_frame_uses_its_last_packet_and_wrap_is_not_a_gap():
    pkts = [(0, 65534, 10), (1 * MS, 65535, 10), (2 * MS, 0, 20), (3 * MS, 1, 20)]
    ready = [2 * MS, 9 * MS]
    d, gaps = frame_delays(pkts, ready)
    assert gaps == 0
    assert [round(x, 3) for _, x, _ in d] == [1.0, 6.0]


def test_frame_without_a_decoded_mark_is_skipped_and_summary_reads():
    pkts = [(0, 1, 10), (5 * MS, 2, 20)]
    d, _ = frame_delays(pkts, [1 * MS])  # only the first frame decoded
    assert len(d) == 1
    assert "after-gap frames   0" in summary("x", d, 0)


def test_packet_loss_counts_gaps_per_window_and_skips_guards():
    pkts = [(t * MS, s, 0) for t, s in enumerate([1, 2, 4, 5, 9, 10, 11])]
    windows = {1: "a", 2: "a", 3: "a", 4: "b", 5: None, 6: "b"}   # arrival ms -> window
    loss = packet_loss(pkts, lambda t: windows.get(t // MS))
    assert loss == {"a": (3, 1), "b": (2, 3)}   # 2->4 lost 1 in a; 5->9 lost 3 in b; the guard sample is not counted
    assert loss_text(*loss["a"]) == "loss 25.00 % (1/4)"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
