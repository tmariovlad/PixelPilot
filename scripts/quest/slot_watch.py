"""Slot monitoring on the PC: the air unit during a slot, the Quest between measurements, and a timeline at the end.
The coordinator starts it; every alert is one line on stdout (follow it with Monitor) and in an alerts file.

Usage:
  slot_watch.py watch   [--interval 5] [--duration S] [--expect channel=157 --expect txpower=12 ...] [--alerts F]
      Reads the air over eth0 (ssh alias `air`, one read-only `sh -s` of air_probe.sh per poll) until Ctrl-C or
      --duration. Never touches the Quest: adb over Wi-Fi during a measurement costs the RTL packets
      (docs/xr/troubleshooting.md, U1). Exit 1 if any ALERT was raised, else 0.
  slot_watch.py between [--expect guardian_pause=1 --expect prox=CLOSE] [--alerts F]
      One pass over the Quest, only between measurements: awake, XR app running, Guardian/proximity as planned,
      the RTL8812AU (0bda:8812) attached, free storage, battery. Exit 1 if any ALERT.
  slot_watch.py report  --alerts F [--since EPOCH] [--until EPOCH] [--no-quest] [--no-air] [--periodic]
      The slot's timeline: the alerts file + the app's PPXR_EVENT/PPXR_HEALTH (files/ppxr_health.log on the Quest,
      pixelpilot-xr-36) + the air's air_health log (openipc-…-40), on PC time, written next to the alerts file.

Alert line: `<local ISO time> <LEVEL> <source> <CODE> k=v ...`, LEVEL = ALERT | WARN | INFO. Conditions are
edge-triggered: one line when a condition starts (or escalates), one INFO `<CODE>_OK` when it clears.
Codes and the DPS-150 checklist: docs/xr/slot-watch.md.
"""
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import quest_env as env

AIR_PROBE = os.path.join(env.HERE, "air_probe.sh")
AIR_HOST = os.environ.get("AIR_SSH", "air")          # ~/.ssh/config alias of 192.168.100.132 (key auth)
RTL_ID = "0bda:8812"
LEVELS = ("INFO", "WARN", "ALERT")


# ---------------------------------------------------------------- alerts

@dataclass
class Alert:
    t: float                  # PC epoch seconds
    level: str
    source: str               # air | quest | watch
    code: str
    detail: dict = field(default_factory=dict)

    def line(self):
        ts = datetime.datetime.fromtimestamp(self.t).isoformat(timespec="milliseconds")
        kv = " ".join(f"{k}={_token(v)}" for k, v in self.detail.items())
        return f"{ts} {self.level} {self.source} {self.code}" + (f" {kv}" if kv else "")

    @staticmethod
    def parse(line):
        parts = line.split()
        t = datetime.datetime.fromisoformat(parts[0]).timestamp()
        return Alert(t, parts[1], parts[2], parts[3], dict(p.split("=", 1) for p in parts[4:] if "=" in p))


def _token(v):
    s = "-" if v is None else str(v)
    return re.sub(r"\s+", "_", s.strip()) or "-"


class Conditions:
    """Edge-triggered conditions: report a condition when it starts or changes level, and <CODE>_OK when it ends."""

    def __init__(self):
        self.active = {}      # code -> level

    def set(self, t, source, code, level, detail=None):
        """level None = the condition is not present."""
        was = self.active.get(code)
        if level is None:
            if was is None:
                return []
            del self.active[code]
            return [Alert(t, "INFO", source, code + "_OK", detail or {})]
        if was == level:
            return []
        self.active[code] = level
        return [Alert(t, level, source, code, detail or {})]


# ---------------------------------------------------------------- air

