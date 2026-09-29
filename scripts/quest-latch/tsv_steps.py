"""Rows of a probe TSV (rtp_holes.py / fec_blocks.py --tsv, first column t_mono_ms = the Quest's CLOCK_MONOTONIC) per
air step: per value of one column, the rows and the sum of a weight column, inside each step's guarded window (the
two-sided window of ab_segments.step_window). Steps are on the PC clock (the air runs ntpd, air wall ~= PC).

The Quest mono -> PC offset comes from any PPXR_EVENT line of the same logcat, which carries both t_mono_ms and
t_wall_ms, minus Quest-PC (ab_detached's meta).

Usage: python3 tsv_steps.py rows.tsv qtx_<label>.raw.txt steps.txt --quest-minus-pc-ms Q --column class
           [--weight gap] [--guard-s 5]
"""
import argparse
import csv
import re

_MONO_WALL = re.compile(r"t_mono_ms=(\d+) t_wall_ms=(\d+)")


def mono_to_pc_offset_ms(lines, quest_minus_pc_ms):
    """PC ms = Quest mono ms + this, from the first logcat line with both clocks."""
    for line in lines:
        m = _MONO_WALL.search(line)
        if m:
            return int(m.group(2)) - int(m.group(1)) - quest_minus_pc_ms
    raise ValueError("no line with t_mono_ms and t_wall_ms")


def count_per_step(rows, steps, end, guard_s, offset_ms, column, weight=None):
    """steps [(pc_s, label)] sorted -> [(label, window_s, {value: (rows, weight sum)})] per step."""
    out = []
    for i, (start, label) in enumerate(steps):
        lo = start + guard_s
        hi = (steps[i + 1][0] if i + 1 < len(steps) else end) - guard_s
        counts = {}
        for r in rows:
            t = (float(r["t_mono_ms"]) + offset_ms) / 1000.0
            if lo <= t < hi:
                n, w = counts.get(r[column], (0, 0))
                counts[r[column]] = (n + 1, w + (int(r[weight]) if weight else 0))
        out.append((label, hi - lo, counts))
    return out


def read_steps(path):
    """'<pc epoch> <label>' lines + '<epoch> END' -> ([(s, label)], end)."""
    steps, end = [], None
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) < 2 or line.startswith("#"):
            continue
        if p[1] == "END":
            end = float(p[0])
        else:
            steps.append((float(p[0]), p[1]))
    return sorted(steps), end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv")
    ap.add_argument("logcat")
    ap.add_argument("steps")
    ap.add_argument("--quest-minus-pc-ms", type=float, required=True)
    ap.add_argument("--column", required=True)
    ap.add_argument("--weight")
    ap.add_argument("--guard-s", type=float, default=5.0)
    a = ap.parse_args()
    with open(a.logcat, encoding="utf-8", errors="ignore") as fh:
        offset = mono_to_pc_offset_ms(fh, a.quest_minus_pc_ms)
    with open(a.tsv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    steps, end = read_steps(a.steps)
    per = count_per_step(rows, steps, end, a.guard_s, offset, a.column, a.weight)
    values = sorted({v for _, _, c in per for v in c})
    unit = f" ({a.weight} sum)" if a.weight else ""
    print(f"per step: rows per minute by {a.column}" + (f"; in brackets the {a.weight} sum per minute" if a.weight else ""))
    print(f"{'':16s}{'s':>5s}" + "".join(f"{v:>18s}" for v in values) + unit)
    for i, (label, secs, c) in enumerate(per):
        cells = "".join(f"{c.get(v, (0, 0))[0] * 60 / secs:9.1f}" + (f" ({c.get(v, (0, 0))[1] * 60 / secs:6.1f})" if a.weight else " " * 9)
                        for v in values)
        print(f"{i:2d} {label:13s}{secs:5.0f}{cells}")


if __name__ == "__main__":
    main()
