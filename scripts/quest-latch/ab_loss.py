"""Per-step RTP loss and undecoded frames for an in-trace A/B run (companion to ab_segments.py, same inputs).

'lost' = RTP sequence gaps the app saw, i.e. what wfb-ng FEC could not repair; 'undec' = frames with no
'ppxr_frame_ready' mark. The same 2 s guard around every switch as ab_segments.py.

Usage: python3 ab_loss.py trace.pftrace steps.txt AIR_OFFSET_S
  AIR_OFFSET_S  the offset ab_segments.py used (after --fit-offset, the fitted value it printed).
"""
import sys
from collections import defaultdict

from ab_segments import load_trace, read_steps, frames_from_packets, step_of
from rtp_seq import seq_loss

trace, steps_path, offset_s = sys.argv[1], sys.argv[2], float(sys.argv[3])
pkts, ready, rt_off = load_trace(trace)
frames, _ = frames_from_packets(pkts, ready)
steps, end = read_steps(steps_path, offset_s, rt_off)
guard = 2e9

by_step = defaultdict(list)
for t, seq, _ in pkts:
    i = step_of(t, steps, end, guard)
    if i is not None:
        by_step[i].append(seq)
fr = defaultdict(lambda: [0, 0])
for f in frames:
    i = step_of(f.first, steps, end, guard)
    if i is not None:
        fr[i][0] += 1
        fr[i][1] += f.ready is None

state = defaultdict(lambda: [0, 0, 0, 0])
print(f"{'step':14s}{'pkts':>7s}{'lost':>6s}{'loss%':>7s}{'frames':>8s}{'undec':>7s}")
for i, (_, lab) in enumerate(steps):
    seqs = by_step[i]
    lost = seq_loss(seqs)[0] if seqs else 0
    n, und = fr[i]
    print(f"{i:2d} {lab:11s}{len(seqs):7d}{lost:6d}{100 * lost / max(1, len(seqs) + lost):7.2f}{n:8d}{und:7d}")
    s = state[lab]
    s[0] += len(seqs); s[1] += lost; s[2] += n; s[3] += und
print("\nper state")
for lab, (p, l, n, u) in state.items():
    print(f"{lab:14s}{p:7d}{l:6d}{100 * l / max(1, p + l):7.2f}{n:8d}{u:7d}")
