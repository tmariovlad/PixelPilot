"""Per-step check of the air's ~3.7 ms TX pause every 100 TU (102.4 ms), the "B4" signature of the OpenIPC beacon-rhythm
audit (repos/tasks/link-25mbit-audit-2026-09-28/beacon-rhythm/B4-clock-domain-phase.md): an RTP arrival gap of 3-4.6 ms
with NO sequence number missing, phase-locked to 102.4 ms, after which frame latency steps up and decays.

Per step (guarded window) it prints:
- pauses/s: arrival gaps between consecutive RTP sequence numbers of --min-ms..--max-ms (B4's definition);
- Z(pause): Rayleigh phase-locking of those gap starts at 102.4 ms (random ~1, locked >> 13);
- per-cycle: pauses per 102.4 ms cycle (B4 saw 0.88-0.93 with the pause present);
- lat mean / p95: frame-complete latency (last packet - capture, minus the baseline drift line, as ab_segments.py);
- lat fold: max-min of the mean latency over 16 phase bins at 102.4 ms (the "teeth"; ~flat when the pause is gone);
- loss: RTP packets lost in the window.
The phase is fitted per step (it moves at every air reboot), so no constant from another trace is needed.

Usage: python3 tu_pause.py trace.pftrace steps.txt --air-offset-s S [--guard-s 5] [--baseline base]
"""
import argparse
import cmath
import math
import statistics as st

from ab_segments import fit_drift, frames_from_packets, load_trace, pct, read_steps, step_window
from rtp_seq import seq_loss

TU_PERIOD_S = 0.1024


def pause_gaps(arrivals_ns, min_ms, max_ms, seqs=None):
    """Start times (ns) of the gaps between consecutive arrivals lasting min_ms..max_ms. With seqs (16-bit RTP sequence
    numbers, same order), only gaps between consecutive sequence numbers count: a gap with a packet missing is loss,
    not a pause."""
    out = []
    for i in range(1, len(arrivals_ns)):
        d = (arrivals_ns[i] - arrivals_ns[i - 1]) / 1e6
        if min_ms <= d <= max_ms and (seqs is None or ((seqs[i] - seqs[i - 1]) & 0xFFFF) == 1):
            out.append(arrivals_ns[i - 1])
    return out


def rayleigh_z(times_ns, period_s):
    """Rayleigh Z = n * R^2 of the event phases at period_s (random ~1; p < 1e-6 above ~13.8)."""
    if not times_ns:
        return 0.0
    v = sum(cmath.exp(2j * math.pi * ((t / 1e9) % period_s) / period_s) for t in times_ns)
    return abs(v) ** 2 / len(times_ns)


def fold_amplitude(points, period_s, bins=16):
    """points [(t_ns, value)]: max - min of the per-bin mean value over one period (bins with < 5 points ignored)."""
    acc = [[] for _ in range(bins)]
    for t, v in points:
        acc[int(((t / 1e9) % period_s) / period_s * bins) % bins].append(v)
    means = [st.mean(a) for a in acc if len(a) >= 5]
    return max(means) - min(means) if len(means) >= 2 else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=5.0)
    ap.add_argument("--baseline", help="label for the latency drift line (default: the first step's label)")
    ap.add_argument("--min-ms", type=float, default=3.0)
    ap.add_argument("--max-ms", type=float, default=4.6)
    a = ap.parse_args()
    pkts, ready, rt_off = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, loop_end = read_steps(a.steps, a.air_offset_s, rt_off)
    end = min(pkts[-1][0], loop_end) if loop_end else pkts[-1][0]
    baseline = a.baseline or steps[0][1]
    guard = a.guard_s * 1e9
    base_pts = []
    for i, (_, lab) in enumerate(steps):
        if lab == baseline:
            lo, hi = step_window(i, steps, end, guard)
            base_pts += [(f.last, f.last - f.capture) for f in frames if lo <= f.first < hi]
    slope, icpt = fit_drift(base_pts)
    print(f"{'':12s}{'pauses/s':>9s}{'per-cyc':>8s}{'Z(pause)':>10s}{'lat mean':>9s}{'lat p95':>8s}{'lat fold':>9s}"
          f"{'loss':>7s}")
    for i, (_, lab) in enumerate(steps):
        lo, hi = step_window(i, steps, end, guard)
        mine = [p for p in pkts if lo <= p[0] < hi]
        if len(mine) < 100:
            print(f"{i:2d} {lab:9s} (too few packets)")
            continue
        secs = (hi - lo) / 1e9
        gaps = pause_gaps([p[0] for p in mine], a.min_ms, a.max_ms, [p[1] for p in mine])
        fr = [f for f in frames if lo <= f.first < hi]
        lat = [(f.last, (f.last - f.capture - (slope * f.last + icpt)) / 1e6) for f in fr]
        vals = [v for _, v in lat]
        print(f"{i:2d} {lab:9s}{len(gaps) / secs:9.2f}{len(gaps) / (secs / TU_PERIOD_S):8.2f}"
              f"{rayleigh_z(gaps, TU_PERIOD_S):10.1f}{st.mean(vals):9.2f}{pct(vals, .95):8.2f}"
              f"{fold_amplitude(lat, TU_PERIOD_S):9.2f}{seq_loss([p[1] for p in mine])[0]:7d}")


if __name__ == "__main__":
    main()
