"""Where do the missing frames go? Per step, every frame the air encoded (RTP timestamps on a 90 kHz clock, one per
1/fps s) is put into one class:
  complete+decoded  every RTP packet of the frame arrived and a ppxr_frame_ready mark followed (<= 20 ms);
  (a) hole          at least one packet of the frame was missing after FEC. For H.264 the app's RTP depacketizer drops
                    the NAL unit (ParseRTP.cpp: flagPacketHasGoneMissing -> no forwardNALU unless the
                    feed_incomplete_frames lever is on); the H.265 path forwards it truncated;
  (a') edge         a sequence gap sits exactly between this frame and the previous one: the missing packets are the
                    tail of one frame or the head of the next, so one of the two is incomplete (counted here once);
  (b) complete, not decoded   all packets arrived but no decoded mark followed. Also holds the other side of an
                    edge whose missing packets were this frame's tail;
  (c) never arrived no packet of that RTP timestamp arrived at all.
Decoded marks are matched one-to-one, in order, to frames without a hole or edge (a mark 20 ms after a dropped
frame is usually the next frame's). Tests: test_frame_fate.py.
Output per step: counts per second of each class and the decoded fps predicted from them vs the measured decoded fps.

Usage: python3 frame_fate.py trace.pftrace steps.txt --air-offset-s S [--guard-s 4] [--fps 90]
"""
import argparse
from bisect import bisect_left

from ab_segments import READY_MAX_NS, load_trace, read_steps, step_window


def classify(pkts, ready, fps, a, b):
    """pkts [(ns, seq16, rtp_ts32)] in arrival order, ready sorted ns. Frames whose first packet is in [a, b).
    Returns a dict of counts."""
    inwin = [p for p in pkts if a <= p[0] < b]
    if len(inwin) < 10:
        return None
    step_ts = round(90000 / fps)
    # unwrap sequence numbers in arrival order
    useq, prev = [], None
    for _, s, _ in inwin:
        if prev is None:
            useq.append(s)
        else:
            useq.append(useq[-1] + (((s - prev + 0x8000) & 0xFFFF) - 0x8000))
        prev = s
    frames = {}   # ts -> [seqs]
    order = []
    for (t, _, ts), u in zip(inwin, useq):
        if ts not in frames:
            frames[ts] = []
            order.append((t, ts))
        frames[ts].append((u, t))
    # frames sorted by their first sequence number
    fl = sorted(((min(u for u, _ in v), max(u for u, _ in v), ts, v) for ts, v in frames.items()))
    res = {"decoded": 0, "hole": 0, "edge": 0, "not_decoded": 0, "never": 0}
    hole = {ts for lo, hi, ts, v in fl if (hi - lo + 1) - len({u for u, _ in v}) > 0}
    edge = set()
    for i in range(1, len(fl)):
        if fl[i][0] - fl[i - 1][1] > 1 and fl[i - 1][2] not in edge:
            edge.add(fl[i][2])
    # Each ready mark belongs to one frame. Frames are ~11 ms apart at 90 fps, so "a mark within 20 ms" alone would
    # give a dropped frame the next frame's mark; frames decode in order, so match greedily by last arrival, and
    # only frames that can be decoded (no known hole, no gap before them). Ambiguity left: when an edge's missing
    # packets were the previous frame's tail, that previous frame can still take the edge frame's mark.
    got = set()
    j = 0
    for last_t, ts in sorted((max(t for _, t in v), ts) for _, _, ts, v in fl if ts not in hole and ts not in edge):
        j = bisect_left(ready, last_t, j)
        if j < len(ready) and ready[j] - last_t < READY_MAX_NS:
            got.add(ts)
            j += 1
    for _, _, ts, _ in fl:
        res["hole" if ts in hole else "edge" if ts in edge else "decoded" if ts in got else "not_decoded"] += 1
    # frames that never arrived: RTP timestamps on the frame grid between the first and last received one
    tss = sorted(ts for _, _, ts, _ in fl)
    if len(tss) > 1:
        span_frames = round(((tss[-1] - tss[0]) & 0xFFFFFFFF) / step_ts) + 1
        res["never"] = max(0, span_frames - len(tss))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("--air-offset-s", type=float, default=0.0)
    ap.add_argument("--guard-s", type=float, default=4.0)
    ap.add_argument("--fps", type=float, default=90.0)
    x = ap.parse_args()
    pkts, ready, rt = load_trace(x.trace)
    steps, end = read_steps(x.steps, x.air_offset_s, rt)
    print(f"{'':16s}{'decoded/s':>10s}{'(a)hole/s':>10s}{'(a)edge/s':>10s}{'(b)ndec/s':>10s}{'(c)never/s':>11s}"
          f"{'measured dec/s':>15s}")
    for i, (_, lab) in enumerate(steps):
        a, b = step_window(i, steps, end, x.guard_s * 1e9)
        r = classify(pkts, ready, x.fps, a, b)
        if r is None:
            continue
        secs = (b - a) / 1e9
        meas = sum(1 for t in ready if a <= t < b) / secs
        print(f"{i:2d} {lab:13s}" + "".join(f"{r[k] / secs:10.1f}" for k in ("decoded", "hole", "edge", "not_decoded"))
              + f"{r['never'] / secs:11.1f}{meas:15.1f}")


if __name__ == "__main__":
    main()
