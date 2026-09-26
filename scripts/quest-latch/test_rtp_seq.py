"""Offline check of the RTP loss count (rtp_seq.py, used by transport_analyze.py and ab_segments.py).
Run: python3 test_rtp_seq.py"""
from rtp_seq import seq_loss


def test_in_order():
    assert seq_loss([10, 11, 12, 13]) == (0, 0)


def test_gap():
    assert seq_loss([10, 11, 15, 16]) == (3, 0)


def test_reorder_is_not_a_wrap():
    # the real-link case of 2026-09-27: one late packet, nothing lost
    assert seq_loss([7575, 7577, 7576, 7578]) == (0, 1)


def test_wrap():
    assert seq_loss([65534, 65535, 0, 1]) == (0, 0)
    assert seq_loss([65534, 1]) == (2, 0)


def test_reorder_across_wrap():
    assert seq_loss([65535, 1, 0, 2]) == (0, 1)


def test_duplicate():
    assert seq_loss([5, 6, 6, 7]) == (0, 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
