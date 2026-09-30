"""Queue signal vs loss per ramp step of openipc-1f's rate-control probe (lever_rc; their rc_fit.py imports this).

For each ramp step ("b<kbps>" labels, rc_fit's steps: up / end in AIR UPTIME seconds):
  owd_cross_s    seconds from the step's SET until the relative one-way delay (the app's rate-control value: owd.LiveBase,
                 unbounded drift-corrected base, first-packet arrival) has a window median above q_hi_ms for n_hi
                 consecutive win_s windows (the persistence rule of stats-backend §7.1; None = never)
  loss_onset_s   seconds from the SET until the first post-FEC loss (an RTP hole on the Quest; None = none)
  lead_s         loss_onset_s - owd_cross_s: positive = the delay signal came first
  owd_med_ms     the step's median OWD after a settle_s settle (rc_fit's 1 s)
  build_ms_per_mbps  (owd_med - the previous ramp step's owd_med) per Mbit/s of the step up
and build_ms_per_mbps_fit: the least-squares slope of owd_med vs kbps over the ramp steps at or above knee_kbps.
cross_skip_s (default 0) starts the crossing search that long after the SET, to step over a SET transient (on
the g56 grid every switch read as a crossing at 0 s); the crossing is still reported from the SET.

frames = [(t_air_up_s, owd_ms)], holes = [(t_start, t_end)] (air uptime s). load() makes both from a Quest Perfetto
trace; compose_offset() chains the clocks: Quest CLOCK_MONOTONIC -> Quest epoch (trace clock snapshot) -> PC (ab_detached
meta quest_minus_pc) -> air epoch (slot_watch AIR_CLOCK pc_minus_air) -> air uptime (lever_rc SAMP0 epoch/up).
docs/xr/stats-backend.md §7.5.
"""
from bisect import bisect_left
from statistics import median

import owd

Q_HI_MS = 3.0
N_HI = 2
WIN_S = 0.25
SETTLE_S = 1.0


def _cross(ts, vs, start, end, q_hi_ms, n_hi, win_s):
    """Start of the first run of n_hi consecutive windows (from start) whose median is above q_hi_ms, or None."""
    run, k = 0, 0
    while start + k * win_s < end:
        a, b = start + k * win_s, min(start + (k + 1) * win_s, end)
        i, j = bisect_left(ts, a), bisect_left(ts, b)
        if j > i and median(vs[i:j]) > q_hi_ms:
            run += 1
            if run == n_hi:
                return a - (n_hi - 1) * win_s - start
        else:
            run = 0
        k += 1
    return None


def _slope(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else None


def lead(steps, frames, holes, knee_kbps=None, q_hi_ms=Q_HI_MS, n_hi=N_HI, win_s=WIN_S, settle_s=SETTLE_S,
         cross_skip_s=0.0):
    frames = sorted(frames)
    ts, vs = [f[0] for f in frames], [f[1] for f in frames]
    t_last = ts[-1] if ts else 0.0
    starts = sorted(h[0] for h in holes)
    out, prev = [], None
    for s in steps:
        if not s["label"].startswith("b"):
            continue
        up = s["up"]
        end = s["end"] if s.get("end") is not None else t_last
        c = _cross(ts, vs, up + cross_skip_s, end, q_hi_ms, n_hi, win_s)
        cross = c + cross_skip_s if c is not None else None
        k = bisect_left(starts, up)
        loss = starts[k] - up if k < len(starts) and starts[k] < end else None
        i, j = bisect_left(ts, up + settle_s), bisect_left(ts, end)
        med = median(vs[i:j]) if j > i else None
        build = None
        if prev is not None and med is not None and prev["owd_med_ms"] is not None and s["kbps"] != prev["kbps"]:
            build = (med - prev["owd_med_ms"]) / ((s["kbps"] - prev["kbps"]) / 1000.0)
        row = {"label": s["label"], "kbps": s["kbps"], "owd_cross_s": cross, "loss_onset_s": loss,
               "lead_s": loss - cross if loss is not None and cross is not None else None,
               "owd_med_ms": med, "build_ms_per_mbps": build}
        out.append(row)
        prev = row
    fit = None
    if knee_kbps is not None:
        above = [r for r in out if r["kbps"] >= knee_kbps and r["owd_med_ms"] is not None]
        if len(above) >= 2:
            s = _slope([r["kbps"] / 1000.0 for r in above], [r["owd_med_ms"] for r in above])
            fit = s
    return {"steps": out, "build_ms_per_mbps_fit": fit}


def compose_offset(realtime_minus_mono_s, quest_minus_pc_s, pc_minus_air_s, samp0_epoch_s, samp0_up_s):
    """Quest CLOCK_MONOTONIC minus air uptime, in s: air_up = quest_mono - this."""
    # quest epoch = mono + rm; PC epoch = quest epoch - quest_minus_pc; air epoch = PC epoch - pc_minus_air;
    # air up = air epoch - (samp0_epoch - samp0_up)
    return -realtime_minus_mono_s + quest_minus_pc_s + pc_minus_air_s + (samp0_epoch_s - samp0_up_s)


def load(trace_path, quest_mono_minus_air_up_s):
    """frames [(t_air_up_s, owd_ms)] (unbounded LiveBase, the app's rate-control value) and holes [(t, t)] from a
    Quest Perfetto trace; quest_mono_minus_air_up_s from compose_offset()."""
    from ab_segments import frames_from_packets, load_trace
    from perfetto.trace_processor import TraceProcessor
    pkts, ready, _ = load_trace(trace_path)
    fr, _ = frames_from_packets(pkts, ready)
    rows = owd.per_frame(fr)
    tp = TraceProcessor(trace=trace_path)
    snap = list(tp.query("select clock_value, ts from clock_snapshot where clock_name='MONOTONIC' order by ts limit 1"))
    mono_minus_trace_s = (snap[0].clock_value - snap[0].ts) / 1e9 if snap else 0.0
    to_air = lambda t_ns: t_ns / 1e9 + mono_minus_trace_s - quest_mono_minus_air_up_s
    rel = owd.live_rel([r["t"] for r in rows], [r["first"] for r in rows], window_s=float("inf"))
    frames = [(to_air(r["t"]), x) for r, x in zip(rows, rel)]
    holes = [(to_air(t), to_air(t)) for t, _ in owd.loss_bursts(pkts)]
    return frames, holes


def realtime_minus_mono_s(trace_path):
    """Quest REALTIME - MONOTONIC (s) from the trace's clock snapshot, for compose_offset()."""
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=trace_path)
    snap = {r.clock_name: r.clock_value for r in tp.query(
        "select clock_name, clock_value from clock_snapshot where ts = (select min(ts) from clock_snapshot)")}
    return (snap["REALTIME"] - snap["MONOTONIC"]) / 1e9
