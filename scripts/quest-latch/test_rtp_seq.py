"""Offline check of the RTP loss count (rtp_seq.py, used by transport_analyze.py and ab_segments.py).
Run: python3 test_rtp_seq.py"""
from rtp_seq import codec_segments, seq_loss


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


def test_codec_segments_names_each_run_of_one_payload_type():
    # ppxr_rtp_pt, one sample per frame: H.264 (96), a live switch to H.265 (97), and back
    samples = [(0, 96), (1, 96), (2, 97), (3, 97), (4, 97), (5, 96)]
    assert codec_segments(samples) == [("H.264", 0, 1, 2), ("H.265", 2, 4, 3), ("H.264", 5, 5, 1)]


def test_codec_segments_unknown_type_and_empty():
    assert codec_segments([]) == []
    assert codec_segments([(7, 33)]) == [("pt33", 7, 7, 1)]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
