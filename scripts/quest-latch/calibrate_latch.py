"""Calibrate the phase meter's constants from a Perfetto trace of the XR app (compositor.pbtx).

Needs the app's own trace markers: counter 'ppxr_display_minus_now_us' (predictedDisplayTime - now at
each xrWaitFrame) and slice 'ppxr_frame_ready' (the time the app records a frame as ready).
Prints:
  latch -> predictedDisplayTime   = LatencyExperiments.DEFAULT_LATCH_TO_DISPLAY_US (circular mean)
  app frame-ready -> queueBuffer  = how much later the compositor actually sees the frame
Usage: python3 calibrate_latch.py trace.pftrace
"""
import math
import statistics as st
import sys
from bisect import bisect_left
from perfetto.trace_processor import TraceProcessor


def circ_mean(values, period):
    c = sum(math.cos(2 * math.pi * v / period) for v in values)
    s = sum(math.sin(2 * math.pi * v / period) for v in values)
    return (math.atan2(s, c) % (2 * math.pi)) / (2 * math.pi) * period, math.hypot(c, s) / len(values)


tp = TraceProcessor(trace=sys.argv[1])
q = lambda s: list(tp.query(s))
pdt = sorted(r.ts + int(r.value) * 1000 for r in q(
    "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id where t.name='ppxr_display_minus_now_us'"))
vid = q("""select distinct s.name from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name like 'dequeueBuffer - SurfaceTexture%'""")[0].name.split(" - ")[1]
latch = [r.ts for r in q(f"""select p.ts from slice s join slice p on s.parent_id=p.id join thread_track tt on p.track_id=tt.id
  join thread t using(utid) where t.name='OVR::TimeWarp' and p.name='acquireBuffer' and s.name like '{vid}:%' order by p.ts""")]
ready = [r.ts for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
qb = [r.ts + r.dur for r in q("""select s.ts, s.dur from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name='queueBuffer' order by s.ts""")]
if not pdt or not latch:
    sys.exit(f"missing markers: pdt={len(pdt)} latch={len(latch)}")
period = st.median(b - a for a, b in zip(pdt, pdt[1:]) if 0 < b - a < 20e6)

# latch -> the next predicted display time after it
offs = []
for L in latch:
    i = bisect_left(pdt, L)
    if i < len(pdt):
        offs.append(pdt[i] - L)
mean, conc = circ_mean(offs, period)
print(f"display period {period/1e6:.4f} ms, latches {len(latch)}")
print(f"latch -> predictedDisplayTime: circular mean {mean/1e3:.0f} us (conc {conc:.3f}); "
      f"linear p5/p50/p95 = {sorted(offs)[len(offs)//20]/1e3:.0f}/{st.median(offs)/1e3:.0f}/{sorted(offs)[-len(offs)//20]/1e3:.0f} us")

d = []
for t in ready:
    i = bisect_left(qb, t)
    if i < len(qb) and qb[i] - t < 5e6:
        d.append(qb[i] - t)
if d:
    d.sort()
    print(f"app frame-ready -> queueBuffer: n={len(d)} p5/p50/p95 = {d[len(d)//20]/1e3:.0f}/{d[len(d)//2]/1e3:.0f}/{d[-len(d)//20]/1e3:.0f} us")
