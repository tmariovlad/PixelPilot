"""Relative one-way delay (OWD) per frame, the queue signal for openipc-1f's air-side rate control
(docs/xr/stats-backend.md §7).

Usage: python3 owd.py trace.pftrace steps.txt --air-offset-s S [--guard-s 15] [--win-ms 250] [--min-s 2,10]
           [--states a,b,...] [--loss]

Per frame (ab_segments.load_trace / frames_from_packets, RTP ts on the 90 kHz clock):
  first = first-packet arrival - capture (RTP ts), last = completion (last packet) - capture, in ms with an
  arbitrary offset; each made relative to its trailing running minimum over W seconds, as a live receiver would
  (no clock sync; the air/Quest clock drift adds drift x W to the floor, reported). RTP ts is the capture time, so
  both include the air's encode time; first drops only the frame's own transmission time.
Reports per state (steps inside their guarded windows):
  (a) the noise floor: p50 / p90 of the relative OWD per window (default 250 ms), and the spread of those window
      values (median, p90, p99), which is what a threshold on a windowed p90 has to clear;
  (b) OWD first / last per state (mean, p50, p95) and the slope of OWD vs packets per frame (the frame-size effect);
  (c) with --loss: the relative OWD in 50 ms bins before each post-FEC loss burst (RTP sequence holes, bursts
      merged within 100 ms), against the same profile at shifted onsets (control).
"""
import argparse
from bisect import bisect_left
from collections import deque

from ab_segments import frames_from_packets, load_trace, pct, read_steps, step_of

MS = 1_000_000


def per_frame(frames):
    """[{t, first, last, npkts}] in first-arrival order; first/last in ms (arbitrary offset), t in ns."""
    rows = [{"t": f.first, "first": (f.first - f.capture) / MS, "last": (f.last - f.capture) / MS, "npkts": f.npkts}
            for f in frames]
    return sorted(rows, key=lambda r: r["t"])


def relative(times, values, window_ns):
    """Each value minus the minimum over the trailing window (t - window, t] (a monotonic deque)."""
    dq, out = deque(), []
    for t, v in zip(times, values):
        while dq and dq[-1][1] >= v:
            dq.pop()
        dq.append((t, v))
        while dq[0][0] <= t - window_ns:
            dq.popleft()
        out.append(v - dq[0][1])
    return out


def windows(times, values, win_ns, min_n=10):
    """[{start, n, p50, p90}] per fixed window (by time), windows with fewer than min_n frames skipped."""
    out, cur, start = [], [], None
    for t, v in zip(times, values):
        w = t // win_ns
        if start is not None and w != start:
            if len(cur) >= min_n:
                out.append({"start": start * win_ns, "n": len(cur), "p50": pct(cur, 0.5), "p90": pct(cur, 0.9)})
            cur = []
        start = w
        cur.append(v)
    if start is not None and len(cur) >= min_n:
        out.append({"start": start * win_ns, "n": len(cur), "p50": pct(cur, 0.5), "p90": pct(cur, 0.9)})
    return out


def window_summary(ws):
    if not ws:
        return {"windows": 0}
    p50, p90 = [w["p50"] for w in ws], [w["p90"] for w in ws]
    return {"windows": len(ws), "p50_median": pct(p50, 0.5), "p90_median": pct(p90, 0.5),
            "p90_p90": pct(p90, 0.9), "p90_p99": pct(p90, 0.99), "p90_max": max(p90)}


