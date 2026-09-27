"""In-trace A/B of an air-unit lever from ONE long Perfetto trace of the XR app (no photodiode needed).

Why one trace: arrival - RTP timestamp (the air unit's 90 kHz capture clock) is the capture -> arrival delay up to a
constant, and that constant drifts with the air/headset clock offset (~+96 ppm, ~5.8 ms per minute). Two separate
traces therefore cannot be compared. Inside one trace, with the lever switched by a timed loop on the air unit
(A B A C A ...), the drift is fitted on the baseline (A) steps only and every step is read against that line, so a
state's delta vs A is an absolute capture -> arrival (and capture -> decoded) difference in ms.

Needs the app's 'ppxr_rtp_seq' / 'ppxr_rtp_ts' counters and 'ppxr_frame_ready' slices (capture with
transport_long.pbtx), plus the air loop's step log: one line per step, "<air epoch seconds> <label>".

Usage: python3 ab_segments.py trace.pftrace steps.txt [--air-offset-s S] [--fit-offset] [--guard-s 2] [--baseline LABEL]
  --air-offset-s  Quest REALTIME minus air REALTIME, in seconds (measure both clocks against the PC before the run).
"""
import argparse
import statistics as st
from bisect import bisect_left
from collections import OrderedDict, namedtuple

from rtp_seq import seq_loss

Frame = namedtuple("Frame", "capture first last npkts ready")  # ns; capture = RTP ts on the air clock; ready or None

RTP_HZ = 90000
READY_MAX_NS = 20e6  # a decoded-frame mark more than 20 ms after the last packet belongs to another frame


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


def frames_from_packets(pkts, ready):
    """pkts: [(arrival_ns, seq, rtp_ts)] in arrival order; ready: sorted decoded-frame mark times.
    Returns (frames, lost) with frames grouped by (unwrapped) RTP timestamp."""
    lost = seq_loss([p[1] for p in pkts])[0]
    groups, base, prev = OrderedDict(), 0, None
    for t, _, ts in pkts:
        if prev is not None and ts < prev and prev - ts > 1 << 31:
            base += 1 << 32
        prev = ts
        groups.setdefault(base + ts, []).append(t)
    frames = []
    for ts, arr in groups.items():
        i = bisect_left(ready, arr[-1])
        r = ready[i] if i < len(ready) and ready[i] - arr[-1] < READY_MAX_NS else None
        frames.append(Frame(ts * 1e9 / RTP_HZ, arr[0], arr[-1], len(arr), r))
    return frames, lost


def step_window(i, steps, end, guard):
    """[start, end) of step i without its guard bands."""
    e = steps[i + 1][0] if i + 1 < len(steps) else end
    return steps[i][0] + guard, e - guard


def step_of(t, steps, end, guard):
    """Index of the step containing t, or None inside a guard band around a switch / outside the run."""
    for i in range(len(steps)):
        a, b = step_window(i, steps, end, guard)
        if a <= t < b:
            return i
    return None


