"""Post-hunt timeline for the HD 71 ms hunt: every rig step event (first light stepping up, first_light_steps.detect)
with +-60 s of context from the other sources, merged in time order on the PC clock.

Sources (each optional except the rig):
- rig: latency-test's per_flash.csv (0d; pc_epoch, step label, first light) -> step events, as first_light_steps.py /
  first_light_follow.py detect them (--fixed hd=46 for a run that may start in the state); runs_summary.txt lines
  ("<run> <end|abort|timeout|interrupted> start <epoch> end <epoch>", latency-test scripts/live_capture.py) as context.
- air: openipc-40's air_health.log EV lines (t = air epoch; code=SNAP trig=... among them; the 2 s AH samples are
  left out), and the snapshot file names "<air epoch>_<trig>.txt" of a pulled /tmp/air_health.snap/.
- quest: the app's ppxr_health.log (or a detached logcat): PPXR_EVENT on its own t_wall_ms, PPXR_STATS (a key subset)
  on t mono ms mapped to wall by the latest PPXR_EVENT pair of the same Quest boot (mono restarts on a reboot).
- wd: the waybeam watchdog log, every line ("[wd HH:MM:SS] ...": DEGRADAT, SKIP [STALLED], restarts). The stamp has
  no date, so --wd-date (the air's date at the first line) and --wd-utc-offset-h (air local - UTC; the air ran UTC on
  2026-09-30) place it; a time that goes backwards is the next day.

Clocks: PC = air + --pc-minus-air-s (ntpd, ~+0.05 s); PC = Quest wall - --quest-minus-pc-s (ab_detached's meta).

Usage: python3 hunt_timeline.py per_flash.csv [more.csv ...] --fixed hd=46 [--runs runs_summary.txt]
         [--air-health air_health.log] [--snap-dir DIR] [--quest ppxr_health.log ...]
         [--wd waybeam-watchdog.log --wd-date 2026-10-01 [--wd-utc-offset-h 0]]
         [--pc-minus-air-s 0.05] [--quest-minus-pc-s -0.28] [--context-s 60] [--stats-keys tot50,lnk50,...]
"""
import argparse
import calendar
import os
import re

import first_light_steps as fls
from health_log import parse as parse_health
from stats_log import parse_kv

STATS_KEYS = ("tot50", "lnk50", "enc50", "dec50", "fps", "post", "n")
_WD = re.compile(r"^\[wd (\d\d):(\d\d):(\d\d)\] ?(.*)$")
_SNAP = re.compile(r"^(\d+(?:\.\d+)?)_(.+)\.txt$")
_STATS_TAG = "PPXR_STATS"
# a PPXR_STATS line may be logged a little before the PPXR_EVENT that precedes it in the file; further back than this
# its mono restarted, i.e. another Quest boot
SAME_BOOT_SLACK_MS = 10_000


def runs_summary(lines):
    """[(pc, "rig", "<run> start" / "<run> <status>")] from latency-test's runs_summary.txt."""
    rows = []
    for line in lines:
        w = line.split()
        if len(w) == 6 and w[2] == "start" and w[4] == "end":
            rows += [(float(w[3]), "rig", f"{w[0]} start"), (float(w[5]), "rig", f"{w[0]} {w[1]}")]
    return rows


def air_health(lines, pc_minus_air_s):
    """[(pc, "air", line)] of the EV lines (their t = air epoch)."""
    rows = []
    for line in lines:
        if line.startswith("EV "):
            t = parse_kv(line).get("t")
            if t:
                rows.append((float(t) + pc_minus_air_s, "air", line.strip()))
    return rows


def snapshots(names, pc_minus_air_s):
    """[(pc, "snap", name)] for "<air epoch>_<trig>.txt" names."""
    rows = []
    for name in names:
        m = _SNAP.match(os.path.basename(name))
        if m:
            rows.append((float(m.group(1)) + pc_minus_air_s, "snap", os.path.basename(name)))
    return sorted(rows)


def watchdog(lines, date, utc_offset_h, pc_minus_air_s):
    """[(pc, "wd", text)]: "[wd HH:MM:SS]" on the given air date (air local = UTC + utc_offset_h); a stamp earlier
    than the previous one is the next day."""
    y, mo, d = (int(x) for x in date.split("-"))
    day0 = calendar.timegm((y, mo, d, 0, 0, 0)) - utc_offset_h * 3600
    rows, day, prev = [], 0, None
    for line in lines:
        m = _WD.match(line.rstrip("\r\n"))
        if not m:
            continue
        sod = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if prev is not None and sod < prev:
            day += 1
        prev = sod
        rows.append((day0 + day * 86400 + sod + pc_minus_air_s, "wd", m.group(4)))
    return rows


def _stats_kv(line):
    """{k: v} of a PPXR_STATS line in the file ("PPXR_STATS k=v") or the logcat ("... PPXR_STATS: k=v") format."""
    if line.startswith(_STATS_TAG + " "):
        return parse_kv(line[len(_STATS_TAG) + 1:])
    i = line.find(" " + _STATS_TAG + ": ")
    return parse_kv(line[i + len(_STATS_TAG) + 3:]) if i >= 0 else None


