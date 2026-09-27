"""Per-second timeline of one trace of the XR app, on the Quest REALTIME clock (epoch seconds): RTP packets received,
frames decoded (ppxr_frame_ready), wfb-ng packets received / lost after FEC, and mean RSSI. Shows transients that the
per-step tables of ab_segments.py / ab_link.py average away: a link dying at a power switch, how long an adaptive link
takes to settle after a drop.

Usage: python3 ab_timeline.py trace.pftrace [from_epoch] [to_epoch] [--csv out.csv]
"""
import argparse
import csv
from collections import defaultdict

from ab_link import WFB_COUNTERS, drop_stale


def per_second(series, rt_off, reduce):
    """series [(trace_ns, value)] -> {epoch second: reduce(values)}; reduce 'count', 'sum' or 'mean'."""
    buckets = defaultdict(list)
    for t, v in series:
        buckets[int((t + rt_off) / 1e9)].append(v)
    op = {"count": len, "sum": sum, "mean": lambda xs: sum(xs) / len(xs)}[reduce]
    return {s: op(vs) for s, vs in buckets.items()}


def rows(rtp, ready, counters, rt_off, lo=None, hi=None):
    cols = {
        "rtp": per_second(rtp, rt_off, "count"),
        "decoded": per_second(ready, rt_off, "count"),
        "wfb_rx": per_second(counters.get("ppxr_wfb_p_all", []), rt_off, "sum"),
        "wfb_lost": per_second(counters.get("ppxr_wfb_lost", []), rt_off, "sum"),
        "rssi": per_second(counters.get("ppxr_wfb_rssi", []), rt_off, "mean"),
    }
    secs = sorted(set().union(*(c.keys() for c in cols.values())))
    lo = secs[0] if lo is None else lo
    hi = secs[-1] if hi is None else hi
    return [(s, {k: c.get(s) for k, c in cols.items()}) for s in range(lo, hi + 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("lo", nargs="?", type=int)
    ap.add_argument("hi", nargs="?", type=int)
    ap.add_argument("--csv")
    a = ap.parse_args()
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=a.trace)
    q = lambda s: list(tp.query(s))
    cnt = lambda n: [(r.ts, r.value) for r in q(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        f"where t.name='{n}' order by c.ts")]
    snap = q("select ts, clock_value from clock_snapshot where clock_name='REALTIME' order by ts limit 1")[0]
    rt_off = snap.clock_value - snap.ts
    rtp = cnt("ppxr_rtp_seq")
    ready = [(r.ts, 1) for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
    counters = drop_stale({n: cnt(n) for n in WFB_COUNTERS}, [t for t, _ in rtp])
    out = rows(rtp, ready, counters, rt_off, a.lo, a.hi)
    keys = ["rtp", "decoded", "wfb_rx", "wfb_lost", "rssi"]
    print("epoch        " + "".join(f"{k:>9s}" for k in keys))
    for s, r in out:
        print(f"{s} " + "".join(f"{'-':>9}" if r[k] is None else f"{r[k]:9.1f}" for k in keys))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["epoch"] + keys)
            for s, r in out:
                vals = [r[k] for k in keys]
                w.writerow([s] + ["" if v is None else round(v, 2) for v in vals])


if __name__ == "__main__":
    main()