def _num(s, cast=float):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def parse_air_probe(text):
    """air_probe.sh output -> a sample dict; a missing or empty source is None."""
    raw = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            raw[k.strip()] = v.strip()
    s = {
        "now": _num(raw.get("now"), int), "uptime": _num(raw.get("uptime")), "boot_id": raw.get("boot_id") or None,
        "temp": _num(raw.get("temp"), int), "tx_packets": _num(raw.get("tx_packets"), int),
        "wfb_lines": _num(raw.get("wfb_lines"), int), "wfb_drop": _num(raw.get("wfb_drop"), int),
        "wfb_inj": _num(raw.get("wfb_inj"), int), "wfb_pkt_lines": _num(raw.get("wfb_pkt_lines"), int),
        "cfg_bitrate": _num(raw.get("cfg_bitrate"), int), "cfg_fps": _num(raw.get("cfg_fps"), int),
        "fps": None, "kbps": None, "idr_honoured": None, "idr_dropped": None, "mcs": None, "fec": None,
        "channel": None, "txpower": None, "bcn_550": None,
    }
    m = re.search(r"\|\s*([\d.]+)\s*fps\s*\|\s*(\d+)\s*kbps", raw.get("wb_verbose", ""))
    if m:
        s["fps"], s["kbps"] = float(m.group(1)), int(m.group(2))
    s["idr_honoured"], s["idr_dropped"] = _idr_counts(raw.get("idr_stats", ""))
    radio = dict(re.findall(r"(\w+)=(\S+)", raw.get("radio", "")))
    s["mcs"] = _num(radio.get("mcs_index"), int)
    m = re.search(r"k=(\d+)\s+n=(\d+)", raw.get("fec", ""))
    s["fec"] = f"{m.group(1)}/{m.group(2)}" if m else None
    m = re.search(r"channel (\d+)", raw.get("iw", ""))
    s["channel"] = int(m.group(1)) if m else None
    m = re.search(r"txpower ([\d.]+) dBm", raw.get("iw", ""))
    s["txpower"] = float(m.group(1)) if m else None
    m = re.search(r"bcn_off 0x550 0x[0-9a-fA-F]+ -> (0x[0-9a-fA-F]+)", raw.get("bcn", ""))
    s["bcn_550"] = m.group(1).lower() if m else None
    return s


def _idr_counts(text):
    """waybeam /api/v1/idr/stats -> (honoured, dropped) summed over channels; (None, None) if absent."""
    try:
        d = json.loads(text)
    except ValueError:
        return None, None
    chans = d.get("data", d).get("channels", [d.get("data", d)])
    h = sum(c.get("honored", c.get("honoured", 0)) for c in chans)
    dr = sum(c.get("dropped", 0) for c in chans)
    return h, dr


@dataclass
class Thresholds:
    idr_per_s_max: float = 2.0       # honoured + dropped key-frame requests per second
    fps_frac: float = 0.975          # waybeam fps below this share of the configured fps (90 -> 87.75, 167 -> 162.8)
    fps_min: Optional[float] = None  # absolute override
    temp_warn: int = 60              # bitrate_grid.sh TEMP_SKIP
    temp_alert: int = 70             # bitrate_grid.sh TEMP_STOP
    drop_max: int = 0                # wfb_tx p_drop per poll
    unreachable_after: int = 2       # consecutive failed polls
    storage_min_mb: int = 2048
    battery_min: int = 30            # link-envelope.md stop rule


# expect key -> (sample key, alert code)
AIR_EXPECT = {"channel": ("channel", "AIR_CHANNEL"), "txpower": ("txpower", "AIR_TXPOWER"), "mcs": ("mcs", "AIR_MCS"),
              "fec": ("fec", "AIR_FEC"), "bitrate": ("cfg_bitrate", "AIR_BITRATE"), "fps": ("cfg_fps", "AIR_CFG_FPS")}


def _same(a, b):
    fa, fb = _num(a), _num(b)
    return fa == fb if fa is not None and fb is not None else str(a) == str(b)


