"""PPXR_FECBLK lines (one per video FEC block the Quest could not recover) -> a per-block TSV and a summary.

Usage: python3 fec_blocks.py <detached logcat> [--tsv blocks.tsv]
           [--air-log wfbtx.log --quest-minus-pc-ms Q --air-minus-pc-ms A]

The app logs a line per unrecoverable block (app/wfbngrtl8812/.../FecBlockProbe.h; docs/xr/fec-block-probe.md):
got = the fragment bitmap (index 0..n-1), frags = idx:dt_us:rssiA:rssiB (raw), span_us, gap_max_us (the longest gap
between received frames while the block was pending), fcs (bad-FCS frames around it; "-" = not visible, keep_corrupted
off), reason (flush / ring). Capture DETACHED (scripts/quest/ab_detached.sh includes the tag), never streamed.

Per block: missing count, missing data fragments (< k), where the holes sit (head / middle / tail, or scattered for
several holes inside the received span), mean RSSI A/B in dBm (raw - 110, devourer src/LinkHealth.cpp:8).
Summary: blocks and per minute, outages (gap_max >= OUTAGE_US), blocks with bad FCS, hole positions, reasons,
gap_max p50/p95, RSSI means, suppressed lines.

Air join (--air-log <the air's /tmp/wfbtx.log> --quest-minus-pc-ms Q --air-minus-pc-ms A): marks each block Y / N by
whether the air's wfb_tx dropped packets at injection in the same log interval (1 s), "?" when the air log does not
cover it. Clocks: the capture's logcat epoch (Quest wall) - Q = PC wall; + A = the air's get_time_ms (A = air ms minus
PC epoch ms). The summary then gives the share of lost blocks the air drops explain.
"""
import sys
from collections import Counter

from stats_log import parse_kv

TAG = " PPXR_FECBLK: "
TAB = "\t"
OUTAGE_US = 2000     # a gap this long means no frame at all arrived: the air not sending or the RX deaf
RSSI_DBM_OFFSET = 110


def _where(got):
    received = [i for i, c in enumerate(got) if c == "1"]
    if not received:
        return "all"
    first, last = received[0], received[-1]
    runs, prev = 0, "1"
    for c in got:
        if c == "0" and prev == "1":
            runs += 1
        prev = c
    middle = any(got[i] == "0" for i in range(first, last + 1))
    if middle and runs >= 2:
        return "scattered"
    parts = [name for name, hit in (("head", first > 0), ("middle", middle), ("tail", last < len(got) - 1)) if hit]
    return "+".join(parts) if parts else "none"


def parse(line):
    i = line.find(TAG)
    if i < 0:
        return None
    kv = parse_kv(line[i + len(TAG):])
    if "blk" not in kv or "got" not in kv:
        return None
    k, got = int(kv["k"]), kv["got"]
    frags = [f.split(":") for f in kv.get("frags", "").split(",") if f]
    ra = [int(f[2]) - RSSI_DBM_OFFSET for f in frags if len(f) == 4]
    rb = [int(f[3]) - RSSI_DBM_OFFSET for f in frags if len(f) == 4]
    return {
        "t_mono_ms": int(kv["t_mono_ms"]), "blk": int(kv["blk"]), "k": k, "n": int(kv["n"]), "got": got,
        "missing": got.count("0"),
        "missing_data": [i for i in range(min(k, len(got))) if got[i] == "0"],
        "where": _where(got),
        "span_us": int(kv.get("span_us") or 0), "gap_max_us": int(kv.get("gap_max_us") or 0),
        "rssi_a_dbm": sum(ra) / len(ra) if ra else None, "rssi_b_dbm": sum(rb) / len(rb) if rb else None,
        "fcs": int(kv["fcs"]) if kv.get("fcs") else None,
        "reason": kv.get("reason", ""), "suppressed": int(kv.get("suppressed") or 0),
    }


def _blocks(lines):
    return [b for b in (parse(line) for line in lines) if b]


def parse_air_log(lines):
    """[(start_ms, end_ms, dropped)] from the air's wfb_tx PKT lines: ts TAB PKT TAB
    fec_timeouts:incoming:b_in:injected:b_inj:dropped:truncated (wfb-ng tx.cpp:729-730). The counters are per log
    interval, so a line covers (previous ts, ts]."""
    out, prev = [], None
    for line in lines:
        f = line.rstrip("\n").split(TAB)
        if len(f) < 3 or f[1] != "PKT":
            continue
        ts, c = int(f[0]), f[2].split(":")
        if prev is not None and len(c) >= 6:
            out.append((prev, ts, int(c[5])))
        prev = ts
    return out


