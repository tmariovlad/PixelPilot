"""Latency over time within each step: capture -> last packet, in ms above the baseline state's drift line
(ab_segments.py), averaged in bins of --bin-s seconds, plus the least-squares slope in ms per second over the step.
A standing queue that builds up during a step (bufferbloat: a large input buffer at a rate above capacity) shows as
rising bins and a positive slope; ab_segments' per-step mean and step_jitter's spread around the median both hide it.

Needs one RTP timestamp base across the run (no waybeam restart), like ab_segments.

Usage: python3 latency_bins.py trace.pftrace steps.txt --air-offset-s S --baseline LABEL [--guard-s 5] [--bin-s 10]
"""
import argparse
import statistics as st

from ab_segments import fit_drift, frames_from_packets, load_trace, read_steps, step_of, step_window


def bins_and_slope(frames, line, lo_ns, hi_ns, bin_s):
    """Frames whose last packet lies in [lo, hi) -> ([mean ms per bin], slope ms/s); empty bins are left out."""
    pts = [(f.last, (f.last - f.capture - line(f.last)) / 1e6) for f in frames if lo_ns <= f.last < hi_ns]
    if len(pts) < 2:
        return [], float("nan")
    width = int(bin_s * 1e9)
    per = {}
    for t, lat in pts:
        per.setdefault((t - lo_ns) // width, []).append(lat)
    bins = [st.mean(per[k]) for k in sorted(per)]
    xs = [(t - lo_ns) / 1e9 for t, _ in pts]
    ys = [lat for _, lat in pts]
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else float("nan")
    return bins, slope


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=5.0)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--bin-s", type=float, default=10.0)
    a = ap.parse_args()
    pkts, ready, rt = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    guard = a.guard_s * 1e9
    tagged = [(f, step_of(f.first, steps, end, guard)) for f in frames]
    slope, icpt = fit_drift([(f.last, f.last - f.capture) for f, i in tagged if i is not None and steps[i][1] == a.baseline])
    line = lambda t: slope * t + icpt
    print(f"ms above the '{a.baseline}' drift line; bins of {a.bin_s:g} s from each step's guarded start; slope in ms/s")
    for i, (_, lab) in enumerate(steps):
        lo, hi = step_window(i, steps, end, guard)
        bins, sl = bins_and_slope(frames, line, lo, hi, a.bin_s)
        print(f"{i:2d} {lab:13s} slope {sl:+7.3f}  " + " ".join(f"{b:6.1f}" for b in bins))


if __name__ == "__main__":
    main()
