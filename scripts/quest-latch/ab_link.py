"""Link side of an in-trace A/B (companion to ab_segments.py, same trace, step log and offset): per step and per
state, the radio and FEC picture plus temperatures, read in the same guarded step windows.

- rx/s, fec_rec/s, wfb_lost/s, rssi: the app's 'ppxr_wfb_*' counters (one sample per ~300 ms wfb-ng stats interval,
  written by WfbStatsTrace). rx = packets received over the air, data + FEC parity; wfb_lost = still missing after FEC.
- tx/s and pre-FEC loss: the air loop writes the cumulative wlan0 tx_packets on every step line
  ("<air epoch> <label> tx=<n> temp=<C>", END line too). tx/s = delta over the whole step on the air clock;
  pre_fec_loss = 1 - rx/s / tx/s. Anything else the air unit transmits on wlan0 counts as sent video, so this is an
  upper bound [INFERRED].
- air_c: the air SoC temperature from the same step line. Quest thermal: --thermal CSV from quest_thermal_log.sh.

Usage: python3 ab_link.py trace.pftrace steps.txt --air-offset-s S [--guard-s 2] [--thermal thermal.csv] [--csv out.csv]
  --air-offset-s  the offset ab_segments.py used (after --fit-offset, the fitted value it printed).
"""
import argparse
import csv
import statistics as st
from collections import OrderedDict

from ab_segments import read_steps, step_window

WFB_COUNTERS = ("ppxr_wfb_p_all", "ppxr_wfb_fec_rec", "ppxr_wfb_lost", "ppxr_wfb_rssi")


def read_step_fields(path):
    """key=value fields of every step line, in step order (ERR lines skipped, END last), with the air epoch as 't'."""
    out = []
    for line in open(path, encoding="utf-8"):
        parts = line.split()
        if len(parts) < 2 or line.startswith("#") or "ERR" in parts or parts[1] == "PRE":
            continue
        try:
            f = {"t": float(parts[0]), "label": parts[1]}
        except ValueError:
            continue
        for kv in parts[2:]:
            k, _, v = kv.partition("=")
            try:
                f[k] = float(v)
            except ValueError:
                pass
        out.append(f)
    return out


def tx_rates(fields):
    """Per step (not END): packets/s sent by the air unit over the whole step, or None without tx= on both ends."""
    rates = []
    for a, b in zip(fields, fields[1:]):
        ok = "tx" in a and "tx" in b and b["t"] > a["t"]
        rates.append((b["tx"] - a["tx"]) / (b["t"] - a["t"]) if ok else None)
    return rates


def window_stats(samples, a, b, per_second):
    """samples [(ts, value)] sorted; sum/s (per_second) or mean of the values with a <= ts < b; None if empty."""
    vals = [v for t, v in samples if a <= t < b]
    if not vals:
        return None
    return sum(vals) / ((b - a) / 1e9) if per_second else st.mean(vals)


def per_step(counters, thermal, fields, steps, end, guard):
    """counters {name: [(trace_ns, v)]}; thermal [(trace_ns, row dict)]; fields/steps aligned by index.
    Returns [(i, label, row)]."""
    tx = tx_rates(fields)
    rows = []
    for i, (_, lab) in enumerate(steps):
        a, b = step_window(i, steps, end, guard)
        r = {
            "rx_per_s": window_stats(counters.get("ppxr_wfb_p_all", []), a, b, True),
            "fec_rec_per_s": window_stats(counters.get("ppxr_wfb_fec_rec", []), a, b, True),
            "wfb_lost_per_s": window_stats(counters.get("ppxr_wfb_lost", []), a, b, True),
            "rssi": window_stats(counters.get("ppxr_wfb_rssi", []), a, b, False),
            "tx_per_s": tx[i] if i < len(tx) else None,
            "air_c": fields[i].get("temp") if i < len(fields) else None,
        }
        r["pre_fec_loss_pct"] = (100.0 * (1 - r["rx_per_s"] / r["tx_per_s"])
                                 if r["rx_per_s"] is not None and r["tx_per_s"] else None)
        th = [row for t, row in thermal if a <= t < b]
        r["quest_status_max"] = max((x["thermal_status"] for x in th), default=None)
        r["quest_cpu_max_c"] = max((x["cpu_max_c"] for x in th), default=None)
        r["quest_batt"] = min((x["batt_level"] for x in th), default=None)
        rows.append((i, lab, r))
    return rows


