"""RTP sequence-number helpers shared by the Perfetto transport analyses (transport_analyze.py,
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
