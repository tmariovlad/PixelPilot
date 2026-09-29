"""Slot monitoring on the PC: the air unit during a slot, the Quest between measurements, and a timeline at the end.
The coordinator starts it; every alert is one line on stdout (follow it with Monitor) and in an alerts file.

Usage:
  slot_watch.py watch   [--interval 5] [--duration S] [--expect channel=157 --expect txpower=12 ...] [--alerts F]
                        [--air-source auto|health|probe]
      Reads the air over eth0 (ssh alias `air`, one read-only `sh -s` per poll) until Ctrl-C or --duration. When
      air_health.sh runs on the air (openipc-…-40) it only reads the new lines of its ring (air_tail.sh: one sampler
      on the air); otherwise it probes (air_probe.sh). `auto` picks at the start. Never touches the Quest: adb over
      Wi-Fi during a measurement costs the RTL packets (docs/xr/troubleshooting.md, U1). Exit 1 if any ALERT, else 0.
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
import collections
import datetime
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import quest_env as env

sys.path.insert(0, env.LATCH_DIR)
import health_log  # noqa: E402  (scripts/quest-latch, pixelpilot-xr-36: the one parser of the app's health lines)

AIR_PROBE = os.path.join(env.HERE, "air_probe.sh")
AIR_TAIL = os.path.join(env.HERE, "air_tail.sh")
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
    m = re.search(r"\| ([\d.]+) fps \| (\d+) kbps", raw.get("wb_verbose", ""))
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
    idr_per_s_max: float = 2.0       # honoured + dropped key-frame requests per second, over idr_window_s
    idr_window_s: float = 30.0       # a 5 s delta flapped WARN <-> OK every 5-10 s in the live run of 2026-09-29
    idr_clear_frac: float = 0.75     # hysteresis: clear below 0.75 x the limit
    fps_frac: float = 0.975          # waybeam fps below this share of the configured fps (90 -> 87.75, 167 -> 162.8)
    fps_min: Optional[float] = None  # absolute override
    temp_warn: int = 60              # bitrate_grid.sh TEMP_SKIP
    temp_alert: int = 70             # bitrate_grid.sh TEMP_STOP
    drop_max: int = 0                # wfb_tx p_drop per poll
    unreachable_after: int = 2       # consecutive failed polls
    health_stale_s: float = 10.0     # air_health's newest line older than this (5 of its 2 s ticks) = not logging
    storage_min_mb: int = 2048
    battery_min: int = 30            # link-envelope.md stop rule


# expect key -> (sample key, alert code)
AIR_EXPECT = {"channel": ("channel", "AIR_CHANNEL"), "txpower": ("txpower", "AIR_TXPOWER"), "mcs": ("mcs", "AIR_MCS"),
              "fec": ("fec", "AIR_FEC"), "bitrate": ("cfg_bitrate", "AIR_BITRATE"), "fps": ("cfg_fps", "AIR_CFG_FPS")}


def _same(a, b):
    fa, fb = _num(a), _num(b)
    return fa == fb if fa is not None and fb is not None else str(a) == str(b)


class AirClock:
    """PC time - air time, bounded instead of guessed.

    The probe prints the air's `date +%s` (whole seconds) and /proc/uptime (10 ms) at the same moment, so
    floor(uptime + B) = date, with B = air epoch - uptime: every poll bounds B to [date - uptime, date + 1 - uptime].
    Intersected over the polls, B converges to ~10 ms without a busy wait on the air. The air's sample happens during
    the ssh call, so pc_before <= its PC time <= pc_after bounds the offset (NTP style); intersected over the polls
    it converges to the fastest calls. An empty intersection (a clock step) or a reboot starts over.
    (Taking PC time after the call against the whole-second date gave a 1.1 -> 2.2 s sawtooth live, 2026-09-29.)"""
    SLACK = 0.02      # uptime resolution + the two reads being a few ms apart

    def __init__(self):
        self.reset()

    def reset(self):
        self.b = [-math.inf, math.inf]
        self.o = [-math.inf, math.inf]

    def add(self, date, uptime, pc_before, pc_after):
        self.b = _intersect(self.b, [date - uptime - self.SLACK, date + 1 - uptime + self.SLACK])
        air = uptime + (self.b[0] + self.b[1]) / 2
        err = (self.b[1] - self.b[0]) / 2
        self.o = _intersect(self.o, [pc_before - air - err, pc_after - air + err])

    @property
    def offset(self):
        return None if math.isinf(self.o[0]) else round((self.o[0] + self.o[1]) / 2, 3)

    @property
    def err(self):
        return None if math.isinf(self.o[0]) else round((self.o[1] - self.o[0]) / 2, 3)


def _intersect(cur, new):
    lo, hi = max(cur[0], new[0]), min(cur[1], new[1])
    return [lo, hi] if lo <= hi else list(new)


class AirWatch:
    """The air's alert rules over consecutive samples. update(None) = the poll failed. `expect` holds planned values;
    after `expect_until` (PC epoch) they are no longer enforced, so a planned revert at the end is not an ALERT."""

    def __init__(self, th, expect=None, expect_until=None):
        self.th, self.expect, self.expect_until = th, dict(expect or {}), expect_until
        self.cond = Conditions()
        self.last = {}            # last known value of every sample key (slow reads come every few polls)
        self.misses = 0
        self.clock = AirClock()
        self.idr = collections.deque()   # (pc time, honoured + dropped) within idr_window_s

    @property
    def clock_offset(self):
        return self.clock.offset

    @property
    def clock_err(self):
        return self.clock.err

    def update(self, s, pc_time, pc_before=None):
        """One probe poll. pc_time = when it returned; pc_before = when it started (bounds the air clock offset)."""
        if s is None:
            return self.poll_failed(pc_time)
        out = self.poll_ok(pc_time) + self.observe(s, pc_time)
        if s.get("now") is not None and s.get("uptime") is not None:
            self.add_clock(s["now"], s["uptime"], pc_time if pc_before is None else pc_before, pc_time)
        return out

    def poll_failed(self, t):
        self.misses += 1
        if self.misses >= self.th.unreachable_after:
            return self.cond.set(t, "air", "AIR_UNREACHABLE", "ALERT", {"misses": self.misses})
        return []

    def poll_ok(self, t):
        self.misses = 0
        return self.cond.set(t, "air", "AIR_UNREACHABLE", None)

    def observe(self, s, t):
        """The rules over one sample taken at PC time t."""
        out = self._reboot(s, t) + self._rates(s, t) + self._levels(s, t) + self._radio(s, t)
        self.last.update({k: v for k, v in s.items() if v is not None})
        return out

    def add_clock(self, date, uptime, pc_before, pc_after):
        self.clock.add(date, uptime, pc_before, pc_after)

    def _reboot(self, s, t):
        old_id, old_up = self.last.get("boot_id"), self.last.get("uptime")
        new_id, new_up = s.get("boot_id"), s.get("uptime")
        rebooted = (old_id and new_id and old_id != new_id) or (old_up is not None and new_up is not None
                                                                 and new_up < old_up)
        if not rebooted:
            return []
        self.idr.clear()          # the counters restart with the air
        self.clock.reset()
        self.last.pop("uptime", None)   # the old boot's uptime says nothing about the new one
        return [Alert(t, "ALERT", "air", "AIR_REBOOT", {"uptime": new_up, "was_uptime": old_up})]

    def _rates(self, s, t):
        out = []
        drop = s.get("wfb_drop")
        if drop is not None:
            out += self.cond.set(t, "air", "WFB_DROP", "ALERT" if drop > self.th.drop_max else None,
                                 {"drop": drop, "inj": s.get("wfb_inj")}
                                 | {k: s[k] for k in ("udp_ddrops", "idr_dh", "wfb_ps") if s.get(k) is not None})
        rate = self._idr_rate(s, t)
        if rate is not None:
            on = "IDR_RATE" in self.cond.active
            limit = self.th.idr_per_s_max * (self.th.idr_clear_frac if on else 1.0)
            out += self.cond.set(t, "air", "IDR_RATE", "WARN" if rate > limit else None,
                                 {"per_s": round(rate, 2), "window_s": round(t - self.idr[0][0], 1)})
        return out

    def _idr_rate(self, s, t):
        """Key-frame requests per second over the last idr_window_s, or None before there are two samples."""
        h, d = s.get("idr_honoured"), s.get("idr_dropped")
        if h is None or d is None:
            return None
        if self.idr and h + d < self.idr[-1][1]:
            self.idr.clear()                              # a counter reset without a detected reboot
        self.idr.append((t, h + d))
        while len(self.idr) > 2 and t - self.idr[1][0] >= self.th.idr_window_s:
            self.idr.popleft()
        (t0, n0), (t1, n1) = self.idr[0], self.idr[-1]
        return (n1 - n0) / (t1 - t0) if t1 > t0 else None

    def _levels(self, s, t):
        out = []
        fps, cfg = s.get("fps"), s.get("cfg_fps") or self.last.get("cfg_fps")
        floor = self.th.fps_min if self.th.fps_min is not None else (cfg * self.th.fps_frac if cfg else None)
        if fps is not None and floor is not None:
            out += self.cond.set(t, "air", "AIR_FPS_LOW", "ALERT" if fps < floor else None,
                                 {"fps": fps, "floor": round(floor, 1)})
        temp = s.get("temp")
        if temp is not None:
            out += self.cond.set(t, "air", "AIR_TEMP", self._temp_level(temp), {"temp": temp})
        bcn = s.get("bcn_550")
        if bcn is not None:
            out += self.cond.set(t, "air", "AIR_BCN_550", "ALERT" if bcn != "0x10" else None, {"value": bcn})
        return out

    def _temp_level(self, temp):
        if temp >= self.th.temp_alert:
            return "ALERT"
        if temp >= self.th.temp_warn:
            return "WARN"
        return None

    def _radio(self, s, t):
        out = []
        for key, (sk, code) in AIR_EXPECT.items():
            v = s.get(sk)
            if v is None:
                continue
            if key in self.expect and self.expect_until is not None and t > self.expect_until:
                self.cond.active.pop(code, None)       # the plan is over: from now on a change is only a WARN
            if key in self.expect and (self.expect_until is None or t <= self.expect_until):
                ok = _same(v, self.expect[key])
                out += self.cond.set(t, "air", code, None if ok else "ALERT", {"now": v, "expected": self.expect[key]})
            elif sk in self.last and not _same(v, self.last[sk]):
                out.append(Alert(t, "WARN", "air", code, {"was": self.last[sk], "now": v}))
        return out


def _script(path):
    """A .sh to send on stdin, LF only: core.autocrlf=true checks it out with CRLF, and the air's busybox sh would take
    the CR as part of each command."""
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def _ssh(host, script, args, timeout):
    """One read-only `ssh host sh -s -- args` with the script on stdin (no quoting through shells) -> stdout, or None."""
    cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", host, "sh", "-s", "--", *args]
    try:
        r = subprocess.run(cmd, input=script, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


class AirProbe:
    """One read-only ssh exec of air_probe.sh per poll (the fallback while air_health.sh is not running)."""

    def __init__(self, host=AIR_HOST, timeout=10):
        self.host, self.timeout = host, timeout
        self.script = _script(AIR_PROBE)
        self.prev_lines = -1

    def read(self, slow):
        text = _ssh(self.host, self.script, [str(self.prev_lines), "1" if slow else "0"], self.timeout)
        if text is None:
            return None
        s = parse_air_probe(text)
        if s["wfb_lines"] is not None:
            self.prev_lines = s["wfb_lines"]
        return s


# ---------------------------------------------------------------- air: air_health.sh's ring log (openipc-…-40)

def air_health_parser():
    """parse_air_health.py (openipc-…-40, 444d017): the one parser of the air_health lines, from env.AIR_HEALTH_DIR."""
    if env.AIR_HEALTH_DIR not in sys.path:
        sys.path.insert(0, env.AIR_HEALTH_DIR)
    try:
        import parse_air_health
    except ImportError as e:
        raise SystemExit(f"parse_air_health.py not found in {env.AIR_HEALTH_DIR} (set AIR_HEALTH_DIR): {e}")
    return parse_air_health


def air_health_record(line):
    """parse_air_health.parse_line; a missing boot (NA or empty, which the parser keeps as text) becomes None, so it
    never counts as a boot of its own. The parser keeps boot= as text since OpenIPC 2eb1567."""
    rec = air_health_parser().parse_line(line)
    if rec is not None and rec.get("boot") in ("", "NA"):
        rec["boot"] = None
    return rec


def _air_pc(rec, anchor):
    """PC time of an air_health line from its uptime: anchor = (PC time, the air's uptime in s) of one moment. 10 ms,
    and no clock offset needed. Valid for lines of the anchor's boot (/tmp is a tmpfs: older boots' lines are gone)."""
    return anchor[0] - (anchor[1] - rec["up"] / 100.0)


def sample_from_ah(rec):
    """An AH record -> the sample AirWatch's rules read (the keys of parse_air_probe). The window sums (wfb_drop,
    udp_ddrops, idr_dh, wfb_ps) only on sa=0 lines: a cached line repeats them (00-DESIGN-air-health.md §2). The drop
    rule counts wfb_tx's input drops and the UDP socket's (the two halves of RXQ_DROP)."""
    g = rec.get
    k, n, bcn = g("fec_k"), g("fec_n"), str(g("bcn") or "").lower()
    s = {"now": None, "uptime": g("up") / 100.0 if isinstance(g("up"), int) else None, "boot_id": g("boot"),
         "temp": g("temp"), "tx_packets": g("wl_txp"), "fps": g("fps"), "kbps": g("kbps"),
         "idr_honoured": g("idr_h"), "idr_dropped": g("idr_d"), "mcs": g("mcs"),
         "fec": f"{k}/{n}" if k is not None and n is not None else None, "channel": g("ch"), "txpower": g("txpwr"),
         "bcn_550": bcn if re.fullmatch(r"0x[0-9a-f]+", bcn) else None, "wfb_drop": None, "wfb_inj": None}
    if g("sa") == 0 and (g("wfb_drop") is not None or g("udp_ddrops") is not None):
        s.update(wfb_drop=(g("wfb_drop") or 0) + (g("udp_ddrops") or 0), wfb_inj=g("wfb_inj"),
                 udp_ddrops=g("udp_ddrops"), idr_dh=g("idr_dh"), wfb_ps=g("wfb_ps"))
    return s


TAIL_HEAD = ("now", "uptime", "boot_id", "cfg_bitrate", "cfg_fps")


def parse_tail(text):
    """air_tail.sh output -> (head, lines): head = the air's clock and boot + waybeam's configured bitrate/fps (slow
    polls only), lines = the AH/EV lines in file order."""
    head, lines = dict.fromkeys(TAIL_HEAD), []
    for line in text.splitlines():
        if line.startswith(("AH ", "EV ")):
            lines.append(line)
        elif "=" in line:
            k, v = line.split("=", 1)
            if k in head:
                head[k] = v.strip() or None
    head["now"], head["uptime"] = _num(head["now"], int), _num(head["uptime"])
    head["cfg_bitrate"], head["cfg_fps"] = _num(head["cfg_bitrate"], int), _num(head["cfg_fps"], int)
    return head, lines


class HealthTail:
    """One read-only ssh exec of air_tail.sh per poll -> (head, lines), or (None, []) when the call failed."""

    def __init__(self, host=AIR_HOST, timeout=10, lines=15):
        self.host, self.timeout, self.lines = host, timeout, lines   # 15 lines per file = 30 s of 2 s ticks
        self.script = _script(AIR_TAIL)

    def read(self, slow):
        text = _ssh(self.host, self.script, ["1" if slow else "0", str(self.lines)], self.timeout)
        return parse_tail(text) if text is not None else (None, [])


def pick_air_source(mode, head, lines, stale_s=Thresholds.health_stale_s):
    """--air-source auto: air_health when its ring has a line of this boot at most stale_s old, else the probe."""
    if mode != "auto":
        return mode
    if head is None or head.get("uptime") is None:
        return "probe"
    boot = (head.get("boot_id") or "")[:8]
    ups = [r["up"] for r in map(air_health_record, lines) if r and r.get("boot") == boot and isinstance(r.get("up"), int)]
    return "health" if ups and head["uptime"] - max(ups) / 100.0 <= stale_s else "probe"


class HealthFeed:
    """air_health.sh's ring log as the watcher's air source: one sampler on the air, the same rules as the probe.

    Each poll reads the air's clock, then the tail of the ring. Only lines not seen before go to AirWatch, each at its
    own PC time (_air_pc). A reboot is seen from the poll's boot_id even while the logger is down. Events no rule
    covers are passed on as `air_health <CODE>` at the air's level. The first poll is only a baseline: its last AH
    line, no replay of older events. The watcher's own findings about the log: AIR_HEALTH_STALE (no line newer than
    health_stale_s, none of this boot, or no log) and AIR_HEALTH_GAP (seq jumped: lines the tail missed)."""
    COVERED = {"THERMAL", "THERMAL_OK", "CHAN", "TXPWR", "RXQ_DROP", "ROTATE"}   # AIR_TEMP, AIR_*, WFB_DROP; noise

    def __init__(self, watch, th):
        self.watch, self.th, self.cond = watch, th, Conditions()
        self.boot, self.up, self.at_up, self.seq = None, None, set(), None
        self.old_boots, self.baseline = set(), True

    def poll(self, head, lines, pc_before, pc_after):
        if head is None or head.get("uptime") is None:
            return self.watch.update(None, pc_after)
        anchor = ((pc_before + pc_after) / 2, head["uptime"])
        boot = (head.get("boot_id") or "")[:8] or None
        # boot only, no uptime: lines written between the head read and the tail are newer than the head's uptime
        out = self.watch.poll_ok(pc_after) + self.watch.observe({"boot_id": boot}, anchor[0])
        for rec in self.new_records(lines):
            t = _air_pc(rec, anchor)
            out += self._event(rec, t) if rec["_kind"] == "EV" else self._sample(rec, head, t)
        if head.get("now") is not None:
            self.watch.add_clock(head["now"], head["uptime"], pc_before, pc_after)
        return out + self._stale(boot, head["uptime"], anchor[0])

    def new_records(self, lines):
        """The tail's lines (chronological) -> the records not seen before, by (boot, uptime) + the exact line."""
        out = []
        for line in lines:
            rec = air_health_record(line)
            if rec is None or rec.get("boot") is None or not isinstance(rec.get("up"), int) \
                    or rec["boot"] in self.old_boots:
                continue
            if rec["boot"] != self.boot:
                if self.boot is not None:
                    self.old_boots.add(self.boot)
                self.boot, self.up, self.at_up, self.seq = rec["boot"], None, set(), None
            if self.up is not None and (rec["up"] < self.up or (rec["up"] == self.up and line in self.at_up)):
                continue
            if rec["up"] != self.up:
                self.up, self.at_up = rec["up"], set()
            self.at_up.add(line)
            out.append(rec)
        if self.baseline and out:
            self.baseline = False
            out = [r for r in out if r["_kind"] == "AH"][-1:]
        return out

    def _sample(self, rec, head, t):
        out, seq = [], rec.get("seq")
        if isinstance(seq, int):
            if self.seq is not None and seq > self.seq + 1:
                out.append(Alert(t, "WARN", "air", "AIR_HEALTH_GAP", {"missed": seq - self.seq - 1, "seq": seq}))
            self.seq = seq
        s = sample_from_ah(rec)
        s.update(cfg_bitrate=head.get("cfg_bitrate"), cfg_fps=head.get("cfg_fps"))
        return out + self.watch.observe(s, t)

    def _event(self, rec, t):
        code = rec.get("code")
        if code is None or code in self.COVERED:
            return []
        meta = air_health_parser().EV_KEYS
        level = rec.get("level") if rec.get("level") in LEVELS else "INFO"
        return [Alert(t, level, "air_health", str(code), {k: rec[k] for k in rec["_keys"] if k not in meta})]

    def _stale(self, boot, uptime, t):
        lag = None
        if self.boot is None:
            reason = "nolog"
        elif self.boot != boot:
            reason = "boot"                                   # the ring is from an earlier boot: not restarted
        else:
            lag = round(uptime - self.up / 100.0, 1)
            reason = "lag" if lag > self.th.health_stale_s else None
        return self.cond.set(t, "air", "AIR_HEALTH_STALE", "ALERT" if reason else None,
                             {"reason": reason, "lag_s": lag} if reason else {"lag_s": lag})


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

