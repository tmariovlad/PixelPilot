"""The app's health log (PPXR_EVENT per notable event, PPXR_HEALTH every 10 s) -> an event timeline and a summary.

Usage: python3 health_log.py <file> [<file> ...] [--tsv timeline.tsv]

Input: files/ppxr_health.log (+ .1) pulled from the Quest
  (adb exec-out run-as com.openipc.pixelpilot.xr cat files/ppxr_health.log), whose lines are "TAG k=v ...", or a
detached logcat capture (scripts/quest/ab_detached.sh), whose lines are "<epoch> <pid> <tid> I TAG: k=v ...".
Every line carries t_mono_ms (Quest CLOCK_MONOTONIC, the traces' clock), t_wall_ms, code and level
(app stats/HealthMonitor.java defines them; docs/xr/health-logging.md lists the codes).
Summary: duration, SIGNAL_LOST count and per minute, causes, time lost, the kinds entered, freeze % of the time,
headset-off time, IDR failure reasons, mean fps / frozen % of the HEALTH lines.
"""
import sys
from collections import Counter

from stats_log import parse_kv

TAGS = ("PPXR_EVENT", "PPXR_HEALTH")


def parse(line):
    """(tag, {k: v}) for a health line in either the file or the logcat format, else None."""
    for tag in TAGS:
        if line.startswith(tag + " "):
            return tag, parse_kv(line[len(tag) + 1:])
        i = line.find(" " + tag + ": ")
        if i >= 0:
            return tag, parse_kv(line[i + len(tag) + 3:])
    return None


def _records(lines):
    out = [p for p in (parse(line.rstrip("\n")) for line in lines) if p and p[1].get("t_mono_ms")]
    return sorted(out, key=lambda p: int(p[1]["t_mono_ms"]))


def timeline(lines):
    """TSV: t_mono_ms, t_wall_ms, tag, code, level, then the remaining k=v pairs as one detail column."""
    fixed = ("t_mono_ms", "t_wall_ms", "code", "level")
    rows = ["\t".join(["t_mono_ms", "t_wall_ms", "tag", "code", "level", "detail"])]
    for tag, kv in _records(lines):
        detail = " ".join(f"{k}={v}" for k, v in kv.items() if k not in fixed)
        rows.append("\t".join([kv.get("t_mono_ms", ""), kv.get("t_wall_ms", ""), tag, kv.get("code", ""),
                               kv.get("level", ""), detail]))
    return "\n".join(rows) + "\n"


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def summarize(lines):
    recs = _records(lines)
    t = [int(kv["t_mono_ms"]) for _, kv in recs]
    duration_s = (t[-1] - t[0]) / 1000.0 if len(t) > 1 else 0.0
    events = [kv for tag, kv in recs if tag == "PPXR_EVENT"]
    health = [kv for tag, kv in recs if tag == "PPXR_HEALTH"]
    lost = [e for e in events if e.get("code") == "SIGNAL_LOST"]
    reasons = Counter()
    for e in events:
        if e.get("code") == "IDR_FAILED":
            for k in ("refused", "connect_timeout", "reply_timeout", "http_status", "error"):
                if k in e:
                    reasons[k] += int(_num(e[k]))
    # IdrRequester's connect race (2026-09-29): SYNs started, requests won by a later attempt, and the connect time
    # per request (each line gives its mean over `connected` requests)
    idr = [e for e in events if e.get("code") in ("IDR", "IDR_FAILED")]
    connected = sum(int(_num(e.get("connected"))) for e in idr)
    connect_ms = sum(_num(e.get("connect_ms")) * int(_num(e.get("connected"))) for e in idr)
    fps = [_num(h["fps"]) for h in health if h.get("fps")]
    frozen = [_num(h["frozen_pct"]) for h in health if h.get("frozen_pct")]
    freeze_ms = sum(_num(e.get("dur_ms")) for e in events if e.get("code") == "FREEZE_END")
    return {
        "duration_s": duration_s,
        "signal_lost": len(lost),
        "alerts": sum(1 for e in events if e.get("level") == "ALERT"),
        "stalls_per_min": len(lost) * 60.0 / duration_s if duration_s else 0.0,
        "causes": dict(Counter(e.get("cause", "") for e in lost)),
        "by_kind": dict(Counter(e.get("to", "") for e in lost)),
        "lost_ms": int(sum(_num(e.get("dur_ms")) for e in events if e.get("code") == "SIGNAL_OK")),
        "freeze_pct": 100.0 * freeze_ms / (duration_s * 1000.0) if duration_s else 0.0,
        "session_off_ms": int(sum(_num(e.get("off_ms")) for e in events if e.get("code") == "SESSION_ACTIVE")),
        "adapter_gone_ms": [int(_num(e.get("gone_ms"))) for e in events if e.get("code") == "ADAPTER_BACK"],
        "idr_fail_reasons": dict(reasons),
        "idr_attempts": sum(int(_num(e.get("attempts"))) for e in idr),
        "idr_won_late": sum(int(_num(e.get("late"))) for e in idr),
        "idr_connect_ms_mean": connect_ms / connected if connected else float("nan"),
        "health_fps_mean": sum(fps) / len(fps) if fps else float("nan"),
        "health_frozen_pct_mean": sum(frozen) / len(frozen) if frozen else float("nan"),
    }


def main():
    args = sys.argv[1:]
    tsv = None
    if "--tsv" in args:
        i = args.index("--tsv")
        tsv = args[i + 1]
        del args[i:i + 2]
    lines = []
    for path in args:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines.extend(fh)
    if tsv:
        with open(tsv, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(timeline(lines))
        print(f"timeline -> {tsv}")
    for k, v in summarize(lines).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
