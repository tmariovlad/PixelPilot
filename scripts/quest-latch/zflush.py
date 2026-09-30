"""-Z analysis (the air's wfb_tx closes the FEC block at each RTP frame end): per frame, whether it needed FEC recovery
and whether its last packet waited for the next frame's packets, and how long frames take to complete, per state.

Usage: python3 zflush.py trace.pftrace steps.txt capture.txt --air-offset-s S --baseline LABEL [--guard-s 4]
           [--air-log wfbtx.log --air-mono-minus-epoch-ms M] [--by-step]

Inputs (one slot):
- trace: the Perfetto trace with the app's per-packet ppxr_rtp_seq / ppxr_rtp_ts counters (ab_segments.load_trace).
  Frames = packets grouped by RTP timestamp; complete = first -> last packet (ms); capture -> last = ms above the
  baseline state's drift line, as big_frames.py.
- steps.txt: the air's step log (air epoch, ab_segments.read_steps).
- capture.txt: the detached logcat with PPXR_RELEASE (app/wfbngrtl8812/.../ReleaseProbe.h): one line per wfb-ng release
  call that was not a plain on-arrival delivery, listing the frames it released (RTP ts, seq range, marker) and the
  fragments recovered in it.
- --air-log: the air's /tmp/wfbtx.log; with -Z it has FRAME_FLUSH frame_ends:blocks_closed:fillers per interval
  (wfb-ng o117-marker-flush tx.cpp:827). Its timestamps are the air's CLOCK_MONOTONIC ms; M = air uptime ms minus
  air epoch ms, read together on the air.

Frame classes (defined only here): recovered = released in a call with rec > 0 (a fragment rebuilt from parity);
held = released late in a call without recovery (queued behind a gap, then flushed); clean = neither.
waited_next = the frame's marker packet shares a release call with a later frame's packets (wfb-ng rx.cpp releases
in slot order): its block could only close with the next frame's data or with parity sent after it, which is what
-Z removes. docs/xr/fec-block-probe.md §7.
"""
import argparse
import statistics as st

from ab_segments import RTP_HZ, baseline_line, frames_from_packets, load_trace, pct, read_steps, step_of
from air_drops import parse_intervals
from stats_log import parse_kv

TAG = " PPXR_RELEASE: "
CLASSES = ("clean", "recovered", "held")
FLUSH_FIELDS = ("frame_ends", "blocks_closed", "fillers")


def parse(line):
    i = line.find(TAG)
    if i < 0:
        return None
    kv = parse_kv(line[i + len(TAG):])
    if "rec" not in kv or "frames" not in kv:
        return None
    frames = []
    for g in kv["frames"].split(","):
        if not g:
            continue
        ts, seqs, m = g.split(":")
        first, last = seqs.split("-")
        frames.append((int(ts), int(first), int(last), m == "1"))
    return {"t_mono_ms": int(kv["t_mono_ms"]), "rec": int(kv["rec"]), "n": int(kv["n"]), "frames": frames,
            "more": int(kv.get("more") or 0), "suppressed": int(kv.get("suppressed") or 0)}


def frame_flags(lines):
    """{rtp ts: {"recovered": bool, "waited_next": bool}} for every frame a logged release call touched."""
    flags = {}
    for r in (parse(line) for line in lines):
        if r is None:
            continue
        for i, (ts, _, _, marker) in enumerate(r["frames"]):
            f = flags.setdefault(ts, {"recovered": False, "waited_next": False})
            f["recovered"] = f["recovered"] or r["rec"] > 0
            f["waited_next"] = f["waited_next"] or (marker and i < len(r["frames"]) - 1)
    return flags


def ts32(frame):
    """The frame's 32-bit RTP timestamp (the trace's frames carry it unwrapped, as capture ns)."""
    return int(round(frame.capture * RTP_HZ / 1e9)) & 0xFFFFFFFF


def frame_class(frame, flags):
    f = flags.get(ts32(frame))
    if f is None:
        return "clean"
    return "recovered" if f["recovered"] else "held"


def dist(values):
    if not values:
        return None
    return {"n": len(values), "mean": st.mean(values), "p95": pct(values, 0.95), "p99": pct(values, 0.99)}


