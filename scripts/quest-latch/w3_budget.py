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
            for a source within ~1 % of the display rate the phase slides too slowly for one short trace (a full
            cycle takes a minute or more), so --uniform-wait MODE replaces the measured wait by its long-run mean,
            half a display period [INFERRED: phase uniform over time without a lock]
  panel     latch -> light, backlight strobe                    (same for every mode)    [INFERRED]
Decision: a mode wins only if its whole range is below every other mode's range; the shared constants cancel, so
the ranges that matter are the per-mode ISP intervals. Otherwise: "equal within uncertainty".

Usage: python3 w3_budget.py air.tsv out/mode_<mode>_<rep>.txt ... [--uniform-wait <mode>]
  air.tsv: tab-separated with a header containing mode, s_air_med, readout_ms, isp_lo, isp_hi (one row per mode;
  several rows for one mode are averaged). Quest files are named mode_<mode>_<rep>.txt (mode_segment.sh output).
  Optional air columns: encode_med (shown, already inside s_air), fov_h / fov_v (the share of the sensor's width /
  height the mode uses, in %; W3c: field of view against latency). With fov columns a trade-off line per mode gives
  its extra latency (range midpoints) against the fastest mode and its field-of-view area against that mode's.
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
    m = re.search(r"(\d+) packets / (\d+) frames .*?([\d.]+) pkt/frame; sequence gaps \(lost before the app\) = (\d+)", text)
    if m:
        pkts, frames, lost = int(m.group(1)), int(m.group(2)), int(m.group(4))
        out["pkt_per_frame"] = float(m.group(3))
        out["lost_pct"] = 100.0 * lost / (pkts + lost) if pkts + lost else 0.0
        d = re.search(re.escape(QUEST_LINES["decode"]) + r"\s+n=\s*(\d+)", text)
        if d and frames:
            # frames with no decoded-frame mark within 20 ms (transport_analyze's matching window): dropped or late
            out["undecoded_pct"] = 100.0 * (frames - int(d.group(1))) / frames
    return out


def parse_air(rows):
    """{mode: {s_air, readout, isp_lo, isp_hi}} averaged over the rows of each mode."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for k_in, k_out in (("s_air_med", "s_air"), ("readout_ms", "readout"), ("isp_lo", "isp_lo"), ("isp_hi", "isp_hi"),
                            ("fps", "fps"), ("encode_med", "encode"), ("fov_h", "fov_h"), ("fov_v", "fov_v")):
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
        robust = {k: st.mean(r[k] for r in reps if k in r) for k in ("pkt_per_frame", "lost_pct", "undecoded_pct")
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


def tradeoff(res):
    """Per mode with fov_h/fov_v: (extra ms against the fastest mode, range midpoints; field-of-view area as a
    multiple of the fastest mode's). Empty if the fastest mode has no field of view."""
    fastest = min(res, key=lambda m: res[m]["total_lo"] + res[m]["total_hi"])
    f = res[fastest]
    if "fov_h" not in f or "fov_v" not in f:
        return {}
    mid = lambda r: (r["total_lo"] + r["total_hi"]) / 2
    area = lambda r: r["fov_h"] * r["fov_v"]
    return {m: (mid(r) - mid(f), area(r) / area(f)) for m, r in res.items() if "fov_h" in r and "fov_v" in r}


DISPLAY_PERIOD_MS = 8.3545  # Quest 2 "120 Hz" = 119.70 Hz (docs/xr/compositor-phase.md, calibration)


def main(argv):
    uniform = set()
    while "--uniform-wait" in argv:
        i = argv.index("--uniform-wait")
        uniform.add(argv[i + 1])
        del argv[i:i + 2]
    with open(argv[1], newline="", encoding="utf-8") as fh:
        air = parse_air(csv.DictReader(fh, delimiter="\t"))
    quest = defaultdict(list)
    for f in argv[2:]:
        m = re.match(r"mode_([^_]+)_", Path(f).name)
        if m:
            quest[m.group(1)].append(parse_quest(Path(f).read_text(encoding="utf-8", errors="ignore")))
    for mode in uniform:
        for rep in quest.get(mode, []):
            rep["wait_measured"] = rep.get("wait")
            rep["wait"] = DISPLAY_PERIOD_MS / 2
    res = budget(air, quest)
    for mode in uniform:
        if mode in res:
            print(f"mode {mode}: latch wait = {DISPLAY_PERIOD_MS / 2:.2f} ms (half a display period, uniform phase); "
                  f"measured in the traces: {[r.get('wait_measured') for r in quest[mode]]}")
    cols = ["capture", "readout", "isp_lo", "isp_hi", "encode", "s_air", "spread", "decode", "wait", "pkt_per_frame",
            "lost_pct", "undecoded_pct"]
    width = max(4, *(len(m) for m in res)) if res else 4
    print(f"{'mode':{width}s}  n  " + "  ".join(f"{c:>7s}" for c in cols) + "      fov   total G2G range (ms)")
    for mode in sorted(res, key=lambda m: res[m]["own_hi"]):
        r = res[mode]
        fov = f"{r['fov_h']:.0f}x{r['fov_v']:.0f}%" if "fov_h" in r and "fov_v" in r else "-"
        print(f"{mode:{width}s} {r['repeats']:2d}  " + "  ".join(f"{r.get(c, float('nan')):7.2f}" for c in cols)
              + f"  {fov:>7s}   {r['total_lo']:.1f} .. {r['total_hi']:.1f}")
    for mode, (extra, area) in sorted(tradeoff(res).items(), key=lambda kv: kv[1][0]):
        print(f"trade-off {mode}: {extra:+.1f} ms for {area:.2f}x the field-of-view area of the fastest mode")
    w = decide(res)
    print("winner:", w if w else "none: the modes are equal within the ISP uncertainty (needs an optical G2G to decide)")


if __name__ == "__main__":
    main(sys.argv)
