"""Offline check of switch_gap.find_switch_gaps. Run: python3 test_switch_gap.py"""
from switch_gap import find_switch_gaps

MS = 1_000_000


def frames(start_ms, n, step_ms=11):
    return [int((start_ms + i * step_ms) * MS) for i in range(n)]


def test_no_gap_on_a_steady_stream():
    assert find_switch_gaps(frames(0, 100), frames(0, 100), 500 * MS) == []


def test_switch_splits_stream_and_decoder_parts():
    old = frames(0, 50)                       # last frame at 539 ms
    new = frames(20_000, 50)                  # the new stream's first frame decodes at 20 000 ms
    rtp_old = frames(0, 50)
    rtp_new = frames(19_950, 50)              # its first packet arrives at 19 950 ms
    (last, first_rtp, first_frame), = find_switch_gaps(old + new, rtp_old + rtp_new, 500 * MS)
    assert last == old[-1]
    assert first_rtp == rtp_new[0]
    assert first_frame == new[0]
    assert (first_frame - first_rtp) == 50 * MS          # the decoder's part


def test_old_stream_tail_is_not_taken_for_the_new_stream():
    old = frames(0, 50)
    tail = [old[-1] + 5 * MS, old[-1] + 9 * MS]           # packets of the old stream still arriving
    rtp_new = frames(10_000, 10)
    (_, first_rtp, _), = find_switch_gaps(old + frames(10_030, 10), old + tail + rtp_new, 500 * MS)
    assert first_rtp == rtp_new[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