def _epoch_ms(line):
    head = line.split(None, 1)
    try:
        return float(head[0]) * 1000.0
    except (ValueError, IndexError):
        return None


def join_air(lines, air_lines, quest_minus_pc_ms, air_minus_pc_ms):
    """The blocks, each with air_drop = Y / N (the air dropped packets in the same interval or not) / ? (not covered)."""
    intervals = parse_air_log(air_lines)
    out = []
    for line in lines:
        b = parse(line)
        if b is None:
            continue
        wall = _epoch_ms(line)
        mark = "?"
        if wall is not None:
            air_ms = wall - quest_minus_pc_ms + air_minus_pc_ms
            for start, end, dropped in intervals:
                if start < air_ms <= end:
                    mark = "Y" if dropped > 0 else "N"
                    break
        b["air_drop"] = mark
        out.append(b)
    return out


COLUMNS = ["t_mono_ms", "blk", "k", "n", "got", "missing", "missing_data", "where", "span_us", "gap_max_us",
           "rssi_a_dbm", "rssi_b_dbm", "fcs", "reason"]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return ",".join(map(str, v))
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def to_tsv(lines, air=None):
    cols = COLUMNS + (["air_drop"] if air else [])
    out = [TAB.join(cols)]
    for b in (join_air(lines, *air) if air else _blocks(lines)):
        out.append(TAB.join(_cell(b[c]) for c in cols))
    return "\n".join(out) + "\n"


def _pct(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))] if v else None


def _air_summary(blocks):
    y = sum(1 for b in blocks if b["air_drop"] == "Y")
    n = sum(1 for b in blocks if b["air_drop"] == "N")
    return {"air_drop_Y": y, "air_drop_N": n, "air_drop_unknown": len(blocks) - y - n,
            "air_drop_share": y / (y + n) if y + n else float("nan")}


def summarize(lines, air=None):
    """air = (air log lines, quest_minus_pc_ms, air_minus_pc_ms) adds the air-drop share."""
    blocks = join_air(lines, *air) if air else _blocks(lines)
    t = [b["t_mono_ms"] for b in blocks]
    dur_s = (max(t) - min(t)) / 1000.0 if len(t) > 1 else 0.0
    gaps = [b["gap_max_us"] for b in blocks]
    known = [b for b in blocks if b["fcs"] is not None]
    ra = [b["rssi_a_dbm"] for b in blocks if b["rssi_a_dbm"] is not None]
    summary = {
        "blocks": len(blocks),
        "per_min": len(blocks) * 60.0 / dur_s if dur_s else 0.0,
        "outage": sum(1 for g in gaps if g >= OUTAGE_US),
        "with_fcs": sum(1 for b in known if b["fcs"] > 0),
        "fcs_known": len(known),
        "where": dict(Counter(b["where"] for b in blocks)),
        "reason": dict(Counter(b["reason"] for b in blocks)),
        "gap_max_us_p50": _pct(gaps, 0.5),
        "gap_max_us_p95": _pct(gaps, 0.95),
        "rssi_a_dbm_mean": sum(ra) / len(ra) if ra else None,
        "suppressed": sum(b["suppressed"] for b in blocks),
    }
    if air:
        summary.update(_air_summary(blocks))
    return summary


def _take(args, flag):
    i = args.index(flag)
    value = args[i + 1]
    del args[i:i + 2]
    return value


def main():
    args = sys.argv[1:]
    tsv = _take(args, "--tsv") if "--tsv" in args else None
    air = None
    if "--air-log" in args:
        with open(_take(args, "--air-log"), encoding="utf-8", errors="replace") as fh:
            air_lines = fh.readlines()
        air = (air_lines, float(_take(args, "--quest-minus-pc-ms")), float(_take(args, "--air-minus-pc-ms")))
    lines = []
    for path in args:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines.extend(fh)
    if tsv:
        with open(tsv, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(to_tsv(lines, air))
        print(f"blocks -> {tsv}")
    for k, v in summarize(lines, air).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