APP_META = ("t_wall_ms", "t_mono_ms", "code", "level")
REPORT_AH_KEYS = ("temp", "cpu0", "fps", "kbps", "mcs", "fec_k", "fec_n", "ch", "txpwr", "sa", "wfb_drop",
                  "udp_ddrops", "idr_dh", "bcn", "reg550")   # the periodic AH row keeps these (a line has 72 keys)


def _alert_row(a, periodic):
    if not periodic and a.code.endswith("_STATUS"):
        return None
    return a.t, a.source, a.code, a.level, " ".join(f"{k}={v}" for k, v in a.detail.items())


def _app_row(line, offset, periodic):
    """An app health line (files/ppxr_health.log or a detached logcat capture) -> a row on PC time, or None. The
    format has one parser, pixelpilot-xr-36's health_log.parse (t_wall_ms = the Quest's epoch ms)."""
    rec = health_log.parse(line.rstrip("\n"))
    if rec is None:
        return None
    tag, kv = rec
    code = kv.get("code", tag)
    if "t_wall_ms" not in kv or (code == "HEALTH" and not periodic):
        return None
    rest = " ".join(f"{k}={v}" for k, v in kv.items() if k not in APP_META)
    return int(kv["t_wall_ms"]) / 1000.0 + offset, "app", code, kv.get("level", "INFO"), rest


