"""Frames right after an RTP sequence gap vs all other frames: frame complete (last packet) -> decoded.

The app's BufferedPacketQueue (app/videonative/src/main/cpp/BufferedPacketQueue.h) holds packets after a sequence
gap until 5 in-order packets arrive or 20 ms pass (checked on the next arrival), in case the gap is a reorder. This
shows what that hold costs on a real link, from existing Perfetto traces (mode_segment.sh / compositor.pbtx):
frames whose last packet arrived within HOLD_PKTS packets after a gap are "after-gap".

Usage: python3 gap_hold.py out/mode_*.pftrace
"""
import sys, statistics as st
from bisect import bisect_left
from collections import OrderedDict
from perfetto.trace_processor import TraceProcessor

HOLD_PKTS = 6  # MONOTONIC_THRESHOLD 5 + the gap packet

def analyse(path):
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    cnt = lambda n: [(r.ts, int(r.value)) for r in q(
        f"select c.ts, c.value from counter c join counter_track t on c.track_id=t.id where t.name='{n}' order by c.ts")]
    seqs, tss = cnt("ppxr_rtp_seq"), cnt("ppxr_rtp_ts")
    pk = [(a[0], a[1], b[1]) for a, b in zip(seqs, tss)]
    gap_after = set()  # arrival indices within the hold window after a gap
    gaps = 0
    for i in range(1, len(pk)):
        step = ((pk[i][1] - pk[i-1][1] + 0x8000) & 0xFFFF) - 0x8000
        if step > 1:
            gaps += 1
            for j in range(i, min(len(pk), i + HOLD_PKTS)):
                gap_after.add(j)
    frames = OrderedDict()
    for i, (t, s, ts) in enumerate(pk):
        frames.setdefault(ts, []).append((t, i))
    ready = [r.ts for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
    held, clean = [], []
    for v in frames.values():
        last_t, last_i = v[-1]
        k = bisect_left(ready, last_t)
        if k < len(ready) and ready[k] - last_t < 40e6:
            (held if last_i in gap_after else clean).append((ready[k] - last_t) / 1e6)
    tp.close()
    return gaps, held, clean

for p in sys.argv[1:]:
    g, h, c = analyse(p)
    hm = f"{st.mean(h):6.2f}" if h else "   n/a"
    print(f"{p.split('/')[-1]:24s} gaps {g:3d}  after-gap frames {len(h):3d} mean {hm} ms | other {len(c):4d} mean {st.mean(c):5.2f} ms"
          f" | share of all frame delay from held frames: {100*sum(h)/(sum(h)+sum(c)) if h else 0:4.1f} %  "
          f"| mean over all {st.mean(h+c):5.2f}")
