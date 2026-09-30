"""An ab_run.sh-style air log rebuilt from the Quest side, for ab_fit.py (openipc repo slot/ab_fit.py) when the air's own
/tmp log is lost, e.g. a power cycle before it was pulled (2026-09-30 HDP/L6 slot).

- "SET <label> epoch=<T>" per step and "END epoch=<T>" come from the steps file (air epochs; tsv_steps.read_steps).
- "S t=<air epoch> fps=<n / 2>" per PPXR_STATS line (n = frames decoded in its 2 s window), only after each step's
  guard, so a switch transient cannot void a block; ab_fit voids a block when any S sample is below --fps-min.
This stands in for the air's own S samples (VENC Fps_1s every 10 s); it measures decoded fps on the headset, so a
block with radio loss can read lower than the encoder did. Say which log a fit used.

Usage: python3 quest_airlog.py steps.txt qtx_<label>.raw.txt --quest-minus-air-s S [--guard-s 15] > ab_<label>_quest.log
"""
import argparse
import re

import tsv_steps

_N = re.compile(r"\bn=(\d+)")


def air_log(steps_path, capture_path, quest_minus_air_s, guard_s=15.0):
    steps, end = tsv_steps.read_steps(steps_path)
    lines = [f"SET {label} epoch={int(s) if s == int(s) else s}" for s, label in steps]
    windows = [(s + guard_s, steps[i + 1][0] if i + 1 < len(steps) else end) for i, (s, _) in enumerate(steps)]
    samples = []
    with open(capture_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "PPXR_STATS" not in line:
                continue
            m = _N.search(line)
            if not m:
                continue
            t_air = float(line.split()[0]) - quest_minus_air_s
            if any(lo <= t_air < hi for lo, hi in windows):
                samples.append((t_air, f"S t={t_air:.3f} fps={int(m.group(1)) / 2:.1f}"))
    merged = [(s, l) for (s, _), l in zip(steps, lines)] + samples
    out = [l for _, l in sorted(merged, key=lambda x: x[0])]
    out.append(f"END epoch={int(end) if end == int(end) else end}")
    return out


def main():
    ap = argparse.ArgumentParser(description="ab_run-style air log from a steps file + the Quest's PPXR_STATS")
    ap.add_argument("steps")
    ap.add_argument("capture")
    ap.add_argument("--quest-minus-air-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=15.0)
    a = ap.parse_args()
    print("\n".join(air_log(a.steps, a.capture, a.quest_minus_air_s, a.guard_s)))


if __name__ == "__main__":
    main()