def app_summary(lines):
    """health_log.summarize of the app's lines (stalls per minute, causes, freeze %, IDR failure reasons)."""
    return health_log.summarize(lines) if lines else {}


def _air_row(line, anchor, periodic):
    """An air_health line (parse_air_health's schema) -> a row on PC time via its uptime (_air_pc), or None. EV = an
    event; AH (every 2 s) only with periodic, with REPORT_AH_KEYS."""
    rec = air_health_record(line)
    if rec is None or anchor is None or not isinstance(rec.get("up"), int) or (rec["_kind"] == "AH" and not periodic):
        return None
    t = _air_pc(rec, anchor)
    if rec["_kind"] == "EV":
        meta = air_health_parser().EV_KEYS
        rest = " ".join(f"{k}={rec[k]}" for k in rec["_keys"] if k not in meta)
        return t, "air_health", str(rec.get("code")), rec.get("level") or "INFO", rest
    return t, "air_health", "AH", "INFO", " ".join(f"{k}={_token(rec.get(k))}" for k in REPORT_AH_KEYS)


def timeline(alerts, app_lines, air_lines, start, end, air_anchor=None, app_offset=0.0, periodic=False):
    """Rows (pc_time, source, code, level, detail) in [start, end], sorted by time. app_lines are corrected by
    app_offset (Quest clock -> PC), air_lines placed by air_anchor (_air_pc). Periodic lines (HEALTH, the air's AH
    lines, the watcher's AIR_STATUS) only with periodic=True. The events the watcher passed on (source air_health)
    are left out when the air's own lines are there, so none is listed twice."""
    rows = [_alert_row(a, periodic) for a in alerts if not (air_lines and a.source == "air_health")]
    rows += [_app_row(line, app_offset, periodic) for line in app_lines]
    rows += [_air_row(line, air_anchor, periodic) for line in air_lines]
    return sorted(r for r in rows if r is not None and start <= r[0] <= end)


