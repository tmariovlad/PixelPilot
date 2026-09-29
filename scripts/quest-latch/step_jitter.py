"""Per-step latency spread when each step restarts the encoder. A waybeam restart draws a new random RTP timestamp base
(HANDOFF), so the capture -> frame-complete latency of different steps cannot be compared on one drift line. Within
one step the base is constant, so each frame's latency minus the step's median is valid: its tail is what a lever
adds for some frames (e.g. the wait of FEC recovery for a larger block). Prints p50 / p95 / p99 / max of that residual
(ms) and the frames per step.

Usage: python3 step_jitter.py trace.pftrace steps.txt --air-offset-s S [--guard-s 4]
"""
import argparse
import statistics as st

from ab_segments import frames_from_packets, load_trace, pct, read_steps, step_window

MIN_FRAMES = 20


def residual_stats(latencies_ns):
    """latencies_ns: frame-complete minus capture per frame of one step. Returns ms stats around the median, or None."""
    if len(latencies_ns) < MIN_FRAMES:
        return None
    med = st.median(latencies_ns)
    r = [(x - med) / 1e6 for x in latencies_ns]
    return {"p50": pct(r, .5), "p95": pct(r, .95), "p99": pct(r, .99), "max": max(r), "n": len(r)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=4.0)
    a = ap.parse_args()
    pkts, ready, rt = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    print(f"{'':16s}{'frames':>7s}{'p50':>7s}{'p95':>7s}{'p99':>7s}{'max':>8s}   (ms around the step's own median)")
    for i, (_, lab) in enumerate(steps):
        lo, hi = step_window(i, steps, end, a.guard_s * 1e9)
        s = residual_stats([f.last - f.capture for f in frames if lo <= f.first < hi])
        if s is None:
            continue
        print(f"{i:2d} {lab:13s}{s['n']:7d}{s['p50']:7.2f}{s['p95']:7.2f}{s['p99']:7.2f}{s['max']:8.2f}")


if __name__ == "__main__":
    main()
