"""Link side of an in-trace A/B (companion to ab_segments.py, same trace, step log and offset): per step and per
state, the radio and FEC picture plus temperatures, read in the same guarded step windows.

- rx/s, fec_rec/s, wfb_lost/s, rssi: the app's 'ppxr_wfb_*' counters (one sample per ~300 ms wfb-ng stats interval,
  written by WfbStatsTrace). rx = packets received over the air, data + FEC parity; wfb_lost = still missing after FEC.
- rssi A/B, snr A/B: the per-receive-chain counters 'ppxr_wfb_rssi_a/_b', 'ppxr_wfb_snr_a/_b' (app builds from
  2026-09-28 on; '-' in older traces). RSSI in the adapter's raw units (1 unit = 1 dB), SNR converted to dB (raw
  rxsnr is 0.5 dB units). They show which Quest antenna carries the signal; 'rssi' is the mapped best chain.
- data_loss_pct ("dataFEC%"): the fraction of DATA packets missing before FEC, from Quest counters only, all in the
  same guarded window: (FEC repairs + RTP sequence gaps) / (RTP packets received + gaps). Use this one: it needs no
  air counter and no cross-device window (link-25mbit audit H5 §1.3, 2026-09-28).
- tx/s and pre-FEC loss: the air loop writes the cumulative wlan0 tx_packets on every step line
  ("<air epoch> <label> tx=<n> temp=<C>", END line too). tx/s = delta over the whole step on the air clock;
  pre_fec_loss = 1 - rx/s / tx/s. Anything else the air unit transmits on wlan0 counts as sent video, so this is an
  upper bound [INFERRED]. It also divides a guarded Quest window by the air's whole step, which shifts it by up to
  ±2 points after a bitrate change (audit H5 §1.3); kept for comparison with older CSVs, prefer data_loss_pct.
- air_c: the air SoC temperature from the same step line. Quest thermal: --thermal CSV from quest_thermal_log.sh.

- Q tx/s: the Quest RTL's uplink injections (adaptive link, tunnel) from --quest-tx (quest_tx_log.sh); ~0 when the
  adaptive link is off, so it also shows whether a pref A/B step really applied.

Usage: python3 ab_link.py trace.pftrace steps.txt --air-offset-s S [--guard-s 2] [--thermal thermal.csv]
       [--quest-tx quest_tx.txt] [--csv out.csv]
  --air-offset-s  the offset ab_segments.py used (after --fit-offset, the fitted value it printed).
"""
import argparse
import csv
import statistics as st
from collections import OrderedDict

from ab_segments import read_steps, step_window
from rtp_seq import seq_loss

# Levels (averages over the last second), not counts: a stale repeat of one is dropped, not zeroed.
LEVEL_COUNTERS = ("ppxr_wfb_rssi", "ppxr_wfb_rssi_a", "ppxr_wfb_rssi_b", "ppxr_wfb_snr_a", "ppxr_wfb_snr_b")
WFB_COUNTERS = ("ppxr_wfb_p_all", "ppxr_wfb_fec_rec", "ppxr_wfb_lost") + LEVEL_COUNTERS
SNR_UNIT_DB = 0.5  # rxsnr in the RTL8812AU PHY status is s(8,1)


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


def drop_stale(counters, rtp_ts):
    """The app clears the wfb-ng counts only when its RX loop handles a video packet (WfbngLink.cpp, should_clear_stats),
    so while nothing arrives each ~300 ms poll repeats the last interval's counts. A sample with no RTP arrival since
    the previous sample is such a repeat: its counts become 0 and its levels (RSSI, SNR) are dropped.
    rtp_ts: sorted arrival times."""
    from bisect import bisect_right
    out = {}
    for name, samples in counters.items():
        fixed, prev = [], None
        for t, v in samples:
            fresh = prev is None or bisect_right(rtp_ts, t) > bisect_right(rtp_ts, prev)
            if fresh:
                fixed.append((t, v))
            elif name not in LEVEL_COUNTERS:
                fixed.append((t, 0))
            prev = t
        out[name] = fixed
    return out


def window_stats(samples, a, b, per_second):
    """samples [(ts, value)] sorted; sum/s (per_second) or mean of the values with a <= ts < b; None if empty."""
    vals = [v for t, v in samples if a <= t < b]
    if not vals:
        return None
    return sum(vals) / ((b - a) / 1e9) if per_second else st.mean(vals)