class AirWatch:
    """The air's alert rules over consecutive samples. update(None) = the poll failed."""

    def __init__(self, th, expect=None):
        self.th, self.expect = th, dict(expect or {})
        self.cond = Conditions()
        self.last = {}            # last known value of every sample key (slow reads come every few polls)
        self.prev_t = None
        self.misses = 0
        self.clock_offset = None  # PC time - air time, s

    def update(self, s, pc_time):
        out = []
        if s is None:
            self.misses += 1
            if self.misses >= self.th.unreachable_after:
                out += self.cond.set(pc_time, "air", "AIR_UNREACHABLE", "ALERT", {"misses": self.misses})
            return out
        self.misses = 0
        out += self.cond.set(pc_time, "air", "AIR_UNREACHABLE", None)
        if s.get("now") is not None:
            self.clock_offset = round(pc_time - s["now"], 3)
        out += self._reboot(s, pc_time)
        out += self._rates(s, pc_time)
        out += self._levels(s, pc_time)
        out += self._radio(s, pc_time)
        self.last.update({k: v for k, v in s.items() if v is not None})
        self.prev_t = pc_time
        return out

    def _reboot(self, s, t):
        old_id, old_up = self.last.get("boot_id"), self.last.get("uptime")
        new_id, new_up = s.get("boot_id"), s.get("uptime")
        rebooted = (old_id and new_id and old_id != new_id) or (old_up is not None and new_up is not None
                                                                 and new_up < old_up)
        if not rebooted:
            return []
        for k in ("idr_honoured", "idr_dropped"):     # counters restart with the air
            self.last.pop(k, None)
        return [Alert(t, "ALERT", "air", "AIR_REBOOT", {"uptime": new_up, "was_uptime": old_up})]

    def _rates(self, s, t):
        out = []
        drop = s.get("wfb_drop")
        if drop is not None:
            out += self.cond.set(t, "air", "WFB_DROP", "ALERT" if drop > self.th.drop_max else None,
                                 {"drop": drop, "inj": s.get("wfb_inj")})
        h, d = s.get("idr_honoured"), s.get("idr_dropped")
        ph, pd = self.last.get("idr_honoured"), self.last.get("idr_dropped")
        if None not in (h, d, ph, pd, self.prev_t) and t > self.prev_t and h + d >= ph + pd:
            rate = (h + d - ph - pd) / (t - self.prev_t)
            out += self.cond.set(t, "air", "IDR_RATE", "WARN" if rate > self.th.idr_per_s_max else None,
                                 {"per_s": round(rate, 2), "honoured": h - ph, "dropped": d - pd})
        return out

    def _levels(self, s, t):
        out = []
        fps, cfg = s.get("fps"), s.get("cfg_fps") or self.last.get("cfg_fps")
        floor = self.th.fps_min if self.th.fps_min is not None else (cfg * self.th.fps_frac if cfg else None)
        if fps is not None and floor is not None:
            out += self.cond.set(t, "air", "AIR_FPS_LOW", "ALERT" if fps < floor else None,
                                 {"fps": fps, "floor": round(floor, 1)})
        temp = s.get("temp")
        if temp is not None:
            lvl = "ALERT" if temp >= self.th.temp_alert else "WARN" if temp >= self.th.temp_warn else None
            out += self.cond.set(t, "air", "AIR_TEMP", lvl, {"temp": temp})
        bcn = s.get("bcn_550")
        if bcn is not None:
            out += self.cond.set(t, "air", "AIR_BCN_550", "ALERT" if bcn != "0x10" else None, {"value": bcn})
        return out

    def _radio(self, s, t):
        out = []
        for key, (sk, code) in AIR_EXPECT.items():
            v = s.get(sk)
            if v is None:
                continue
            if key in self.expect:
                ok = _same(v, self.expect[key])
                out += self.cond.set(t, "air", code, None if ok else "ALERT", {"now": v, "expected": self.expect[key]})
            elif sk in self.last and not _same(v, self.last[sk]):
                out.append(Alert(t, "WARN", "air", code, {"was": self.last[sk], "now": v}))
        return out


class AirProbe:
    """One read-only ssh exec of air_probe.sh per poll (the script goes on stdin: no quoting through shells)."""

    def __init__(self, host=AIR_HOST, timeout=10):
        self.host, self.timeout = host, timeout
        self.script = open(AIR_PROBE, "rb").read()
        self.prev_lines = -1

    def read(self, slow):
        cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", self.host, "sh", "-s", "--",
               str(self.prev_lines), "1" if slow else "0"]
        try:
            r = subprocess.run(cmd, input=self.script, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        s = parse_air_probe(r.stdout.decode("utf-8", "replace"))
        if s["wfb_lines"] is not None:
            self.prev_lines = s["wfb_lines"]
        return s


# ---------------------------------------------------------------- quest (between measurements only)

QUEST_SCRIPT = ("dumpsys power | grep mWakefulness=; echo @@; pidof {pkg}; echo @@; "
                "getprop debug.oculus.guardian_pause; echo @@; dumpsys vrpowermanager 2>/dev/null | head -n 8; echo @@; "
                "dumpsys usb | grep -E 'vendor_id=|product_id='; echo @@; df -k /data; echo @@; "
                "dumpsys battery | grep ' level:'")


def parse_wakefulness(text):
    m = re.search(r"mWakefulness=(\w+)", text)
    return m.group(1) if m else None


def parse_df_free_mb(text):
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) >= 6 and f[5].startswith("/data"):
            return int(f[3]) // 1024
    return None


