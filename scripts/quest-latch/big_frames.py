"""Latency of the largest frames apart from the rest, per step and per state. A scene change (the G2G rig's LED flash in
front of the camera) or an IDR frame is several times the usual packet count, and its last packet reaches the Quest
tens of ms later. A lever that queues bursts instead of dropping them (e.g. a bigger wfb_tx input buffer on the air)
shows up in these frames' tail, not in the step mean.

"Big" = npkts at or above --pct (default p98) of all the frames inside the steps. Latency = capture -> last packet on
the baseline's drift line (ab_segments.py), so it needs one RTP timestamp base across the run (no waybeam restart).

Usage: python3 big_frames.py trace.pftrace steps.txt --air-offset-s S --baseline LABEL [--guard-s 4] [--pct 0.98]
"""
import argparse
import statistics as st

from ab_segments import fit_drift, frames_from_packets, load_trace, pct, read_steps, step_of


def split_stats(frames, line, threshold):
    """frames above/below threshold packets -> (big stats or None, rest stats); latencies in ms above line(t_last)."""
    def stats(fs):
        if not fs:
            return None
        lat = [(f.last - f.capture - line(f.last)) / 1e6 for f in fs]
        return {"n": len(fs), "pkts": st.mean(f.npkts for f in fs), "last": st.mean(lat), "p50": pct(lat, .5),
                "p95": pct(lat, .95), "max": max(lat)}
    return stats([f for f in frames if f.npkts >= threshold]), stats([f for f in frames if f.npkts < threshold])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=4.0)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--pct", type=float, default=0.98)
    a = ap.parse_args()
    pkts, ready, rt = load_trace(a.trace)
    frames, _ = frames_from_packets(pkts, ready)
    steps, end = read_steps(a.steps, a.air_offset_s, rt)
    end = end if end else pkts[-1][0]
    tagged = [(f, step_of(f.first, steps, end, a.guard_s * 1e9)) for f in frames]
    tagged = [(f, i) for f, i in tagged if i is not None]
    slope, icpt = fit_drift([(f.last, f.last - f.capture) for f, i in tagged if steps[i][1] == a.baseline])
    line = lambda t: slope * t + icpt
    thr = pct([f.npkts for f, _ in tagged], a.pct)
    print(f"big = npkts >= {thr:.0f} (p{a.pct * 100:.0f} of the frames in the steps); ms above the '{a.baseline}' drift line")
    print(f"{'':16s}{'big n':>6s}{'pkts':>6s}{'last':>7s}{'p50':>7s}{'p95':>7s}{'max':>7s} |{'rest n':>7s}{'last':>7s}{'p95':>7s}")
    labels = list(dict.fromkeys(lab for _, lab in steps))
    groups = [(f"{i:2d} {lab}", [f for f, j in tagged if j == i]) for i, (_, lab) in enumerate(steps)]
    groups += [("", None)] + [(lab, [f for f, j in tagged if steps[j][1] == lab]) for lab in labels]
    for name, fs in groups:
        if fs is None:
            print("per state")
            continue
        big, rest = split_stats(fs, line, thr)
        if rest is None:
            continue
        b = (f"{big['n']:6d}{big['pkts']:6.0f}{big['last']:7.2f}{big['p50']:7.2f}{big['p95']:7.2f}{big['max']:7.2f}"
             if big else f"{0:6d}" + " " * 30)
        print(f"{name:16s}{b} |{rest['n']:7d}{rest['last']:7.2f}{rest['p95']:7.2f}")


if __name__ == "__main__":
    main()
