"""Offline checks of frame_fate.classify on synthetic RTP arrivals: each class (decoded, hole, edge, complete-not-decoded,
never arrived) and a sequence-number wrap. Run: python3 test_frame_fate.py"""

from frame_fate import classify

MS = 1_000_000
TS_STEP = 1000          # 90 kHz RTP clock at 90 fps


def synth(n_frames=12, pkts=3, seq0=100, drop_seqs=(), skip_frames=(), no_ready=()):
    """Frame k: `pkts` packets 1 ms apart starting at k*11 ms, RTP ts k*TS_STEP; a ready mark 2 ms after its last
    packet unless one of its packets was lost (the app drops such a frame). drop_seqs: sequence numbers lost; skip_frames: frames that never arrive (their seqs are not used either,
    as when the air never sent them); no_ready: frames that arrive but are not decoded."""
    pk, ready, seq = [], [], seq0
    for k in range(n_frames):
        if k in skip_frames:
            continue
        last, lost = None, False
        for j in range(pkts):
            t = k * 11 * MS + j * MS
            if seq % 0x10000 not in drop_seqs:
                pk.append((t, seq % 0x10000, k * TS_STEP))
                last = t
            else:
                lost = True
            seq += 1
        if last is not None and not lost and k not in no_ready:     # the app drops a frame that lost a packet
            ready.append(last + 2 * MS)
    return pk, sorted(ready)


def run(pk, ready):
    return classify(pk, ready, 90, 0, 10**12)


def test_all_complete_and_decoded():
    r = run(*synth())
    assert r == {"decoded": 12, "hole": 0, "edge": 0, "not_decoded": 0, "never": 0}, r


def test_a_packet_missing_inside_a_frame_is_a_hole():
    r = run(*synth(drop_seqs={100 + 4 * 3 + 1}))       # middle packet of frame 4
    assert r["hole"] == 1 and r["decoded"] == 11, r


def test_a_gap_between_two_frames_is_one_edge():
    r = run(*synth(drop_seqs={100 + 5 * 3}))           # first packet of frame 5 = right after frame 4's last
    assert r["edge"] == 1 and r["hole"] == 0 and r["decoded"] == 11, r


def test_complete_without_a_ready_mark_is_not_decoded():
    r = run(*synth(no_ready={7}))
    assert r["not_decoded"] == 1 and r["decoded"] == 11, r


def test_a_frame_that_never_arrived_is_counted_on_the_ts_grid():
    r = run(*synth(skip_frames={6}))
    assert r["never"] == 1 and r["decoded"] == 11 and r["edge"] == 0, r


def test_sequence_wrap_is_not_a_gap():
    r = run(*synth(seq0=0xFFFF - 10))
    assert r == {"decoded": 12, "hole": 0, "edge": 0, "not_decoded": 0, "never": 0}, r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
