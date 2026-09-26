"""Decoder -> compositor buffer-queue stats from a Perfetto trace of the XR app: queueBuffer rate vs
compositor latches, CodecLooper dequeueBuffer blocking, BufferQueue depth, media.decode_latency_us.
Usage: python3 bq_stats.py trace.pftrace      Needs: pip install perfetto"""
import sys, statistics as st
from perfetto.trace_processor import TraceProcessor
tp = TraceProcessor(trace=sys.argv[1]); q = lambda s: list(tp.query(s))
def pct(v, p): v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))]
dq = [r.dur / 1e6 for r in q("""select s.dur from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name like 'dequeueBuffer - SurfaceTexture%'""")]
qb = q("""select count(*) n, (max(s.ts)-min(s.ts))/1e9 span from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name='queueBuffer'""")[0]
vid = q("""select distinct substr(s.name, 17) v from slice s join thread_track tt on s.track_id=tt.id join thread t using(utid)
  where t.name='CodecLooper' and s.name like 'dequeueBuffer - SurfaceTexture%'""")[0].v
lat = q(f"""select count(*) n from slice s join slice p on s.parent_id=p.id join thread_track tt on p.track_id=tt.id join thread t using(utid)
  where t.name='OVR::TimeWarp' and p.name='acquireBuffer' and s.name like '{vid}:%'""")[0].n
depth = [r.value for r in q(f"select c.value from counter c join counter_track t on c.track_id=t.id where t.name='{vid}'")]
dl = [r.value / 1000 for r in q("select c.value from counter c join counter_track t on c.track_id=t.id where t.name like 'media.decode_latency_us%'")]
print(f"decoder queueBuffer: {qb.n} in {qb.span:.1f}s = {qb.n/qb.span:.1f}/s ; compositor latched {lat} = {lat/qb.span:.1f}/s")
print(f"CodecLooper dequeueBuffer (blocking for a free buffer): n={len(dq)} mean={st.mean(dq):.2f} p50={pct(dq,.5):.2f} p95={pct(dq,.95):.2f} max={max(dq):.2f} ms")
if depth: print(f"BufferQueue queued-depth counter ({vid}): mean={st.mean(depth):.2f} max={max(depth):.0f}")
if dl: print(f"media.decode_latency (codec-internal): mean={st.mean(dl):.1f} p50={pct(dl,.5):.1f} max={max(dl):.1f} ms")