def parse_battery(text):
    m = re.search(r"level:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def parse_vrpower(text):
    """dumpsys vrpowermanager -> (virtual proximity state, headset state), e.g. ("CLOSE", "HEADSET_MOUNTED")."""
    p = re.search(r"Virtual proximity state:\s*(\w+)", text)
    st = re.search(r"^State:\s*(\w+)", text, re.M)
    return (p.group(1) if p else None), (st.group(1) if st else None)


def parse_usb_ids(text):
    """dumpsys usb host devices -> ["vvvv:pppp"]; the IDs are decimal there (0bda = 3034) and /sys/bus/usb is not
    readable from adb shell on the Quest."""
    vids = re.findall(r"vendor_id=(\d+)", text)
    pids = re.findall(r"product_id=(\d+)", text)
    return ["%04x:%04x" % (int(v), int(p)) for v, p in zip(vids, pids)]


def parse_quest(text):
    parts = (text.split("@@") + [""] * 7)[:7]
    prox, headset = parse_vrpower(parts[3])
    return {"wakefulness": parse_wakefulness(parts[0]), "pid": parts[1].strip(), "guardian_pause": parts[2].strip(),
            "prox": prox, "headset": headset, "usb": parse_usb_ids(parts[4]), "data_free_mb": parse_df_free_mb(parts[5]),
            "battery": parse_battery(parts[6])}


def read_quest():
    import quest_adb
    return parse_quest(quest_adb.adb("shell", QUEST_SCRIPT.format(pkg=env.PKG)))


def quest_alerts(q, th, expect, t=None):
    t = time.time() if t is None else t
    out = []

    def add(lvl, code, **d):
        out.append(Alert(t, lvl, "quest", code, d))

    if q.get("wakefulness") != "Awake":
        add("ALERT", "QUEST_ASLEEP", state=q.get("wakefulness"))
    if not q.get("pid"):
        add("ALERT", "QUEST_XR_NOT_RUNNING", pkg=env.PKG)
    if RTL_ID not in (q.get("usb") or []):
        add("ALERT", "QUEST_NO_ADAPTER", usb=",".join(q.get("usb") or []) or "-")
    for key, code in (("guardian_pause", "QUEST_GUARDIAN"), ("prox", "QUEST_PROX")):
        if key in expect and str(q.get(key)) != str(expect[key]):
            add("WARN", code, now=q.get(key), expected=expect[key])
    if q.get("data_free_mb") is not None and q["data_free_mb"] < th.storage_min_mb:
        add("WARN", "QUEST_STORAGE", free_mb=q["data_free_mb"])
    if q.get("battery") is not None and q["battery"] < th.battery_min:
        add("WARN", "QUEST_BATTERY", battery=q["battery"])
    return out


# ---------------------------------------------------------------- end-of-slot timeline

def _kv(tokens):
    return dict(p.split("=", 1) for p in tokens if "=" in p)


def timeline(alerts, app_lines, air_lines, start, end, air_offset=0.0, app_offset=0.0, periodic=False):
    """Rows (pc_time, source, code, level, detail) in [start, end], sorted by time.
    app_lines: "PPXR_EVENT|PPXR_HEALTH k=v ..." with t_wall_ms (Quest epoch ms) + app_offset.
    air_lines: air_health lines, epoch s in t= (+ air_offset); "EV ..." lines are events, the rest periodic.
    Periodic lines (HEALTH, the air's 2 s lines, the watcher's STATUS) only with periodic=True."""
    rows = []
    for a in alerts:
        if periodic or not a.code.endswith("_STATUS"):
            rows.append((a.t, a.source, a.code, a.level, " ".join(f"{k}={v}" for k, v in a.detail.items())))
    for line in app_lines:
        f = line.split()
        if not f or not f[0].startswith("PPXR_"):
            continue
        kv = _kv(f[1:])
        if "t_wall_ms" not in kv:
            continue
        code = kv.get("code", f[0])
        if code == "HEALTH" and not periodic:
            continue
        rest = " ".join(p for p in f[1:] if not p.startswith(("t_wall_ms=", "t_mono_ms=", "code=", "level=")))
        rows.append((int(kv["t_wall_ms"]) / 1000.0 + app_offset, "app", code, kv.get("level", "INFO"), rest))
    for line in air_lines:
        f = line.split()
        if not f:
            continue
        event = f[0] == "EV"
        kv = _kv(f[1:] if event else f)
        ts = kv.get("t", kv.get("epoch", kv.get("ts")))
        if ts is None or (not event and not periodic):
            continue
        code = kv.get("code", "AIR_HEALTH")
        rest = " ".join(p for p in (f[1:] if event else f) if not p.startswith(("t=", "up_cs=", "code=")))
        rows.append((float(ts) + air_offset, "air_health", code, kv.get("level", "EV" if event else "INFO"), rest))
    return sorted(r for r in rows if start <= r[0] <= end)


def render_report(rows, start, end):
    counts = {}
    for r in rows:
        counts[(r[1], r[2], r[3])] = counts.get((r[1], r[2], r[3]), 0) + 1
    fmt = lambda t: datetime.datetime.fromtimestamp(t).isoformat(sep=" ", timespec="seconds")
    out = [f"# Slot report {fmt(start)} → {fmt(end)}", "", "## Counts", "", "| source | code | level | n |",
           "|---|---|---|---|"]
    out += [f"| {s} | {c} | {lv} | {n} |" for (s, c, lv), n in sorted(counts.items())]
    out += ["", "## Timeline (PC time)", "", "| time | source | level | code | detail |", "|---|---|---|---|---|"]
    out += [f"| {fmt(t)} | {s} | {lv} | {c} | {d.replace('|', '/')} |" for t, s, c, lv, d in rows]
    return "\n".join(out) + "\n"


def pull_app_lines():
    """files/ppxr_health.log(.1) from the Quest (after the slot: adb over Wi-Fi is fine then) + the Quest's clock."""
    import quest_adb
    lines = []
    for name in ("files/ppxr_health.log.1", "files/ppxr_health.log"):
        lines += quest_adb.adb("exec-out", "run-as", env.PKG, "cat", name).splitlines()
    t0 = time.time()
    q = _num(quest_adb.adb("shell", "date +%s").strip())
    offset = round((t0 + time.time()) / 2 - q, 1) if q else 0.0
    return lines, offset


def pull_air_lines(host=AIR_HOST):
    cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", host, "sh", "-s"]
    script = b"cat /tmp/air_health.log.1 /tmp/air_health.log 2>/dev/null; echo @@now=$(date +%s)\n"
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=script, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        return [], 0.0
    text = r.stdout.decode("utf-8", "replace")
    m = re.search(r"@@now=(\d+)", text)
    offset = round((t0 + time.time()) / 2 - int(m.group(1)), 1) if m else 0.0
    return [l for l in text.splitlines() if not l.startswith("@@")], offset


# ---------------------------------------------------------------- CLI

class Sink:
    """stdout (for Monitor) + the alerts file."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.alerts = 0

    def emit(self, alerts):
        with open(self.path, "a", encoding="utf-8") as f:
            for a in alerts:
                line = a.line()
                print(line, flush=True)
                f.write(line + "\n")
                self.alerts += a.level == "ALERT"


def _expect(pairs):
    return dict(p.split("=", 1) for p in pairs or [])


def cmd_watch(args):
    sink, th = Sink(args.alerts), _thresholds(args)
    watch, probe = AirWatch(th, _expect(args.expect)), AirProbe(args.air_host)
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    end = time.time() + args.duration if args.duration else None
    sink.emit([Alert(time.time(), "INFO", "watch", "WATCH_START", {"interval_s": args.interval, "host": args.air_host})])
    n = 0
    while not stop["now"] and (end is None or time.time() < end):
        t_poll = time.time()
        s = probe.read(slow=n % args.slow_every == 0)
        now = time.time()
        sink.emit(watch.update(s, now))
        if s is not None and args.status_every and n % args.status_every == 0:
            sink.emit([Alert(now, "INFO", "air", "AIR_STATUS", {k: watch.last.get(k) for k in (
                "uptime", "temp", "fps", "kbps", "mcs", "fec", "channel", "txpower", "cfg_bitrate")}
                | {"clock_offset_s": watch.clock_offset})])
        n += 1
        time.sleep(max(0.0, args.interval - (time.time() - t_poll)))
    sink.emit([Alert(time.time(), "INFO", "watch", "WATCH_END", {"polls": n, "alerts": sink.alerts})])
    return 1 if sink.alerts else 0


def cmd_between(args):
    sink = Sink(args.alerts)
    q = read_quest()
    alerts = quest_alerts(q, _thresholds(args), _expect(args.expect))
    ok = Alert(time.time(), "INFO", "quest", "QUEST_OK" if not alerts else "QUEST_CHECK",
               {k: (",".join(v) if isinstance(v, list) else v) for k, v in q.items()})
    sink.emit(alerts + [ok])
    return 1 if sink.alerts else 0


def cmd_report(args):
    alerts = [Alert.parse(l) for l in open(args.alerts, encoding="utf-8") if l.strip()]
    start = args.since or (alerts[0].t if alerts else 0.0)
    end = args.until or (alerts[-1].t if alerts else time.time())
    app, app_off = ([], 0.0) if args.no_quest else pull_app_lines()
    air, air_off = ([], 0.0) if args.no_air else pull_air_lines(args.air_host)
    rows = timeline(alerts, app, air, start, end, air_offset=air_off, app_offset=app_off, periodic=args.periodic)
    out = os.path.splitext(args.alerts)[0] + "-report.md"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_report(rows, start, end))
    print(f"report {out}: {len(rows)} rows (app lines {len(app)}, clock {app_off:+} s; air lines {len(air)}, "
          f"clock {air_off:+} s)")
    return 0


def _thresholds(args):
    return Thresholds(idr_per_s_max=args.idr_max, fps_min=args.fps_min, temp_warn=args.temp_warn,
                      temp_alert=args.temp_alert, storage_min_mb=args.storage_min_mb, battery_min=args.battery_min)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=("watch", "between", "report"))
    p.add_argument("--alerts", default=None, help="alerts file (default out/slot_watch/<date>/alerts.log)")
    p.add_argument("--expect", action="append", metavar="KEY=VALUE",
                   help="planned value: air channel/txpower/mcs/fec/bitrate/fps; quest guardian_pause/prox")
    p.add_argument("--air-host", default=AIR_HOST)
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--slow-every", type=int, default=6, help="radio/iw/config reads every N polls (6 x 5 s = 30 s)")
    p.add_argument("--status-every", type=int, default=12, help="an AIR_STATUS line every N polls (0 = never)")
    p.add_argument("--duration", type=float, default=0, help="seconds (0 = until Ctrl-C)")
    p.add_argument("--idr-max", type=float, default=Thresholds.idr_per_s_max)
    p.add_argument("--fps-min", type=float, default=None)
    p.add_argument("--temp-warn", type=int, default=Thresholds.temp_warn)
    p.add_argument("--temp-alert", type=int, default=Thresholds.temp_alert)
    p.add_argument("--storage-min-mb", type=int, default=Thresholds.storage_min_mb)
    p.add_argument("--battery-min", type=int, default=Thresholds.battery_min)
    p.add_argument("--since", type=float, default=None)
    p.add_argument("--until", type=float, default=None)
    p.add_argument("--no-quest", action="store_true")
    p.add_argument("--no-air", action="store_true")
    p.add_argument("--periodic", action="store_true", help="report: keep the periodic lines too")
    args = p.parse_args(argv)
    if args.alerts is None:
        args.alerts = env.out_path(os.path.join("slot_watch", time.strftime("%Y%m%d"), "alerts.log"))
    return {"watch": cmd_watch, "between": cmd_between, "report": cmd_report}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
