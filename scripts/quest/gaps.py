"""Packet inter-arrival gaps (within a frame vs at frame boundaries) and burstiness from the app's
per-packet counters ppxr_rtp_seq / ppxr_rtp_ts in a Perfetto trace (see ../quest-latch/transport_analyze.py
for the full transport-delay analysis).
Usage: python3 gaps.py trace.pftrace      Needs: pip install perfetto"""
import sys
from collections import Counter
from perfetto.trace_processor import TraceProcessor
tp = TraceProcessor(trace=sys.argv[1]); q = lambda s: list(tp.query(s))
c = lambda n: [(r.ts, int(r.value)) for r in q(f"select c.ts, c.value from counter c join counter_track t on c.track_id=t.id where t.name='{n}' order by c.ts")]
p = [(a[0], b[1]) for a, b in zip(c("ppxr_rtp_seq"), c("ppxr_rtp_ts"))]
g = [(b[0] - a[0]) / 1e3 for a, b in zip(p, p[1:])]           # us between consecutive packets
same = [x for (a, b), x in zip(zip(p, p[1:]), g) if a[1] == b[1]]  # within a frame
cross = [x for (a, b), x in zip(zip(p, p[1:]), g) if a[1] != b[1]]  # frame boundary
bins = [0, 50, 100, 250, 500, 1000, 2000, 4000, 8000, 1e9]
def hist(v):
    h = Counter(next(f"{bins[i]:.0f}-{bins[i+1]:.0f}" for i in range(len(bins)-1) if bins[i] <= x < bins[i+1]) for x in v)
    return "  ".join(f"{k}us:{h[k]}" for k in [f"{bins[i]:.0f}-{bins[i+1]:.0f}" for i in range(len(bins)-1)] if h[k])
print("within-frame gaps :", hist(same)); print("frame-boundary gaps:", hist(cross))
# burstiness: packets arriving < 100 us after the previous one
print(f"share of packets arriving <100us after the previous: {100*sum(x < 100 for x in g)/len(g):.1f}%")
# first 3 frames' packet timelines relative to first packet
seen = []
for t, ts in p:
    if not seen or seen[-1][0] != ts: seen.append((ts, []))
    seen[-1][1].append(t)
for ts, ts_list in seen[200:206]:
    print("frame", [round((x - ts_list[0]) / 1e3) for x in ts_list], "us")
