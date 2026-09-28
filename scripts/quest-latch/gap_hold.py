"""Frames right after an RTP sequence gap vs all other frames: frame complete (last packet) -> decoded.

The app's BufferedPacketQueue (app/videonative/src/main/cpp/BufferedPacketQueue.h) holds packets after a sequence
gap until a few in-order packets arrive or a time bound passes, in case the gap is a reorder (upstream 5 packets /
20 ms; the pref rtp_tight_reorder selects 2 / 3 ms). This shows what that hold costs on a real link, from Perfetto
traces with the app's RTP counters and frame-ready marks (mode_segment.sh / compositor.pbtx, ab_long.sh): frames
whose last packet arrived within HOLD_PKTS packets after a gap are "after-gap".

Usage:
  python3 gap_hold.py out/mode_*.pftrace                         one line per trace
  python3 gap_hold.py trace.pftrace --steps out/steps_<label>.txt [--guard-s 12]
                                                                 one line per step of a pref_ab.sh run, plus the
                                                                 per-value totals, each with its packet loss
                                                                 (Quest clock, as pref_ab logs it)
"""
import argparse
import statistics as st
from bisect import bisect_left
from collections import OrderedDict, defaultdict

HOLD_PKTS = 6  # upstream monotonic threshold 5 + the gap packet: the widest window a frame can be held in
READY_MAX_NS = 40e6  # a frame held for the full upstream 20 ms must still find its decoded mark


def frame_delays(pkts, ready, hold_pkts=HOLD_PKTS):
    """pkts: [(arrival_ns, seq, rtp_ts)] in arrival order; ready: sorted decoded-frame times.
    Returns [(last_arrival_ns, complete_to_decoded_ms, after_gap)] per frame that has a decoded mark, and the number
    of sequence gaps. A frame is after-gap if its last packet arrived within hold_pkts packets after a gap."""
    after, gaps = set(), 0
    for i in range(1, len(pkts)):
        step = ((pkts[i][1] - pkts[i - 1][1] + 0x8000) & 0xFFFF) - 0x8000  # signed 16-bit step
        if step > 1:
            gaps += 1
            after.update(range(i, min(len(pkts), i + hold_pkts)))
    frames = OrderedDict()
    for i, (t, _, ts) in enumerate(pkts):
        frames.setdefault(ts, []).append((t, i))
    out = []
    for v in frames.values():
        last_t, last_i = v[-1]
        k = bisect_left(ready, last_t)
        if k < len(ready) and ready[k] - last_t < READY_MAX_NS:
            out.append((last_t, (ready[k] - last_t) / 1e6, last_i in after))
    return out, gaps


def packet_loss(pkts, window_of):
    """Lost packets per window: {window: (received, lost)}, counting sequence gaps between consecutive arrivals
    whose later packet falls in that window (window_of(arrival_ns) -> key or None)."""
    out = {}
    for i in range(1, len(pkts)):
        w = window_of(pkts[i][0])
        if w is None:
            continue
        step = ((pkts[i][1] - pkts[i - 1][1] + 0x8000) & 0xFFFF) - 0x8000
        n, lost = out.get(w, (0, 0))
        out[w] = (n + 1, lost + max(0, step - 1))
    return out


def loss_text(n, lost):
    return f"loss {100 * lost / (n + lost):.2f} % ({lost}/{n + lost})" if n else "loss n/a"


def summary(name, delays, gaps=None):
    held = [d for _, d, a in delays if a]
    clean = [d for _, d, a in delays if not a]
    hm = f"{st.mean(held):6.2f}" if held else "   n/a"
    cm = f"{st.mean(clean):5.2f}" if clean else "  n/a"
    allm = f"{st.mean(held + clean):5.2f}" if held or clean else "  n/a"
    g = f"gaps {gaps:3d}  " if gaps is not None else ""
    return (f"{name:24s} {g}after-gap frames {len(held):3d} mean {hm} ms | other {len(clean):4d} mean {cm} ms"
            f" | mean over all {allm} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--steps", help="pref_ab.sh step log (Quest epoch, value); needs exactly one trace")
    ap.add_argument("--guard-s", type=float, default=12.0, help="skip this long after each switch (app restart)")
    a = ap.parse_args()
    from ab_segments import load_trace, read_steps, step_of
    if not a.steps:
        for path in a.traces:
            pkts, ready, _ = load_trace(path)
            d, g = frame_delays(pkts, ready)
            print(summary(path.replace("\\", "/").split("/")[-1], d, g))
        return
    if len(a.traces) != 1:
        raise SystemExit("--steps needs exactly one trace")
    pkts, ready, rt_minus_trace = load_trace(a.traces[0])
    steps, end = read_steps(a.steps, 0.0, rt_minus_trace)
    end = end if end is not None else pkts[-1][0]
    guard = a.guard_s * 1e9
    d, _ = frame_delays(pkts, ready)
    per_step, per_value = defaultdict(list), defaultdict(list)
    for f in d:
        i = step_of(f[0], steps, end, guard)
        if i is not None:
            per_step[i].append(f)
            per_value[steps[i][1].split(":")[-1]].append(f)
    loss = packet_loss(pkts, lambda t: step_of(t, steps, end, guard))
    per_value_loss = defaultdict(lambda: (0, 0))
    for i, (_, label) in enumerate(steps):
        n, lost = loss.get(i, (0, 0))
        v = label.split(":")[-1]
        per_value_loss[v] = (per_value_loss[v][0] + n, per_value_loss[v][1] + lost)
        print(summary(f"step {i + 1} {label}", per_step[i]) + " | " + loss_text(n, lost))
    for value, fs in sorted(per_value.items()):
        print(summary(f"ALL {value}", fs) + " | " + loss_text(*per_value_loss[value]))


if __name__ == "__main__":
    main()