def air_summary(records):
    """parse_air_health.summarize of the air's records, without its event list (the timeline has the events)."""
    if not records:
        return {}
    s = air_health_parser().summarize(records)
    s.pop("events", None)
    return s


def render_report(rows, start, end, app_summary=None, air_summary=None):
    counts = {}
    for r in rows:
        counts[(r[1], r[2], r[3])] = counts.get((r[1], r[2], r[3]), 0) + 1
    fmt = lambda t: datetime.datetime.fromtimestamp(t).isoformat(sep=" ", timespec="seconds")
    out = [f"# Slot report {fmt(start)} → {fmt(end)}", "", "## Counts", "", "| source | code | level | n |",
           "|---|---|---|---|"]
    out += [f"| {s} | {c} | {lv} | {n} |" for (s, c, lv), n in sorted(counts.items())]
    out += ["", "## Timeline (PC time)", "", "| time | source | level | code | detail |", "|---|---|---|---|---|"]
    out += [f"| {fmt(t)} | {s} | {lv} | {c} | {d.replace('|', '/')} |" for t, s, c, lv, d in rows]
    for title, summary in (("App health summary (health_log.summarize)", app_summary),
                           ("Air health summary (parse_air_health.summarize, slot window)", air_summary)):
        if summary:
            out += ["", f"## {title}", "", "| key | value |", "|---|---|"]
            out += [f"| {k} | {str(v).replace('|', '/')} |" for k, v in summary.items()]
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
    """Both ring files of air_health.sh -> (lines, anchor). The anchor comes from its own short call (the air's uptime
    at the middle of it), because the copy of a few MB takes long enough to blur a time taken with it."""
    text = _ssh(host, b"cat /tmp/air_health.log.1 /tmp/air_health.log 2>/dev/null\n", [], timeout=60)
    t0 = time.time()
    up = _num((_ssh(host, b"cut -d' ' -f1 /proc/uptime\n", [], timeout=10) or "").strip())
    anchor = ((t0 + time.time()) / 2, up) if up is not None else None
    return [l for l in (text or "").splitlines() if l.startswith(("AH ", "EV "))], anchor


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
    start = time.time()
    until = parse_until(args.expect_until, start)
    watch = AirWatch(th, _expect(args.expect), expect_until=until)
    probe, tail = AirProbe(args.air_host), HealthTail(args.air_host)
    source = args.air_source
    if source == "auto":
        source = pick_air_source(source, *tail.read(slow=False), stale_s=th.health_stale_s)
    feed = HealthFeed(watch, th) if source == "health" else None
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    end = start + args.duration if args.duration else None
    sink.emit([Alert(start, "INFO", "watch", "WATCH_START", {"interval_s": args.interval, "host": args.air_host,
                                                             "air_source": source, "expect_until": until})])
    n = 0
    while not stop["now"] and (end is None or time.time() < end):
        t_poll, slow = time.time(), n % args.slow_every == 0
        if feed:
            head, lines = tail.read(slow)
            now = time.time()
            sink.emit(feed.poll(head, lines, t_poll, now))
            ok = head is not None
        else:
            s = probe.read(slow)
            now = time.time()
            sink.emit(watch.update(s, now, pc_before=t_poll))
            ok = s is not None
        if ok and args.status_every and n % args.status_every == 0:
            sink.emit([Alert(now, "INFO", "air", "AIR_STATUS", {k: watch.last.get(k) for k in (
                "uptime", "temp", "fps", "kbps", "mcs", "fec", "channel", "txpower", "cfg_bitrate")}
                | {"clock_offset_s": watch.clock_offset, "clock_err_s": watch.clock_err})])
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
    air, anchor = ([], None) if args.no_air else pull_air_lines(args.air_host)
    rows = timeline(alerts, app, air, start, end, air_anchor=anchor, app_offset=app_off, periodic=args.periodic)
    recs = [r for r in map(air_health_record, air) if r and anchor and isinstance(r.get("up"), int)
            and start <= _air_pc(r, anchor) <= end]
    out = os.path.splitext(args.alerts)[0] + "-report.md"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_report(rows, start, end, app_summary=app_summary(app), air_summary=air_summary(recs)))
    print(f"report {out}: {len(rows)} rows (app lines {len(app)}, clock {app_off:+} s; air lines {len(air)}, "
          f"{len(recs)} in the slot, anchor {anchor})")
    return 0


