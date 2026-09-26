"""Compositor phase on Quest (Horizon OS) from a Perfetto trace: when the compositor takes the video
frame relative to vsync, and how long a decoded frame waits for it.

Anchors: the display HAL's DRM vsync callback (SDM_EventThread 'HWEventsDRM::VSyncHandlerCallback'),
OVR::TimeWarp 'acquireBuffer' of the video SurfaceTexture (the latch), TimeWarp
'dequeueBuffer - TotallyFake' (start of each compositor pass), and the decoder's 'queueBuffer' on
CodecLooper (frame ready). Kernel drm/sde ftrace events are not available on user builds.

Capture (XR app streaming, Guardian paused so the session stays FOCUSED):
    adb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/t.pftrace' < compositor.pbtx
    adb pull /data/misc/perfetto-traces/t.pftrace
Analyse:  pip install perfetto;  python3 latch_analyze.py t.pftrace
"""
import statistics as st
import sys
from bisect import bisect_right
from perfetto.trace_processor import TraceProcessor

tp = TraceProcessor(trace=sys.argv[1])
q = lambda s: list(tp.query(s))

vs = [r.ts for r in q("""select s.ts from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='SDM_EventThread' and s.name like 'HWEventsDRM::VSyncHandlerCallback%' order by s.ts""")]
d = [b - a for a, b in zip(vs, vs[1:])]
P = st.median([x for x in d if 5e6 < x < 15e6])
jit = [x - P for x in d if 5e6 < x < 15e6]
print(f"vsync callbacks={len(vs)} period={P/1e6:.4f} ms  interval jitter p95={sorted(abs(j) for j in jit)[int(.95*len(jit))]/1e3:.1f} us")

def phase(t):  # time since the last vsync (nearest callback within 50 ms; None if too far)
    i = bisect_right(vs, t)
    cands = [vs[k] for k in (i - 1, i) if 0 <= k < len(vs)]
    cb = min(cands, key=lambda c: abs(c - t))
    return (t - cb) % P if abs(t - cb) < 50e6 else None

vid = q("""select distinct s.name from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name like 'dequeueBuffer - SurfaceTexture%'""")[0].name.split(" - ")[1]
print("video surface:", vid)
latch = [r.ts for r in q(f"""select p.ts from slice s join slice p on s.parent_id=p.id join thread_track tt on p.track_id=tt.id
  join thread t using(utid) where t.name='OVR::TimeWarp' and p.name='acquireBuffer' and s.name like '{vid}:%' order by p.ts""")]
passes = [r.ts for r in q("""select s.ts from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='OVR::TimeWarp' and s.name='dequeueBuffer - TotallyFake' order by s.ts""")]
qb = [r.ts + r.dur for r in q("""select s.ts, s.dur from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name='queueBuffer' order by s.ts""")]
acq_all = [r.ts for r in q("""select s.ts from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='OVR::TimeWarp' and s.name='acquireBuffer' order by s.ts""")]

def summ(name, xs, unit=1e6):
    xs = sorted(xs)
    if not xs:
        print(name, "none"); return
    pct = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))] / unit
    print(f"{name:44s} n={len(xs):4d} mean={st.mean(xs)/unit:6.2f} p5={pct(.05):6.2f} p50={pct(.5):6.2f} p95={pct(.95):6.2f} max={xs[-1]/unit:6.2f} ms")

ph = lambda arr: [p for p in (phase(t) for t in arr) if p is not None]
summ("TW pass start: phase after vsync", ph(passes))
summ("TW acquireBuffer (any): phase after vsync", ph(acq_all))
summ("video latch: phase after vsync", ph(latch))
pd = [b - a for a, b in zip(passes, passes[1:])]
summ("TW pass interval", pd)
# wait: decoder queueBuffer -> the latch that picks it up (latest queued before the latch)
waits, used = [], set()
for L in latch:
    i = bisect_right(qb, L) - 1
    if i >= 0 and i not in used:
        used.add(i); waits.append(L - qb[i])
summ("frame ready (queueBuffer) -> latch", waits)
if waits:
    print(f"frames that missed a latch (wait > half a period): {100 * sum(w > P / 2 for w in waits) / len(waits):.1f} %")
print(f"decoded frames queued={len(qb)} latched={len(used)} (never shown={len(qb)-len(used)})")
# latch -> next pass start (compose) and -> next vsync
nxt = lambda arr, t: arr[bisect_right(arr, t)] if bisect_right(arr, t) < len(arr) else None
summ("latch -> next TW pass start", [nxt(passes, L) - L for L in latch if nxt(passes, L)])
summ("latch -> next vsync", [P - p for p in ph(latch)])
