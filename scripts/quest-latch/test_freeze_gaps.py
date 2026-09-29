"""Offline checks of freeze_gaps.classify: each gap between decoded frames above the stall threshold is a real link gap
(no packets), a freeze until the IDR (packets arrive and frozen slices rise), or packets without frames.
Run: python3 test_freeze_gaps.py"""

from freeze_gaps import classify, summary

MS = 1_000_000


def frames(start_ms, end_ms, step_ms=11):
    return [t * MS for t in range(start_ms, end_ms, step_ms)]


def packets(start_ms, end_ms, seq0, every_ms=1, skip=()):
    out, seq = [], seq0
    for t in range(start_ms, end_ms, every_ms):
        if seq not in skip:
            out.append((t * MS, seq & 0xFFFF))
        seq += 1
    return out, seq


def test_a_gap_without_packets_is_a_link_gap():
    ready = frames(0, 1000) + frames(1400, 2000)
    p1, s = packets(0, 1000, 100)
    p2, _ = packets(1400, 2000, s + 50)        # 50 packets never arrived, none in the gap
    g = classify(ready, p1 + p2, [], [], [], 250 * MS)
    assert len(g) == 1 and g[0]["kind"] == "no packets", g
    assert 380 <= g[0]["ms"] <= 420, g


def test_a_gap_with_packets_and_rising_frozen_slices_is_a_freeze():
    ready = frames(0, 1000) + frames(1300, 2000)
    p, _ = packets(0, 2000, 100, skip={1100})  # one packet lost at ~1000 ms, packets keep coming
    frozen = [(1010 * MS, 1), (1050 * MS, 5), (1290 * MS, 26)]
    idr_ok = [(1015 * MS, 1), (1220 * MS, 2)]
    g = classify(ready, p, frozen, idr_ok, [], 250 * MS)
    assert len(g) == 1, g
    assert g[0]["kind"] == "freeze", g
    assert g[0]["frozen"] == 26 and g[0]["idr_ok"] == 2 and g[0]["lost"] == 1, g


def test_packets_without_frames_and_no_freeze_is_a_decoder_gap():
    ready = frames(0, 1000) + frames(1300, 2000)
    p, _ = packets(0, 2000, 100)
    g = classify(ready, p, [], [], [], 250 * MS)
    assert len(g) == 1 and g[0]["kind"] == "packets, no frames", g


def test_short_gaps_are_not_stalls_and_the_summary_counts_kinds():
    ready = frames(0, 1000) + frames(1100, 2000)   # 100 ms gap < 250 ms
    p, _ = packets(0, 2000, 100)
    g = classify(ready, p, [], [], [], 250 * MS)
    assert g == []
    s = summary(g, 2.0)
    assert s["stalls"] == 0 and s["per_min"] == 0.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
