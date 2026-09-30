"""Live vs offline one-way delay on the same capture: does the app's queue signal equal the reference?

Usage: python3 owd_crosscheck.py trace.pftrace capture.txt [--window-s 2] [--top 5]

The app prints, every stats tick, the p50/p95 over the last stats window (StatsCollector.WINDOW_US = 2 s) of its
relative one-way delay (OwdWindow: LiveBase over each decoded frame's first-packet arrival - RTP ts), for the 60 s base
(owd50/owd95) and the unbounded, rate-control base (owdu50/owdu95), plus the learnt drift (owdd); t = CLOCK_MONOTONIC ms
(PPXR_STATS, docs/xr/stats-backend.md §7.3). This script recomputes the same numbers from the Perfetto trace of the same
capture with the reference owd.LiveBase: per frame, the first packet's raw arrival (ppxr_rtp_seq/ts counters) - RTP ts,
only frames the app decoded (ab_segments frames with a decoded mark), the same window and Segment's percentile
interpolation. The trace clock is BOOTTIME; its clock snapshot gives MONOTONIC - BOOTTIME.

Reading it: differences ~0 = the app's signal is the reference. A difference that appears with loss and not without is
the reorder-queue hold on the first-packet stamp (builds before rawfirst, xr-native 15a7c83, stamp after the queue: ce70daa4). A drift gap
(owdd) points at the drift learning.
"""
import argparse

import owd
from stats_log import parse_kv

TAG = " PPXR_STATS: "
KEYS = ("owd50", "owd95", "owdu50", "owdu95", "owdd")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_stats(lines):
    """[{t_ms, owd50, owd95, owdu50, owdu95, owdd}] ("-" -> None)."""
    out = []
    for line in lines:
        i = line.find(TAG)
        if i < 0:
            continue
        kv = parse_kv(line[i + len(TAG):])
        if "t" not in kv:
            continue
        out.append({"t_ms": int(kv["t"]), **{k: _num(kv.get(k)) for k in KEYS}})
    return out


def quantile(sorted_v, q):
    """The app's Segment.quantile: linear between order statistics at q * (n - 1)."""
    if not sorted_v:
        return None
    pos = q * (len(sorted_v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_v) - 1)
    return sorted_v[lo] + (pos - lo) * (sorted_v[hi] - sorted_v[lo])


def compare(stats, t_ns, rel60, relinf, drift, mono_minus_trace_ns, window_ns):
    """Per stats line: the offline values over the same window (frames with t in (T - window, T], T on the trace clock)
    and d_<key> = app - offline (None when either side has nothing)."""
    from bisect import bisect_right
    out = []
    for row in stats:
        end = row["t_ms"] * 1e6 - mono_minus_trace_ns
        i, j = bisect_right(t_ns, end - window_ns), bisect_right(t_ns, end)
        w60, winf = sorted(rel60[i:j]), sorted(relinf[i:j])
        off = {"owd50": quantile(w60, 0.5), "owd95": quantile(w60, 0.95), "owdu50": quantile(winf, 0.5),
               "owdu95": quantile(winf, 0.95), "owdd": drift[j - 1] if j > 0 else None}
        r = {"t_ms": row["t_ms"], "n": j - i}
        for k in KEYS:
            r["app_" + k], r["off_" + k] = row[k], off[k]
            r["d_" + k] = row[k] - off[k] if row[k] is not None and off[k] is not None else None
        out.append(r)
    return out


def summarize(rows):
    """Per key: windows compared, median / p95 / max |difference|, and the share within 0.5 ms."""
    out = {}
    for k in KEYS:
        d = sorted(abs(r["d_" + k]) for r in rows if r.get("d_" + k) is not None)
        if d:
            out[k] = {"n": len(d), "median_abs": quantile(d, 0.5), "p95_abs": quantile(d, 0.95), "max_abs": d[-1],
                      "within_0.5ms": sum(1 for x in d if x <= 0.5) / len(d)}
    return out


def offline(trace):
    """(t_ns, rel60, relinf, drift, mono_minus_trace_ns) for the decoded frames of a trace."""
    from ab_segments import frames_from_packets, load_trace
    from perfetto.trace_processor import TraceProcessor
    pkts, ready, _ = load_trace(trace)
    frames, _ = frames_from_packets(pkts, ready)
    rows = owd.per_frame([f for f in frames if f.ready is not None])   # only frames the app decoded
    t = [r["t"] for r in rows]
    v = [r["first"] for r in rows]
    b60, binf = owd.LiveBase(window_s=60.0), owd.LiveBase(window_s=float("inf"))
    rel60, relinf, drift = [], [], []
    for x, y in zip(t, v):
        rel60.append(b60.push(x, y))
        relinf.append(binf.push(x, y))
        drift.append(binf.d)
    tp = TraceProcessor(trace=trace)
    snap = list(tp.query("select clock_value, ts from clock_snapshot where clock_name='MONOTONIC' order by ts limit 1"))
    if not snap:
        raise SystemExit("trace has no MONOTONIC clock snapshot")
    return t, rel60, relinf, drift, snap[0].clock_value - snap[0].ts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("capture")
    ap.add_argument("--window-s", type=float, default=2.0)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    with open(a.capture, encoding="utf-8", errors="replace") as fh:
        stats = [r for r in parse_stats(fh) if any(r[k] is not None for k in KEYS)]
    if not stats:
        raise SystemExit("no PPXR_STATS lines with owd fields (an APK before ce70daa4?)")
    t, rel60, relinf, drift, mono_off = offline(a.trace)
    rows = compare(stats, t, rel60, relinf, drift, mono_off, a.window_s * 1e9)
    print(f"{a.trace}: {len(t)} decoded frames; {len(stats)} stats lines; MONOTONIC - trace clock {mono_off / 1e6:.3f} ms")
    print(f"{'key':7s} {'windows':>7s} {'med|d|':>8s} {'p95|d|':>8s} {'max|d|':>8s} {'<=0.5ms':>8s}")
    for k, s in summarize(rows).items():
        print(f"{k:7s} {s['n']:7d} {s['median_abs']:8.3f} {s['p95_abs']:8.3f} {s['max_abs']:8.3f} "
              f"{s['within_0.5ms']:8.1%}")
    worst = sorted((r for r in rows if r["d_owdu95"] is not None), key=lambda r: -abs(r["d_owdu95"]))[:a.top]
    if worst:
        print(f"largest owdu95 differences (app - offline, ms): t_ms n app off")
        for r in worst:
            print(f"  {r['t_ms']} n={r['n']} {r['app_owdu95']:.2f} {r['off_owdu95']:.2f} d={r['d_owdu95']:+.2f}")


if __name__ == "__main__":
    main()