def quest(lines, quest_minus_pc_s, stats_keys):
    """[(pc, "quest", event line) / (pc, "stats", "k=v ...")] in file order. PPXR_STATS carry only mono t: they take
    wall - mono from the latest PPXR_EVENT pair; a mono smaller than that pair's is another boot, so it waits for
    the next pair."""
    rows, off, pair_mono = [], None, None
    for line in lines:
        h = parse_health(line.rstrip("\r\n"))
        if h:
            kv = h[1]
            if kv.get("t_mono_ms") and kv.get("t_wall_ms"):
                pair_mono = int(kv["t_mono_ms"])
                off = int(kv["t_wall_ms"]) - pair_mono
                text = " ".join(f"{k}={v}" for k, v in kv.items() if k not in ("t_mono_ms", "t_wall_ms"))
                rows.append((int(kv["t_wall_ms"]) / 1000.0 - quest_minus_pc_s, "quest", f"{h[0]} {text}"))
            continue
        kv = _stats_kv(line)
        if kv is None or not kv.get("t") or off is None or pair_mono is None:
            continue
        if int(kv["t"]) < pair_mono - SAME_BOOT_SLACK_MS:
            continue
        text = " ".join(f"{k}={kv[k] if kv[k] != '' else '-'}" for k in stats_keys if k in kv)
        rows.append(((int(kv["t"]) + off) / 1000.0 - quest_minus_pc_s, "stats", text))
    return rows


def timeline(events, rows, ctx_s):
    """[(event, [rows within [start - ctx, end + ctx], time order])]."""
    rows = sorted(rows)
    return [(e, [r for r in rows if e.start - ctx_s <= r[0] <= e.end + ctx_s]) for e in events]


def render(blocks, ctx_s):
    out = []
    for e, rows in blocks:
        out.append(f"\n=== STEP {e.label} {e.start:.1f}-{e.end:.1f} ({e.end - e.start:.0f} s) n={e.n} "
                   f"median {e.median_ms:.1f} ms vs {e.baseline_ms:.1f} ms (+{e.median_ms - e.baseline_ms:.1f}); "
                   f"context +-{ctx_s:g} s, t = s from the step start (PC clock)")
        marks = [(e.start, "", ">>> step start"), (e.end, "", "<<< step end (last high flash)")]
        for t, src, text in sorted(rows + marks, key=lambda r: (r[0], r[1] != "")):
            out.append(f"{t - e.start:+8.1f}  {src:5s}  {text}")
    return "\n".join(out)


def run(per_flash, fixed, runs, air_health_log, snap_names, quest_logs, wd_log, wd_date, wd_utc_offset_h,
        pc_minus_air_s, quest_minus_pc_s, ctx_s, stats_keys):
    flashes = fls.read_per_flash(per_flash)
    events = fls.detect(flashes, fixed=fls._fixed(fixed))
    rows = []

    def lines(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()

    if runs:
        rows += runs_summary(lines(runs))
    if air_health_log:
        rows += air_health(lines(air_health_log), pc_minus_air_s)
    rows += snapshots(snap_names, pc_minus_air_s)
    for q in quest_logs:
        rows += quest(lines(q), quest_minus_pc_s, stats_keys)
    if wd_log:
        if not wd_date:
            raise SystemExit("--wd needs --wd-date (the air's date at the log's first line)")
        rows += watchdog(lines(wd_log), wd_date, wd_utc_offset_h, pc_minus_air_s)
    head = (f"# hunt_timeline: rig {', '.join(per_flash)} ({len(flashes)} ok flashes, --fixed {fixed or '-'}) | "
            f"runs {runs or '-'} | air_health {air_health_log or '-'} | snaps {len(snap_names)} | "
            f"quest {', '.join(quest_logs) or '-'} | wd {wd_log or '-'}"
            f"{' @' + wd_date + f' UTC{wd_utc_offset_h:+g}' if wd_log else ''} | PC-air {pc_minus_air_s:+g} s | "
            f"Quest-PC {quest_minus_pc_s:+g} s\n# {len(events)} step event(s); {len(rows)} context rows read")
    return head + render(timeline(events, rows, ctx_s), ctx_s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("per_flash", nargs="+")
    ap.add_argument("--fixed", default="", help="per-label first-light reference, e.g. hd=46 (first_light_steps)")
    ap.add_argument("--runs", help="latency-test runs_summary.txt")
    ap.add_argument("--air-health", help="air_health.log (EV lines)")
    ap.add_argument("--snap-dir", help="a pulled /tmp/air_health.snap/ (file names only)")
    ap.add_argument("--quest", nargs="*", default=[], help="ppxr_health.log(.1) or a detached logcat")
    ap.add_argument("--wd", help="waybeam watchdog log")
    ap.add_argument("--wd-date", help="YYYY-MM-DD, the air's date at the watchdog log's first line")
    ap.add_argument("--wd-utc-offset-h", type=float, default=0.0, help="air local time - UTC (h)")
    ap.add_argument("--pc-minus-air-s", type=float, default=0.0)
    ap.add_argument("--quest-minus-pc-s", type=float, default=0.0)
    ap.add_argument("--context-s", type=float, default=60.0)
    ap.add_argument("--stats-keys", default=",".join(STATS_KEYS))
    a = ap.parse_args()
    snaps = sorted(os.listdir(a.snap_dir)) if a.snap_dir else []
    print(run(a.per_flash, a.fixed, a.runs, a.air_health, snaps, a.quest, a.wd, a.wd_date, a.wd_utc_offset_h,
              a.pc_minus_air_s, a.quest_minus_pc_s, a.context_s, tuple(a.stats_keys.split(","))))


if __name__ == "__main__":
    main()