def slope(x, y):
    """Least-squares slope of y on x (0 when x has no spread)."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else 0.0


def loss_bursts(pkts, merge_ns=100 * MS):
    """[(onset_ns, packets_lost)] for RTP sequence numbers never received (as rtp_seq.seq_loss counts them: the
    16-bit numbers unwrapped with a signed step, so a late packet fills its own hole). Each lost number is timed at
    the arrival that first went past it; losses within merge_ns of the previous one join its burst."""
    useq, prev = [], None
    for _, s, _ in pkts:
        u = s if prev is None else useq[-1] + (((s - prev + 0x8000) & 0xFFFF) - 0x8000)
        useq.append(u)
        prev = s
    received = set(useq)
    lost_at = []                                  # (arrival that skipped it, count) per jump past the maximum
    top = None
    for (t, _, _), u in zip(pkts, useq):
        if top is not None and u > top + 1:
            n = sum(1 for x in range(top + 1, u) if x not in received)
            if n:
                lost_at.append((t, n))
        top = u if top is None else max(top, u)
    out, last = [], None
    for t, n in lost_at:
        if out and t - last <= merge_ns:
            out[-1] = (out[-1][0], out[-1][1] + n)
        else:
            out.append((t, n))
        last = t
    return out


def locked(times, values, onsets, bins):
    """Mean value in each bin [a, b) relative to every onset (None for an empty bin); times sorted."""
    prof = []
    for a, b in bins:
        total, n = 0.0, 0
        for o in onsets:
            i, j = bisect_left(times, o + a), bisect_left(times, o + b)
            total += sum(values[i:j])
            n += j - i
        prof.append(total / n if n else None)
    return prof


def locked_control(times, values, onsets, bins, shifts):
    """The locked profile with every onset moved by each shift (wrapping inside the data's time span): per bin the
    mean and max over the shifts."""
    t0, t1 = times[0], times[-1]
    span = t1 - t0
    profs = [locked(times, values, [t0 + (o - t0 + s) % span for o in onsets], bins) for s in shifts]
    out = []
    for i in range(len(bins)):
        vs = [p[i] for p in profs if p[i] is not None]
        out.append({"mean": sum(vs) / len(vs) if vs else None, "max": max(vs) if vs else None})
    return out


def _dist(v):
    return {"n": len(v), "mean": sum(v) / len(v), "p50": pct(v, 0.5), "p95": pct(v, 0.95)} if v else None


def drift(rows, step_idx):
    """Clock drift in ms per s: the median over steps of the slope of each step's per-second minimum of first.
    Per step, because a waybeam restart between steps moves the RTP timestamp base (a jump, not drift)."""
    per = {}
    for r, s in zip(rows, step_idx):
        if s is None:
            continue
        sec = per.setdefault(s, {})
        k = int(r["t"] // 1e9)
        sec[k] = min(sec.get(k, r["first"]), r["first"])
    slopes = sorted(slope(sorted(sec), [sec[k] for k in sorted(sec)]) for sec in per.values() if len(sec) >= 3)
    return slopes[len(slopes) // 2] if slopes else 0.0


def state_rows(rows, rel, step_idx, steps, label, win_ns):
    """Per signal (first, last) of one state: the window summary, the distribution and the ms-per-packet slope.
    Windows are cut per step, so none spans a switch, then pooled."""
    idx = [i for i, s in enumerate(step_idx) if s is not None and steps[s][1] == label]
    out = {}
    for k in ("first", "last"):
        ws = []
        for s in sorted({step_idx[i] for i in idx}):
            ii = [i for i in idx if step_idx[i] == s]
            ws += windows([rows[i]["t"] for i in ii], [rel[k][i] for i in ii], win_ns)
        out[k] = (window_summary(ws), _dist([rel[k][i] for i in idx]),
                  slope([rows[i]["npkts"] for i in idx], [rel[k][i] for i in idx]) if idx else 0.0)
    return out


def _print_state(label, per):
    for k, (sm, d, sl) in per.items():
        if not d or not sm["windows"]:
            continue
        print(f"{label:10s} {k:5s} {sm['windows']:5d} {sm['p50_median']:7.2f} {sm['p90_median']:7.2f} "
              f"{sm['p90_p90']:7.2f} {sm['p90_p99']:7.2f} {sm['p90_max']:7.2f} | {d['mean']:6.2f} "
              f"{d['p50']:6.2f} {d['p95']:6.2f} | {sl:+7.3f}")


def _print_loss(pkts, rows, rel_first, step_idx, steps, end, guard, labels):
    """The loss-locked profile over the steps of the given states only."""
    def ok(i):
        return i is not None and steps[i][1] in labels
    bursts = [(o, n) for o, n in loss_bursts(pkts) if ok(step_of(o, steps, end, guard))]
    onsets = [o for o, _ in bursts]
    bins = [(b * 50 * MS, (b + 1) * 50 * MS) for b in range(-20, 2)]
    sel = [i for i, s in enumerate(step_idx) if ok(s)]
    ts, vs = [rows[i]["t"] for i in sel], [rel_first[i] for i in sel]
    prof = locked(ts, vs, onsets, bins)
    ctl = locked_control(ts, vs, onsets, bins, [int(k * 7.919e9) for k in range(1, 21)])
    print()
    print(f"loss bursts in the steps: {len(bursts)} ({sum(n for _, n in bursts)} packets); "
          f"relative OWD first (ms) by bin before the onset, vs 20 shifted-onset controls (mean / max)")
    for (lo, hi), p, c in zip(bins, prof, ctl):
        ps = f"{p:6.3f}" if p is not None else "     -"
        cs = f"{c['mean']:6.3f} / {c['max']:6.3f}" if c["mean"] is not None else "-"
        print(f"  [{lo / MS:+5.0f},{hi / MS:+5.0f}) ms  {ps}   control {cs}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=15.0)
    ap.add_argument("--win-ms", type=float, default=250.0)
    ap.add_argument("--min-s", default="2,10")
    ap.add_argument("--states", help="comma-separated labels to report (default: all)")
    ap.add_argument("--loss", action="store_true")
    a = ap.parse_args()
    pkts, ready, rt = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    guard = a.guard_s * 1e9
    rows = per_frame(frames)
    t = [r["t"] for r in rows]
    step_idx = [step_of(x, steps, end, guard) for x in t]
    wanted = set(a.states.split(",")) if a.states else None
    labels = [lab for lab in dict.fromkeys(s[1] for s in steps) if wanted is None or lab in wanted]
    print(f"{a.trace}: {len(rows)} frames; drift (median per-step slope of the per-second minimum of first): "
          f"{drift(rows, step_idx):+.4f} ms/s")
    for w_s in [float(x) for x in a.min_s.split(",")]:
        rel = {k: relative(t, [r[k] for r in rows], w_s * 1e9) for k in ("first", "last")}
        print()
        print(f"== running minimum over {w_s:g} s; windows of {a.win_ms:g} ms ==")
        print(f"{'state':10s} {'sig':5s} {'win':>5s} {'p50med':>7s} {'p90med':>7s} {'p90p90':>7s} {'p90p99':>7s} "
              f"{'p90max':>7s} | {'mean':>6s} {'p50':>6s} {'p95':>6s} | {'ms/pkt':>7s}")
        for lab in labels:
            _print_state(lab, state_rows(rows, rel, step_idx, steps, lab, a.win_ms * MS))
        if a.loss:
            _print_loss(pkts, rows, rel["first"], step_idx, steps, end, guard, set(labels))


if __name__ == "__main__":
    main()