def fit_drift(points):
    """Least-squares line through the lower envelope (5th percentile per 1 s window) of (t, d) points."""
    t0 = points[0][0]
    wins = {}
    for t, d in points:
        wins.setdefault(int((t - t0) // 1e9), []).append((t, d))
    env = [(st.mean(x[0] for x in w), pct([x[1] for x in w], .05)) for w in wins.values() if len(w) > 20]
    if len(env) < 2:
        raise ValueError("not enough baseline data to fit the clock drift")
    xs, ys = [e[0] for e in env], [e[1] for e in env]
    mx, my = st.mean(xs), st.mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return slope, my - slope * mx


def analyze(frames, steps, end, guard, baseline, pkts=None):
    """steps: [(start_ns, label)] sorted. Returns (per_step rows, per_state rows, slope) with delays in ms,
    each relative to the baseline's drift line. With pkts ([(arrival_ns, seq, rtp_ts)]) each row also gets the
    RTP packets lost inside the step's guarded window ("lost", "lost_per_s", "lost_pct" = lost / (received + lost))."""
    tagged = [(f, step_of(f.first, steps, end, guard)) for f in frames]
    tagged = [(f, i) for f, i in tagged if i is not None]
    slope, icpt = fit_drift([(f.last, f.last - f.capture) for f, i in tagged if steps[i][1] == baseline])
    line = lambda t: slope * t + icpt

    def stats(fs):
        span = (max(f.first for f in fs) - min(f.first for f in fs)) / 1e9
        last = [(f.last - f.capture - line(f.last)) / 1e6 for f in fs]
        first = [(f.first - f.capture - line(f.first)) / 1e6 for f in fs]
        dec = [(f.ready - f.capture - line(f.ready)) / 1e6 for f in fs if f.ready is not None]
        return {"frames": len(fs), "fps": len(fs) / span if span else 0.0,
                "pkt_per_frame": st.mean(f.npkts for f in fs),
                "spread_ms": st.mean((f.last - f.first) / 1e6 for f in fs),
                "first_ms": st.mean(first), "last_ms": st.mean(last), "last_p95_ms": pct(last, .95),
                "decoded_ms": st.mean(dec) if dec else float("nan"), "decoded_n": len(dec),
                # frames with no ppxr_frame_ready mark within READY_MAX_NS after their last packet
                # (frames_from_packets). Not "never decoded": a frame decoded later than that counts too
                # (in a decoder stall, e.g. ~78 ms, every frame would). And a missing frame can take the next
                # frame's mark if it falls within READY_MAX_NS, so real drops can be undercounted.
                "undecoded": len(fs) - len(dec)}

    per_step = [(i, lab, stats([f for f, j in tagged if j == i])) for i, (_, lab) in enumerate(steps)
                if any(j == i for _, j in tagged)]
    labels = list(OrderedDict.fromkeys(lab for _, lab in steps))
    per_state = [(lab, stats([f for f, i in tagged if steps[i][1] == lab])) for lab in labels]
    if pkts is not None:
        for i, _, row in per_step:
            a, b = step_window(i, steps, end, guard)
            seqs = [p[1] for p in pkts if a <= p[0] < b]
            row["lost"] = seq_loss(seqs)[0]
            row["received"] = len(set(seqs))  # unique, like seq_loss; raw 16-bit is fine while a window < 65536 pkts
            row["lost_per_s"] = row["lost"] / ((b - a) / 1e9)
            row["lost_pct"] = 100.0 * row["lost"] / max(1, row["received"] + row["lost"])
        for lab, row in per_state:
            mine = [r for _, l, r in per_step if l == lab]
            row["lost"] = sum(r["lost"] for r in mine)
            row["received"] = sum(r["received"] for r in mine)
            row["lost_per_s"] = st.mean(r["lost_per_s"] for r in mine)
            row["lost_pct"] = 100.0 * row["lost"] / max(1, row["received"] + row["lost"])
    for lab, s in per_state:  # a state's steps are not contiguous: its fps is the mean of its steps' fps
        s["fps"] = st.mean(ps["fps"] for _, l, ps in per_step if l == lab)
    return per_step, per_state, slope


def load_trace(path):
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    cnt = lambda name: [(r.ts, int(r.value)) for r in q(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        f"where t.name='{name}' order by c.ts")]
    seqs, tss = cnt("ppxr_rtp_seq"), cnt("ppxr_rtp_ts")
    if not seqs or len(seqs) != len(tss):
        raise SystemExit(f"missing/unpaired RTP counters: seq={len(seqs)} ts={len(tss)}")
    ready = [r.ts for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
    snap = q("select ts, clock_value from clock_snapshot where clock_name='REALTIME' order by ts limit 1")
    if not snap:
        raise SystemExit("trace has no REALTIME clock snapshot")
    realtime_minus_trace = snap[0].clock_value - snap[0].ts
    pkts = [(a[0], a[1], b[1]) for a, b in zip(seqs, tss)]
    return pkts, ready, realtime_minus_trace


def read_steps(path, air_offset_s, realtime_minus_trace):
    """Air step log -> ([(trace_ns, label)], end_ns or None). air epoch + offset = Quest REALTIME; minus the
    snapshot = trace clock. A '<epoch> END' line closes the last step; 'ERR ...' lines are reported and skipped."""
    steps, end = [], None
    for line in open(path, encoding="utf-8"):
        parts = line.split()
        if not parts or line.startswith("#"):
            continue
        if "ERR" in parts:
            print("air loop reported:", line.strip())
            continue
        try:
            t = (float(parts[0]) + air_offset_s) * 1e9 - realtime_minus_trace
        except ValueError:
            continue
        if parts[1:2] == ["PRE"]:  # the air loop's state before the first step, not a step
            continue
        if parts[1:2] == ["END"]:
            end = t
        elif len(parts) >= 2:
            steps.append((t, parts[1]))
    return sorted(steps), end


def fit_offset(frames, steps, end, span_s=3.0, res_s=0.01):
    """Shift (s) to add to the steps so that packets/frame is most constant within each step: minimises the
    within-step variance of npkts (coarse 0.1 s scan, then res_s around the best). Only meaningful when the lever
    changes packets/frame (e.g. bitrate)."""
    firsts = [f.first for f in frames]
    npk = [f.npkts for f in frames]

    def cost(sh):
        starts = [s + sh for s, _ in steps] + [end + sh]
        total = 0.0
        for a, b in zip(starts, starts[1:]):
            g = npk[bisect_left(firsts, a):bisect_left(firsts, b)]
            if g:
                m = sum(g) / len(g)
                total += sum((x - m) ** 2 for x in g)
        return total

    scan = lambda lo, hi, step: min((cost(k * step * 1e9), k * step) for k in range(int(round(lo / step)), int(round(hi / step)) + 1))
    _, coarse = scan(-span_s, span_s, 0.1)
    return scan(coarse - 0.1, coarse + 0.1, res_s)[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=2.0)
    ap.add_argument("--baseline", help="label of the reference state (default: the first step's label)")
    ap.add_argument("--csv", help="also write the per-step rows to this CSV file")
    ap.add_argument("--fit-offset", action="store_true",
                    help="refine --air-offset-s (±3 s) from the packets/frame steps (levers that change the packet count)")
    a = ap.parse_args()
    pkts, ready, rt_off = load_trace(a.trace)
    frames, lost = frames_from_packets(pkts, ready)
    steps, loop_end = read_steps(a.steps, a.air_offset_s, rt_off)
    end = min(pkts[-1][0], loop_end) if loop_end else pkts[-1][0]
    if a.fit_offset:
        shift = fit_offset(frames, steps, end)
        print(f"offset fitted from packets/frame: {a.air_offset_s + shift:+.2f} s (given {a.air_offset_s:+.2f}, shift {shift:+.2f})")
        steps = [(t + shift * 1e9, lab) for t, lab in steps]
        end = min(pkts[-1][0], loop_end + shift * 1e9) if loop_end else end
    baseline = a.baseline or steps[0][1]
    inside = sum(1 for f in frames if steps[0][0] <= f.first < end)
    print(f"{len(pkts)} packets, {len(frames)} frames, {lost} lost before the app; {inside} frames inside the steps")
    per_step, per_state, slope = analyze(frames, steps, end, a.guard_s * 1e9, baseline, pkts)
    print(f"clock drift fitted on '{baseline}': {slope * 1e6:+.0f} ppm")
    hdr = f"{'':14s}{'frames':>7s}{'fps':>7s}{'pkt/f':>7s}{'spread':>8s}{'first':>8s}{'last':>8s}{'last95':>8s}{'decoded':>9s}{'lost/s':>8s}{'lost%':>7s}{'undec':>6s}"
    row = lambda name, s: (f"{name:14s}{s['frames']:7d}{s['fps']:7.1f}{s['pkt_per_frame']:7.2f}{s['spread_ms']:8.2f}"
                           f"{s['first_ms']:8.2f}{s['last_ms']:8.2f}{s['last_p95_ms']:8.2f}{s['decoded_ms']:9.2f}"
                           f"{s.get('lost_per_s', float('nan')):8.1f}{s.get('lost_pct', float('nan')):7.2f}{s['undecoded']:6d}")
    print("\nper step (ms vs the baseline drift line; 'last' = frame complete, 'decoded' = decoder output)")
    print(hdr)
    for i, lab, s in per_step:
        print(row(f"{i:2d} {lab}", s))
    if a.csv:
        import csv
        keys = ["frames", "fps", "pkt_per_frame", "spread_ms", "first_ms", "last_ms", "last_p95_ms", "decoded_ms", "lost", "lost_per_s",
                "lost_pct", "undecoded"]  # append only: docs/xr/data/*-ab.csv keep the earlier column order
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["step", "label"] + keys)
            for i, lab, row_ in per_step:
                w.writerow([i, lab] + [round(row_.get(k, float('nan')), 3) for k in keys])
        print(f"per-step rows written to {a.csv}")
    print("\nper state")
    print(hdr + f"{'Δlast':>8s}{'Δdecoded':>10s}")
    ref = dict(per_state)[baseline]
    for lab, s in per_state:
        print(row(lab, s) + f"{s['last_ms'] - ref['last_ms']:+8.2f}{s['decoded_ms'] - ref['decoded_ms']:+10.2f}")


if __name__ == "__main__":
    main()
