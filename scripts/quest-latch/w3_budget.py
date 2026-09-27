"""W3: glass-to-glass budget per air-unit mode from separately measured segments, and the decision rule.

Absolute capture -> arrival cannot be compared between modes (each waybeam start draws a new random RTP base), so
each mode's budget is a sum of segments that do not need it:
  capture   event -> next exposure: half a frame period on average (air, per mode from fps) [INFERRED: uniform arrival]
  readout   sensor readout from the IMX415 registers            (air, per mode)          [PROVEN]
            counted in full (active lines x 1H: the top line waits the whole readout), the same for every mode;
            [2] 1080p 5.31, [6]/[9] 720p 3.52, [7] 480p 2.34 ms (OpenIPC w3-readout-per-mode.md, driver 6e637e75)
  isp       ISP (+ VPE/SCL) before VENC input                   (air, per mode, range)   [INFERRED]
  s_air     VENC input -> last packet sent, waybeam sidecar     (air, per mode)          [PROVEN]
  tx_floor  first packet on air -> Quest                        (same for every mode)    [INFERRED, HIL t2->t3]
  spread    frame first -> last packet on the Quest             (Quest trace, per mode)  [PROVEN]
  decode    frame complete -> decoded                           (Quest trace, per mode)  [PROVEN]
  wait      decoded -> compositor latch                         (Quest trace, per mode)  [PROVEN]
  panel     latch -> light, backlight strobe                    (same for every mode)    [INFERRED]
Decision: a mode wins only if its whole range is below every other mode's range; the shared constants cancel, so
the ranges that matter are the per-mode ISP intervals. Otherwise: "equal within uncertainty".

Usage: python3 w3_budget.py air.tsv out/mode_<mode>_<rep>.txt ...
  air.tsv: tab-separated with a header containing mode, s_air_med, readout_ms, isp_lo, isp_hi (one row per mode;
  several rows for one mode are averaged). Quest files are named mode_<mode>_<rep>.txt (mode_segment.sh output).
"""
import csv
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

TX_FLOOR_MS = 1.9          # HIL t2->t3 on APFPV, OpenIPC docs/KNOWLEDGE.md:21 (docs/xr/g2g-budget.md)
PANEL_MS = (10.2, 13.5)    # latch -> mid-flash of the two backlight halves (docs/xr/compositor-phase.md)

QUEST_LINES = {
    "spread": "frame packet spread (first -> last packet)",
    "decode": "frame complete -> decoded frame ready",
    "wait": "frame ready (queueBuffer) -> latch",
}


def parse_quest(text):
    """Mean (ms) of each Quest segment from one mode_segment.sh output, plus the robustness figures of the same
    trace: packets per frame and the RTP loss before the app in % (tie-breaker when latencies are equal)."""
    out = {}
    for key, label in QUEST_LINES.items():
        m = re.search(re.escape(label) + r".*?mean=\s*([-\d.]+)", text)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"(\d+) packets / \d+ frames .*?([\d.]+) pkt/frame; sequence gaps \(lost before the app\) = (\d+)", text)
    if m:
        pkts, lost = int(m.group(1)), int(m.group(3))
        out["pkt_per_frame"] = float(m.group(2))
        out["lost_pct"] = 100.0 * lost / (pkts + lost) if pkts + lost else 0.0
    return out


def parse_air(rows):
    """{mode: {s_air, readout, isp_lo, isp_hi}} averaged over the rows of each mode."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for k_in, k_out in (("s_air_med", "s_air"), ("readout_ms", "readout"), ("isp_lo", "isp_lo"), ("isp_hi", "isp_hi"),
                            ("fps", "fps")):
            if r.get(k_in) not in (None, ""):
                acc[str(r["mode"]).strip()][k_out].append(float(r[k_in]))
    return {m: {k: st.mean(v) for k, v in d.items()} for m, d in acc.items()}


def budget(air, quest):
    """Per mode: segments and the total as (lo, hi) in ms. quest: {mode: [segment dicts, one per repeat]}."""
    res = {}
    for mode, a in air.items():
        reps = quest.get(mode, [])
        if not reps:
            continue
        q = {k: st.mean(r[k] for r in reps if k in r) for k in QUEST_LINES if any(k in r for r in reps)}
        robust = {k: st.mean(r[k] for r in reps if k in r) for k in ("pkt_per_frame", "lost_pct")
                  if any(k in r for r in reps)}
        capture = 500.0 / a["fps"] if a.get("fps") else 0.0  # ms: half a frame period
        fixed = capture + a["s_air"] + a["readout"] + TX_FLOOR_MS + sum(q.values())
        lo = fixed + a["isp_lo"] + PANEL_MS[0]
        hi = fixed + a["isp_hi"] + PANEL_MS[1]
        res[mode] = {**a, **q, **robust, "capture": capture, "repeats": len(reps), "own_lo": fixed + a["isp_lo"], "own_hi": fixed + a["isp_hi"],
                     "total_lo": lo, "total_hi": hi}
    return res


def decide(res):
    """The winner, if its own range (shared constants excluded) lies wholly below every other mode's; else None."""
    if len(res) < 2:
        return None
    best = min(res, key=lambda m: res[m]["own_hi"])
    if all(res[best]["own_hi"] < res[m]["own_lo"] for m in res if m != best):
        return best
    return None


def main(argv):
    with open(argv[1], newline="", encoding="utf-8") as fh:
        air = parse_air(csv.DictReader(fh, delimiter="\t"))
    quest = defaultdict(list)
    for f in argv[2:]:
        m = re.match(r"mode_([^_]+)_", Path(f).name)
        if m:
            quest[m.group(1)].append(parse_quest(Path(f).read_text(encoding="utf-8", errors="ignore")))
    res = budget(air, quest)
    cols = ["capture", "readout", "isp_lo", "isp_hi", "s_air", "spread", "decode", "wait", "pkt_per_frame", "lost_pct"]
    print("mode  n  " + "  ".join(f"{c:>7s}" for c in cols) + "   total G2G range (ms)")
    for mode in sorted(res, key=lambda m: res[m]["own_hi"]):
        r = res[mode]
        print(f"{mode:4s} {r['repeats']:2d}  " + "  ".join(f"{r.get(c, float('nan')):7.2f}" for c in cols)
              + f"   {r['total_lo']:.1f} .. {r['total_hi']:.1f}")
    w = decide(res)
    print("winner:", w if w else "none: the modes are equal within the ISP uncertainty (needs an optical G2G to decide)")


if __name__ == "__main__":
    main(sys.argv)