def rows(frames, flags, steps, end, guard_ns, line, by_step=False):
    """Per state (or per step): frames, per class the first -> last and capture -> last distributions (ms), and the
    waited-for-next-frame shares."""
    groups = {}
    for f in frames:
        i = step_of(f.first, steps, end, guard_ns)
        if i is not None:
            groups.setdefault(f"{i:2d} {steps[i][1]}" if by_step else steps[i][1], []).append(f)
    out = {}
    for key, fs in groups.items():
        row: dict = {"frames": len(fs)}
        for c in CLASSES:
            cf = [f for f in fs if frame_class(f, flags) == c]
            row[c] = {"complete": dist([(f.last - f.first) / 1e6 for f in cf]),
                      "capture_last": dist([(f.last - f.capture - line(f.last)) / 1e6 for f in cf])}
        waited = [f for f in fs if flags.get(ts32(f), {}).get("waited_next")]
        recovered = [f for f in fs if frame_class(f, flags) == "recovered"]
        row["waited_next_share"] = len(waited) / len(fs)
        row["waited_next_of_recovered"] = (sum(1 for f in recovered if flags[ts32(f)]["waited_next"]) / len(recovered)
                                           if recovered else None)
        out[key] = row
    return out


def air_per_step(intervals, to_trace_ns, steps, end, guard_ns, by_step=False):
    """FRAME_FLUSH counters summed per state (or step), each interval assigned by its end time; "ms" sums the
    intervals' own lengths (end - start, air ms), for rates."""
    out = {}
    for b, e, c in intervals:
        i = step_of(to_trace_ns(e), steps, end, guard_ns)
        if i is None or len(c) < 3:
            continue
        s = out.setdefault(f"{i:2d} {steps[i][1]}" if by_step else steps[i][1],
                           {"intervals": 0, "ms": 0, **{k: 0 for k in FLUSH_FIELDS}})
        s["intervals"] += 1
        s["ms"] += e - b
        for k, v in zip(FLUSH_FIELDS, c):
            s[k] += int(v)
    return out


def _fmt(d):
    return f"{d['n']:5d}{d['mean']:7.2f}{d['p95']:7.2f}{d['p99']:7.2f}" if d else f"{0:5d}" + " " * 21


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("capture")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--guard-s", type=float, default=4.0)
    ap.add_argument("--air-log")
    ap.add_argument("--air-mono-minus-epoch-ms", type=float)
    ap.add_argument("--by-step", action="store_true")
    a = ap.parse_args()
    pkts, ready, rt = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    guard = a.guard_s * 1e9
    with open(a.capture, encoding="utf-8", errors="replace") as fh:
        flags = frame_flags(fh)
    slope, icpt = baseline_line(frames, steps, end, guard, a.baseline)
    line = lambda t: slope * t + icpt
    print("complete = first -> last packet; capture->last = ms above the baseline drift line; n mean p95 p99")
    print(f"{'':14s}{'frames':>7s} | {'class':9s}{'n':>5s}{'mean':>7s}{'p95':>7s}{'p99':>7s} |"
          f"{'n':>5s}{'mean':>7s}{'p95':>7s}{'p99':>7s} | waited_next all / of recovered")
    for key, row in rows(frames, flags, steps, end, guard, line, a.by_step).items():
        for j, c in enumerate(CLASSES):
            head = f"{key:14s}{row['frames']:7d}" if j == 0 else " " * 21
            tail = ""
            if j == 0:
                w = row["waited_next_of_recovered"]
                tail = f" | {row['waited_next_share']:.3f} / {w:.3f}" if w is not None else \
                    f" | {row['waited_next_share']:.3f} / -"
            print(f"{head} | {c:9s}{_fmt(row[c]['complete'])} |{_fmt(row[c]['capture_last'])}{tail}")
    if a.air_log:
        if a.air_mono_minus_epoch_ms is None:
            raise SystemExit("--air-log needs --air-mono-minus-epoch-ms (air uptime ms - air epoch ms)")
        with open(a.air_log, encoding="utf-8", errors="replace") as fh:
            iv = parse_intervals(fh, "FRAME_FLUSH")
        to_trace = lambda air_ms: ((air_ms - a.air_mono_minus_epoch_ms) / 1000 + a.air_offset_s) * 1e9 - rt
        print("air FRAME_FLUSH per state: intervals frame_ends blocks_closed fillers")
        for key, s in air_per_step(iv, to_trace, steps, end, guard, a.by_step).items():
            print(f"{key:14s}{s['intervals']:5d}{s['frame_ends']:9d}{s['blocks_closed']:9d}{s['fillers']:9d}")


if __name__ == "__main__":
    main()