def parse_until(value, start):
    """--expect-until: a PC epoch, or "+N" = N seconds after the watch started; None = the whole watch."""
    if value is None:
        return None
    return start + float(value[1:]) if str(value).startswith("+") else float(value)


def _thresholds(args):
    return Thresholds(idr_per_s_max=args.idr_max, idr_window_s=args.idr_window, fps_min=args.fps_min,
                      temp_warn=args.temp_warn, temp_alert=args.temp_alert, storage_min_mb=args.storage_min_mb,
                      battery_min=args.battery_min)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=("watch", "between", "report"))
    p.add_argument("--alerts", default=None, help="alerts file (default out/slot_watch/<date>/alerts.log)")
    p.add_argument("--expect", action="append", metavar="KEY=VALUE",
                   help="planned value: air channel/txpower/mcs/fec/bitrate/fps; quest guardian_pause/prox")
    p.add_argument("--air-host", default=AIR_HOST)
    p.add_argument("--air-source", choices=("auto", "health", "probe"), default="auto",
                   help="watch: air_health's ring (one sampler on the air), the probe, or auto = the ring if it is live")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--slow-every", type=int, default=6, help="radio/iw/config reads every N polls (6 x 5 s = 30 s)")
    p.add_argument("--status-every", type=int, default=12, help="an AIR_STATUS line every N polls (0 = never)")
    p.add_argument("--duration", type=float, default=0, help="seconds (0 = until Ctrl-C)")
    p.add_argument("--expect-until", default=None, metavar="EPOCH|+SECONDS",
                   help="stop enforcing --expect after this (e.g. before the planned revert at the end of the run)")
    p.add_argument("--idr-max", type=float, default=Thresholds.idr_per_s_max)
    p.add_argument("--idr-window", type=float, default=Thresholds.idr_window_s, help="seconds of the IDR rate")
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
