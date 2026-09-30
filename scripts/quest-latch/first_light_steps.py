"""Rig-side detector for a sustained step in optical first light (latency-test's per-flash CSV), e.g. the HD pre-VENC
state of 2026-09-30 Part A: the lens read 71 ms instead of 45-48 while every Quest segment (enc/lnk/dec/dsp, which all
start at the air PTS) stayed the same, so only the rig can see it (docs/xr/link-envelope.md, rig slot 2026-09-30).

A flash is "high" when its first light exceeds the baseline of its step label by more than --min-step-ms. The baseline is
the median of the same label's flashes over the previous --baseline-s seconds (rolling; needs 5 of them), or a fixed
per-label reference (--fixed hd=45) for a run that may start in the bad state. High flashes form one event while at most
one normal flash and at most MAX_PAUSE_S seconds separate them; an event counts when it lasts >= --min-s seconds with >= --min-n high flashes. The
baseline is frozen while an event is open, so the step does not raise its own reference.

Usage: python3 first_light_steps.py per_flash.csv [more.csv ...] [--fixed hd=45,race=27] [--min-step-ms 15]
           [--min-s 10] [--baseline-s 60] [--min-n 5]
Prints one "STEP <label> ..." line per event and exits 1 when there is at least one (0 when none), so a slot script can
act on it. Input columns: run,id,pc_epoch,result,first_us,full_us,step (only result == ok rows with a step count).
Reference for HD 1080p90 16M MCS7: first light 45-48 ms, median ~46 (latency-test-0d, 9 runs, n = 225), so
--fixed hd=46 flags the Part A state (71 ms) even when a run starts in it.
"""
import argparse
import csv
import statistics
import sys
from dataclasses import dataclass

MIN_BASE_N = 5
MAX_GAP = 1
MAX_PAUSE_S = 10.0   # no flash for this long (e.g. between two rig runs) closes an open event


@dataclass
class Event:
    label: str
    start: float
    end: float
    n: int
    median_ms: float
    baseline_ms: float


def read_per_flash(paths):
    """[(pc_epoch, step label, first_ms)] of the ok rows with a step label, in time order. An empty step is a flash
    inside a switch guard or outside the schedule (latency-test's per_flash.py), not a label, so it is dropped."""
    rows = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("result") == "ok" and r.get("first_us") and r.get("step"):
                    rows.append((float(r["pc_epoch"]), r["step"], int(r["first_us"]) / 1000.0))
    return sorted(rows)


def _close(label, run, base, min_s, min_n, out):
    highs = [(t, v) for t, v, high in run if high]
    if len(highs) >= min_n and highs[-1][0] - highs[0][0] >= min_s:
        out.append(Event(label, highs[0][0], highs[-1][0], len(highs),
                         statistics.median(v for _, v in highs), base))


def _rolling_baseline(normal, t, baseline_s):
    """Median of the label's normal flashes in [t - baseline_s, t), or None while fewer than MIN_BASE_N."""
    pool = [x for s, x in normal if t - baseline_s <= s < t]
    return statistics.median(pool) if len(pool) >= MIN_BASE_N else None


def _baseline(run_base, fixed_ms, normal, t, baseline_s):
    """The reference for a flash at t: frozen while an event is open, else the fixed one, else the rolling median."""
    if run_base is not None:
        return run_base
    if fixed_ms is not None:
        return fixed_ms
    return _rolling_baseline(normal, t, baseline_s)


class _LabelScan:
    """One label's flashes, fed in time order; events collect in .events."""

    def __init__(self, label, fixed_ms, min_step_ms, min_s, baseline_s, min_n):
        self.label, self.fixed_ms, self.min_step_ms = label, fixed_ms, min_step_ms
        self.min_s, self.baseline_s, self.min_n = min_s, baseline_s, min_n
        self.events = []
        self.normal = []             # (t, v) outside events: the rolling baseline's pool
        self.run, self.run_base, self.gap = [], None, 0

    def _flush(self):
        """Close the open event (kept only if long enough) and return its flashes to the baseline pool."""
        if self.run:
            _close(self.label, self.run, self.run_base, self.min_s, self.min_n, self.events)
            self.normal.extend((s, x) for s, x, _ in self.run)
        self.run, self.run_base, self.gap = [], None, 0

    def feed(self, t, v):
        if self.run and t - self.run[-1][0] > MAX_PAUSE_S:
            self._flush()
        base = _baseline(self.run_base, self.fixed_ms, self.normal, t, self.baseline_s)
        if base is not None and v - base > self.min_step_ms:
            self.run_base = base
            self.run.append((t, v, True))
            self.gap = 0
        elif not self.run:
            self.normal.append((t, v))
        elif self.gap < MAX_GAP:
            self.gap += 1
            self.run.append((t, v, False))
        else:
            self._flush()
            self.normal.append((t, v))

    def finish(self):
        self._flush()
        return self.events


def detect(flashes, fixed=None, min_step_ms=15.0, min_s=10.0, baseline_s=60.0, min_n=5):
    """flashes: [(epoch, label, first_ms)]. Returns [Event] in time order."""
    fixed = fixed or {}
    events = []
    for label in sorted({lab for _, lab, _ in flashes}):
        seq = [(t, v) for t, lab, v in sorted(flashes) if lab == label]
        scan = _LabelScan(label, fixed.get(label), min_step_ms, min_s, baseline_s, min_n)
        for t_, v in seq:
            scan.feed(t_, v)
        events += scan.finish()
    return sorted(events, key=lambda e: e.start)


def _fixed(spec):
    out = {}
    for part in filter(None, (spec or "").split(",")):
        k, v = part.split("=", 1)
        out[k] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser(description="Sustained first-light step detector on latency-test per_flash.csv")
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--fixed", default="", help="label=ms,... fixed reference per step label")
    ap.add_argument("--min-step-ms", type=float, default=15.0)
    ap.add_argument("--min-s", type=float, default=10.0)
    ap.add_argument("--baseline-s", type=float, default=60.0)
    ap.add_argument("--min-n", type=int, default=5)
    a = ap.parse_args()
    flashes = read_per_flash(a.csv)
    events = detect(flashes, _fixed(a.fixed), a.min_step_ms, a.min_s, a.baseline_s, a.min_n)
    labels = sorted({lab for _, lab, _ in flashes})
    for lab in labels:
        v = [x for _, l, x in flashes if l == lab]
        print(f"label {lab or '-':10s} n={len(v):4d} median={statistics.median(v):6.1f} ms")
    for e in events:
        print(f"STEP {e.label or '-'} start={e.start:.1f} end={e.end:.1f} dur={e.end - e.start:.1f}s n={e.n} "
              f"median={e.median_ms:.1f} baseline={e.baseline_ms:.1f} (+{e.median_ms - e.baseline_ms:.1f} ms)")
    if not events:
        print("no sustained step")
    return 1 if events else 0


if __name__ == "__main__":
    sys.exit(main())
