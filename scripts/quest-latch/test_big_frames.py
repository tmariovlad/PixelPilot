"""Offline checks of big_frames: latency of the largest frames (scene changes such as the G2G rig's LED flash, and IDR
frames) apart from the rest, on the baseline's drift line. Run: python3 test_big_frames.py"""

from ab_segments import Frame
from big_frames import split_stats

MS = 1_000_000


def frame(capture_ms, last_ms, npkts):
    return Frame(capture_ms * MS, last_ms * MS, last_ms * MS, npkts, None)


def test_big_frames_are_split_off_by_packet_count_and_measured_on_the_line():
    line = lambda t: -100 * MS                      # capture is 100 ms ahead of arrival on the drift line
    fs = [frame(1000 + i, 1000 + i - 100 + 4, 16) for i in range(20)]      # 4 ms above the line
    fs += [frame(2000, 2000 - 100 + 40, 60), frame(3000, 3000 - 100 + 60, 50)]
    big, rest = split_stats(fs, line, threshold=32)
    assert big["n"] == 2 and big["pkts"] == 55 and big["last"] == 50.0 and big["max"] == 60.0, big
    assert rest["n"] == 20 and rest["last"] == 4.0 and rest["p95"] == 4.0, rest


def test_no_big_frames_gives_none():
    big, rest = split_stats([frame(i, i + 1, 10) for i in range(5)], lambda t: 0, threshold=32)
    assert big is None and rest["n"] == 5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