def data_loss_pct(counters, a, b):
    """Share of data packets missing before FEC in [a, b): (FEC repairs + RTP gaps) / (RTP received + gaps).
    counters["rtp"] = [(ts, rtp_seq)] in arrival order; None without RTP events in the window."""
    seqs = [v for t, v in counters.get("rtp", []) if a <= t < b]
    if not seqs:
        return None
    lost = seq_loss(seqs)[0]
    fec = sum(v for t, v in counters.get("ppxr_wfb_fec_rec", []) if a <= t < b)
    return 100.0 * (fec + lost) / (len(seqs) + lost)


def scaled(v, k):
    return None if v is None else v * k


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
            "rssi_a": window_stats(counters.get("ppxr_wfb_rssi_a", []), a, b, False),
            "rssi_b": window_stats(counters.get("ppxr_wfb_rssi_b", []), a, b, False),
            "snr_a_db": scaled(window_stats(counters.get("ppxr_wfb_snr_a", []), a, b, False), SNR_UNIT_DB),
            "snr_b_db": scaled(window_stats(counters.get("ppxr_wfb_snr_b", []), a, b, False), SNR_UNIT_DB),
            # Quest RTL uplink injections; 0 frames in the window is a real 0 when the log was recorded
            "quest_tx_per_s": ((window_stats(counters["quest_tx"], a, b, True) or 0.0)
                               if "quest_tx" in counters else None),
            "tx_per_s": tx[i] if i < len(tx) else None,
            "air_c": fields[i].get("temp") if i < len(fields) else None,
        }
        r["pre_fec_loss_pct"] = (100.0 * (1 - r["rx_per_s"] / r["tx_per_s"])
                                 if r["rx_per_s"] is not None and r["tx_per_s"] else None)
        r["data_loss_pct"] = data_loss_pct(counters, a, b)
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


def load(path, air_offset_s, steps_path, thermal_path, quest_tx_path=None):
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    counters = {n: [(r.ts, r.value) for r in q(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        f"where t.name='{n}' order by c.ts")] for n in WFB_COUNTERS}
    rtp = [(r.ts, int(r.value)) for r in q("select c.ts, c.value from counter c join counter_track t "
                                           "on c.track_id=t.id where t.name='ppxr_rtp_seq' order by c.ts")]
    counters = drop_stale(counters, [t for t, _ in rtp])
    counters["rtp"] = rtp
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
    if quest_tx_path:  # one Quest epoch per injected frame (quest_tx_log.sh)
        counters["quest_tx"] = [(float(x) * 1e9 - rt_off, 1) for x in open(quest_tx_path, encoding="utf-8")
                                if x.strip()]
    return counters, thermal, read_step_fields(steps_path), steps, end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=2.0)
    ap.add_argument("--thermal", help="CSV from quest_thermal_log.sh")
    ap.add_argument("--quest-tx", help="file from quest_tx_log.sh (Quest uplink injections)")
    ap.add_argument("--csv", help="also write the per-step rows to this CSV file")
    a = ap.parse_args()
    counters, thermal, fields, steps, end = load(a.trace, a.air_offset_s, a.steps, a.thermal, a.quest_tx)
    if not counters["ppxr_wfb_p_all"]:
        print("no ppxr_wfb_* counters in the trace (app build without WfbStatsTrace?)")
    rows = per_step(counters, thermal, fields, steps, end, a.guard_s * 1e9)
    keys = ["tx_per_s", "rx_per_s", "pre_fec_loss_pct", "fec_rec_per_s", "wfb_lost_per_s", "rssi",
            "rssi_a", "rssi_b", "snr_a_db", "snr_b_db", "quest_tx_per_s", "air_c", "quest_cpu_max_c", "quest_status_max", "quest_batt",
            "data_loss_pct"]  # append only: older link CSVs keep their column order
    heads = ["tx/s", "rx/s", "preFEC%", "fec/s", "lost/s", "rssi", "rssi A", "rssi B", "snrA dB", "snrB dB", "Q tx/s", "air°C", "Q cpu°C", "Q st", "batt", "dataFEC%"]
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
