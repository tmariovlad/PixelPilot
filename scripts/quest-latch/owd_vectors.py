"""Test vectors for the app's port of owd.LiveBase (docs/xr/stats-backend.md §7.2): identical inputs, expected outputs
from the Python reference, so the Java/C++ port can be checked number for number.

Usage: python3 owd_vectors.py <out dir> [--g56 trace.pftrace steps.txt --air-offset-s 1.284]

Writes CSV files (# header lines: what and the parameters; then t_ns,first_ms,rel_w60_ms,rel_winf_ms):
  synthetic.csv  10 fps, 600 s: OWD 5 + 0.06 ms/s drift (not the 0.07 prior, so the drift estimate must be learnt)
                 + a deterministic 0..1 ms ripple; +50 ms standing queue 250-400 s (longer than the 60 s window);
                 a +5000 ms RTP base jump at 500 s (a waybeam restart: reset).
  g56_m6.csv     the real g56 frames of its first two steps, m7b25f46 (clean) then m6b25f46 (+55 ms standing queue,
                 link-envelope), t relative to the first frame (--g56 needs the trace).
The reference parameters are LiveBase's defaults except window_s: 60 s and unbounded (inf).
"""
import argparse
import math
import os

import owd

PARAMS = "block_s=10 horizon_s=300 prior=0.07 min_blocks=6 jump_ms=1000 accept_ms=2 (owd.LiveBase defaults)"


def synthetic():
    t, v = [], []
    for i in range(6000):
        x = i / 10
        ripple = ((i * 37) % 11) / 10.0
        q = 50.0 if 250 <= x < 400 else 0.0
        jump = 5000.0 if x >= 500 else 0.0
        t.append(int(i * 1e8))
        v.append(5.0 + 0.06 * x + ripple + q + jump)
    return t, v


def write(path, what, t, v):
    w60 = owd.live_rel(t, v, window_s=60.0)
    winf = owd.live_rel(t, v, window_s=math.inf)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {what}\n# reference: owd.LiveBase, window_s = 60 / inf, {PARAMS}\n")
        fh.write("t_ns,first_ms,rel_w60_ms,rel_winf_ms\n")
        for row in zip(t, v, w60, winf):
            fh.write(f"{row[0]},{row[1]:.9f},{row[2]:.9f},{row[3]:.9f}\n")
    print(f"{path}: {len(t)} frames")


def g56(trace, steps_path, offset):
    from ab_segments import frames_from_packets, load_trace, read_steps
    pkts, ready, rt = load_trace(trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, _ = read_steps(steps_path, offset, rt)
    lo, hi = steps[0][0], steps[2][0]
    rows = [r for r in owd.per_frame(frames) if lo <= r["t"] < hi]
    t0 = rows[0]["t"]
    return [r["t"] - t0 for r in rows], [r["first"] - rows[0]["first"] for r in rows], (steps[0][1], steps[1][1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--g56", nargs=2, metavar=("TRACE", "STEPS"))
    ap.add_argument("--air-offset-s", type=float, default=1.284)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t, v = synthetic()
    write(os.path.join(a.out, "synthetic.csv"), "synthetic: drift 0.06 ms/s, ripple, +50 ms 250-400 s, +5000 ms jump "
          "at 500 s (owd_vectors.synthetic)", t, v)
    if a.g56:
        t, v, labels = g56(a.g56[0], a.g56[1], a.air_offset_s)
        write(os.path.join(a.out, "g56_m6.csv"), f"real frames, g56 steps 0-1 ({labels[0]} then {labels[1]}), "
              "first relative to the first frame, t from the first frame", t, v)


if __name__ == "__main__":
    main()