def per_state(rows):
    """Mean of each field over a state's steps (None-safe; statuses/temps take the max, battery the min)."""
    out = OrderedDict()
    for _, lab, r in rows:
        out.setdefault(lab, []).append(r)
    pick = {"quest_status_max": max, "quest_cpu_max_c": max, "air_c": max, "quest_batt": min}
    res = []
    for lab, rs in out.items():
        agg = {}
        for k in rs[0]:
            vals = [x[k] for x in rs if x[k] is not None]
            agg[k] = (pick.get(k, st.mean))(vals) if vals else None
        res.append((lab, agg))
    return res


def load(path, air_offset_s, steps_path, thermal_path):
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    counters = {n: [(r.ts, r.value) for r in q(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        f"where t.name='{n}' order by c.ts")] for n in WFB_COUNTERS}
    snap = q("select ts, clock_value from clock_snapshot where clock_name='REALTIME' order by ts limit 1")
    rt_off = snap[0].clock_value - snap[0].ts
    steps, end = read_steps(steps_path, air_offset_s, rt_off)
    if end is None:
        end = max((s[-1][0] for s in counters.values() if s), default=steps[-1][0])
    thermal = []
    if thermal_path:
        for row in csv.DictReader(open(thermal_path, encoding="utf-8")):
            thermal.append((float(row["quest_epoch"]) * 1e9 - rt_off,
                            {k: float(v) for k, v in row.items() if k != "quest_epoch"}))
    return counters, thermal, read_step_fields(steps_path), steps, end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=2.0)
    ap.add_argument("--thermal", help="CSV from quest_thermal_log.sh")
    ap.add_argument("--csv", help="also write the per-step rows to this CSV file")
    a = ap.parse_args()
    counters, thermal, fields, steps, end = load(a.trace, a.air_offset_s, a.steps, a.thermal)
    if not counters["ppxr_wfb_p_all"]:
        print("no ppxr_wfb_* counters in the trace (app build without WfbStatsTrace?)")
    rows = per_step(counters, thermal, fields, steps, end, a.guard_s * 1e9)
    keys = ["tx_per_s", "rx_per_s", "pre_fec_loss_pct", "fec_rec_per_s", "wfb_lost_per_s", "rssi",
            "air_c", "quest_cpu_max_c", "quest_status_max", "quest_batt"]
    heads = ["tx/s", "rx/s", "preFEC%", "fec/s", "lost/s", "rssi", "air°C", "Q cpu°C", "Q st", "batt"]
    def fmt(v):
        if v is None:
            return f"{'-':>9}"
        return f"{v:9.1f}" if isinstance(v, float) else f"{v:>9}"

    hdr = f"{'':14s}" + "".join(f"{h:>9s}" for h in heads)
    print("per step (link side, guarded windows)\n" + hdr)
    for i, lab, r in rows:
        print(f"{i:2d} {lab:11s}" + "".join(fmt(r[k]) for k in keys))
    print("\nper state\n" + hdr)
    for lab, r in per_state(rows):
        print(f"{lab:14s}" + "".join(fmt(r[k]) for k in keys))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["step", "label"] + keys)
            for i, lab, r in rows:
                w.writerow([i, lab] + ["" if r[k] is None else round(r[k], 3) for k in keys])
        print(f"per-step rows written to {a.csv}")


if __name__ == "__main__":
    main()
