"""RTP sequence-number and payload-type helpers shared by the Perfetto transport analyses (transport_analyze.py,
ab_segments.py). No dependencies, so the offline tests run without perfetto."""


def seq_loss(seqs):
    """(lost, reordered) for 16-bit RTP sequence numbers in arrival order. Each number is unwrapped
    against the previous one with a signed step, so a late packet is a reorder that fills its own hole,
    not a ~65535-packet gap (seen on the real link 2026-09-27: 7575, 7577, 7576)."""
    if not seqs:
        return 0, 0
    useq, reorders = [seqs[0]], 0
    for a, b in zip(seqs, seqs[1:]):
        step = ((b - a + 0x8000) & 0xFFFF) - 0x8000   # signed 16-bit difference
        reorders += step < 0
        useq.append(useq[-1] + step)
    return max(useq) - min(useq) + 1 - len(set(useq)), reorders


CODEC_NAMES = {96: "H.264", 97: "H.265"}   # RTP payload types from waybeam (H26XParser::parse_rtp_stream)


def codec_segments(samples):
    """Runs of one codec from the app's 'ppxr_rtp_pt' counter ([(ts, payload_type)], one sample per frame, in time
    order): [(name, first_ts, last_ts, frames)]. A live H.264 <-> H.265 switch (CodecSwitch.h) starts a new run."""
    runs = []
    for ts, pt in samples:
        name = CODEC_NAMES.get(pt, f"pt{pt}")
        if runs and runs[-1][0] == name:
            runs[-1] = (name, runs[-1][1], ts, runs[-1][3] + 1)
        else:
            runs.append((name, ts, ts, 1))
    return runs
