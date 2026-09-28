"""Transport analysis of a real link from a Perfetto trace of the XR app.

Needs the app's per-packet counters 'ppxr_rtp_seq' / 'ppxr_rtp_ts' (VideoPlayer::onNewRTPData, set only
while tracing) and the 'ppxr_frame_ready' slices. The air unit's RTP timestamp is its capture clock
(90 kHz), so arrival - rtp_ts is the transport delay up to an unknown constant; after removing the
air/headset clock drift, its excess over the best frame shows how much each frame is held back
(bursting, loss recovery, USB batching).

Usage: python3 transport_analyze.py trace.pftrace
"""
import statistics as st
import sys
from bisect import bisect_left
from collections import OrderedDict

from perfetto.trace_processor import TraceProcessor

from rtp_seq import codec_segments, seq_loss


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


def summ(name, v, unit=1e6):
    if not v:
        print(f"{name:46s} none")
        return
    print(f"{name:46s} n={len(v):5d} mean={st.mean(v)/unit:6.2f} p5={pct(v,.05)/unit:6.2f} p50={pct(v,.5)/unit:6.2f} "
          f"p95={pct(v,.95)/unit:6.2f} max={max(v)/unit:6.2f} ms")


def main(path):
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    cnt = lambda name: [(r.ts, int(r.value)) for r in q(
        f"select c.ts, c.value from counter c join counter_track t on c.track_id=t.id where t.name='{name}' order by c.ts")]
    seqs, tss = cnt("ppxr_rtp_seq"), cnt("ppxr_rtp_ts")
    if not seqs or len(seqs) != len(tss):
        sys.exit(f"missing/unpaired RTP counters: seq={len(seqs)} ts={len(tss)}")
    pkts = [(a[0], a[1], b[1]) for a, b in zip(seqs, tss)]  # (arrival_ns, seq, rtp_ts)
    span = (pkts[-1][0] - pkts[0][0]) / 1e9

    gaps, reorders = seq_loss([p[1] for p in pkts])

    # group packets into frames by RTP timestamp (unwrapped)
    frames, base, prev = OrderedDict(), 0, None
    for t, s, ts in pkts:
        if prev is not None and ts < prev and prev - ts > 1 << 31:
            base += 1 << 32
        prev = ts
        frames.setdefault(base + ts, []).append(t)
    fr = [(k, v[0], v[-1], len(v)) for k, v in frames.items()]
    # which codec the segment carried (ppxr_rtp_pt, one sample per frame; builds with live codec switching)
    runs = codec_segments(cnt("ppxr_rtp_pt"))
    if runs:
        print("codec: " + ", ".join(f"{n} {k} frames ({(b - a) / 1e9:.1f} s)" for n, a, b, k in runs))
    print(f"{len(pkts)} packets / {len(fr)} frames in {span:.1f}s = {len(fr)/span:.1f} fps, {len(pkts)/len(fr):.2f} pkt/frame; "
          f"sequence gaps (lost before the app) = {gaps}, reordered = {reorders}")
    summ("frame packet spread (first -> last packet)", [f[2] - f[1] for f in fr if f[3] > 1])

    # transport-delay excess: d = arrival - capture clock; remove the linear clock drift fitted on the
    # lower envelope (5th percentile per 1 s window), then report the excess over the best frame.
    def excess(idx):
        d = [(f[idx], f[idx] - f[0] * 1e9 / 90000) for f in fr]
        t0 = d[0][0]
        wins = {}
        for t, v in d:
            wins.setdefault(int((t - t0) // 1e9), []).append(v)
        pts = [(k + 0.5, pct(v, .05)) for k, v in sorted(wins.items()) if len(v) > 20]
        if len(pts) >= 2:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            mx, my = st.mean(xs), st.mean(ys)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        else:
            slope = 0.0
        r = [v - slope * (t - t0) / 1e9 for t, v in d]
        m = min(r)
        return [x - m for x in r], slope


    ex_last, slope = excess(2)
    print(f"air/headset clock drift removed: {slope/1e3:+.1f} us/s ({slope/1e3:+.0f} ppm)")
    summ("transport excess, frame complete (last pkt)", ex_last)
    summ("transport excess, first packet", excess(1)[0])

    # Quest side: frame complete -> frame ready (decoder output), nearest following ready mark
    ready = [r.ts for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
    d = []
    for _, _, last, _ in fr:
        i = bisect_left(ready, last)
        if i < len(ready) and ready[i] - last < 20e6:
            d.append(ready[i] - last)
    summ("frame complete -> decoded frame ready", d)


if __name__ == "__main__":
    main(sys.argv[1])
