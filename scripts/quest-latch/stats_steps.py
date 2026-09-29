"""The median of PPXR_STATS fields per air step, e.g. the per-chain RSSI in dBm (rssiA/rssiB) that a TX-power step must
move ~dB-for-dB to count (ab_link's rssi columns are a 0-100 quality, not dBm). PPXR_STATS lines come every 2 s with
the `general` pref stats_log (docs/xr/stats-backend.md). Windows are the two-sided guarded ones of the other analyzers.

Usage: python3 stats_steps.py qtx_<label>.raw.txt steps.txt --quest-minus-air-s S [--guard-s 5] [--keys rssiA,rssiB]
  S = Quest - PC (ab_detached's meta, in s) + PC - air (this boot's slot_watch AIR_CLOCK pc_minus_air_s).
"""
import argparse
import re
import statistics as st

from tsv_steps import read_steps

_KV = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?)(?=\s|$)")


def medians_per_step(lines, steps, end, guard_s, quest_minus_air_s, keys):
    """steps [(air s, label)] sorted -> [(label, samples, {key: median})] per step; non-numeric values are skipped."""
    per = [{k: [] for k in keys} for _ in steps]
    counts = [0] * len(steps)
    for line in lines:
        if "PPXR_STATS" not in line:
            continue
        try:
            t = float(line.split()[0]) - quest_minus_air_s
        except (ValueError, IndexError):
            continue
        for i, (start, _) in enumerate(steps):
            hi = (steps[i + 1][0] if i + 1 < len(steps) else end) - guard_s
            if start + guard_s <= t < hi:
                f = dict(_KV.findall(line))
                counts[i] += 1
                for k in keys:
                    if k in f:
                        per[i][k].append(float(f[k]))
                break
    return [(label, counts[i], {k: st.median(v) for k, v in per[i].items() if v}) for i, (_, label) in enumerate(steps)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logcat")
    ap.add_argument("steps")
    ap.add_argument("--quest-minus-air-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=5.0)
    ap.add_argument("--keys", default="rssiA,rssiB,snrA,snrB")
    a = ap.parse_args()
    keys = a.keys.split(",")
    steps, end = read_steps(a.steps)
    with open(a.logcat, encoding="utf-8", errors="ignore") as fh:
        rows = medians_per_step(fh, steps, end, a.guard_s, a.quest_minus_air_s, keys)
    print("per step: median of the PPXR_STATS samples (every 2 s)")
    print(f"{'':16s}{'n':>4s}" + "".join(f"{k:>8s}" for k in keys))
    for i, (label, n, med) in enumerate(rows):
        print(f"{i:2d} {label:13s}{n:4d}" + "".join(f"{med[k]:8.1f}" if k in med else f"{'-':>8s}" for k in keys))


if __name__ == "__main__":
    main()
