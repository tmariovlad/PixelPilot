"""Shape of the losses that FEC did not recover, per step: each RTP sequence hole is a run (packets missing in a row).
Per step it prints the run-length histogram, the run durations in ms (from the last packet before the hole to the
first after it), runs/s, and the Rayleigh phase lock of the run starts at the 102.4 ms beacon period (Z > ~13:
locked; the neighbour AP's beacons, docs/xr/link-envelope.md).

What it cannot show: which positions of a FEC block were lost. The wfb-ng receiver logs only "PKT_LOST <n>" per
unrecoverable block, with no bitmap of the fragments received, so the pre-FEC burst shape inside a block is not in the
trace or the logcat.

Usage: python3 loss_bursts.py trace.pftrace steps.txt --air-offset-s S [--guard-s 4]
"""
import argparse

from ab_segments import load_trace, pct, read_steps, step_window
from tu_pause import TU_PERIOD_S, rayleigh_z

BINS = ("1", "2", "3", "4", "5-8", "9+")


def runs(pkts):
    """pkts [(ns, seq16)] in arrival order -> [(start_ns, length, ms)] for each sequence hole. start_ns is the arrival
    of the last packet before the hole, ms the time to the first packet after it."""
    out = []
    for (t0, s0), (t1, s1) in zip(pkts, pkts[1:]):
        d = (s1 - s0) & 0xFFFF
        if 1 < d < 0x8000:
            out.append((t0, d - 1, (t1 - t0) / 1e6))
    return out


def histogram(rs):
    h = {b: 0 for b in BINS}
    for _, n, _ in rs:
        h["1" if n == 1 else "2" if n == 2 else "3" if n == 3 else "4" if n == 4 else "5-8" if n <= 8 else "9+"] += 1
    return h


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=4.0)
    a = ap.parse_args()
    pkts, _, rt = load_trace(a.trace)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    print(f"{'':16s}{'runs/s':>7s} " + " ".join(f"{b:>4s}" for b in BINS)
          + f"{'pkts p50':>9s}{'ms p50':>7s}{'ms p95':>7s}{'ms max':>7s}{'Z 9.77':>8s}")
    for i, (_, lab) in enumerate(steps):
        lo, hi = step_window(i, steps, end, a.guard_s * 1e9)
        mine = [(t, s) for t, s, _ in pkts if lo <= t < hi]
        if len(mine) < 100:
            continue
        rs = runs(mine)
        secs = (hi - lo) / 1e9
        h = histogram(rs)
        lens = [n for _, n, _ in rs]
        ms = [m for _, _, m in rs]
        z = rayleigh_z([t for t, _, _ in rs], TU_PERIOD_S)
        print(f"{i:2d} {lab:13s}{len(rs) / secs:7.2f} " + " ".join(f"{h[b]:4d}" for b in BINS)
              + (f"{pct(lens, .5):9.0f}{pct(ms, .5):7.1f}{pct(ms, .95):7.1f}{max(ms):7.1f}" if rs else f"{'-':>9s}{'-':>7s}{'-':>7s}{'-':>7s}")
              + f"{z:8.1f}")


if __name__ == "__main__":
    main()
