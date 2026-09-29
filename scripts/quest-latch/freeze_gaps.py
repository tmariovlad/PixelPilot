"""What the "VIDEO STALLED" headline is made of. The app shows it when no decoded frame came for
max(250 ms, 6 frame periods) (SignalState.java MIN_STALL_NS / STALL_FRAMES). With freeze_until_idr on, a freeze that
waits for the IDR produces no decoded frames either. So each gap between decoded frames (ppxr_frame_ready) at or
above the threshold is classified:
  no packets          fewer than 5 RTP packets arrived in the gap (after a 20 ms decode margin): a real link gap;
  freeze              packets arrived and the ppxr_frozen_slices counter rose: FRZ held the picture for the IDR;
  packets, no frames  packets arrived, nothing frozen: the decoder or the parser.
Per gap: its length, RTP packets lost inside it (sequence gaps), frozen slices, IDR requests ok / failed.

Usage: python3 freeze_gaps.py trace.pftrace [--threshold-ms 250]
"""
import argparse
from bisect import bisect_left

MIN_PACKETS = 5
# The last decoded frame comes a few ms after its own packets (decode latency), so packets are counted only from this
# far into the gap on; otherwise a real link gap always looks as if packets kept arriving.
DECODE_MARGIN_NS = 20_000_000


def _in(series, a, b):
    """Values of a cumulative counter [(ns, value)] rising within [a, b): the last value in it minus the one before."""
    before = [v for t, v in series if t < a]
    inside = [v for t, v in series if a <= t < b]
    if not inside:
        return 0
    return inside[-1] - (before[-1] if before else 0)


def classify(ready, pkts, frozen, idr_ok, idr_fail, threshold_ns):
    """ready: sorted ns of decoded frames; pkts: [(ns, seq16)] in arrival order; frozen / idr_ok / idr_fail:
    cumulative counters [(ns, value)]. Returns one dict per gap >= threshold_ns."""
    times = [t for t, _ in pkts]
    out = []
    for a, b in zip(ready, ready[1:]):
        if b - a < threshold_ns:
            continue
        i, j = bisect_left(times, a), bisect_left(times, b)
        inside = pkts[bisect_left(times, a + DECODE_MARGIN_NS):j]
        lost = 0
        for (_, s0), (_, s1) in zip(pkts[max(i - 1, 0):j], pkts[max(i - 1, 0) + 1:j + 1] if j < len(pkts) else pkts[max(i - 1, 0) + 1:j]):
            d = (s1 - s0) & 0xFFFF
            if 1 < d < 0x8000:
                lost += d - 1
        fz = _in(frozen, a, b)
        kind = "no packets" if len(inside) < MIN_PACKETS else "freeze" if fz > 0 else "packets, no frames"
        out.append({"start_ns": a, "ms": (b - a) / 1e6, "kind": kind, "packets": len(inside), "lost": lost,
                    "frozen": fz, "idr_ok": _in(idr_ok, a, b), "idr_failed": _in(idr_fail, a, b)})
    return out


def summary(gaps, seconds):
    kinds = {}
    for g in gaps:
        kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
    ms = sorted(g["ms"] for g in gaps)
    return {"stalls": len(gaps), "per_min": len(gaps) / seconds * 60 if seconds > 0 else 0.0, "kinds": kinds,
            "ms_p50": ms[len(ms) // 2] if ms else 0.0, "ms_max": ms[-1] if ms else 0.0}


def load(path):
    from perfetto.trace_processor import TraceProcessor
    tp = TraceProcessor(trace=path)
    q = lambda s: list(tp.query(s))
    cnt = lambda name: [(r.ts, int(r.value)) for r in q(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        f"where t.name='{name}' order by c.ts")]
    ready = [r.ts for r in q("select ts from slice where name='ppxr_frame_ready' order by ts")]
    return ready, cnt("ppxr_rtp_seq"), cnt("ppxr_frozen_slices"), cnt("ppxr_idr_req_ok"), cnt("ppxr_idr_req_failed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("--threshold-ms", type=float, default=250)
    a = ap.parse_args()
    ready, seqs, frozen, ok, failed = load(a.trace)
    if len(ready) < 2:
        raise SystemExit("no decoded frames in the trace")
    seconds = (ready[-1] - ready[0]) / 1e9
    gaps = classify(ready, seqs, frozen, ok, failed, a.threshold_ms * 1e6)
    total_lost = sum((d - 1) for d in (((s1 - s0) & 0xFFFF) for (_, s0), (_, s1) in zip(seqs, seqs[1:])) if 1 < d < 0x8000)
    print(f"{seconds:.1f} s, {len(ready)} decoded frames ({len(ready) / seconds:.1f}/s), RTP lost {total_lost} "
          f"({total_lost / seconds:.1f}/s), frozen slices {frozen[-1][1] - frozen[0][1] if len(frozen) > 1 else 0}, "
          f"IDR requests ok {ok[-1][1] - ok[0][1] if len(ok) > 1 else 0} failed {failed[-1][1] - failed[0][1] if len(failed) > 1 else 0}")
    s = summary(gaps, seconds)
    print(f"stalls >= {a.threshold_ms:.0f} ms: {s['stalls']} ({s['per_min']:.1f}/min), p50 {s['ms_p50']:.0f} ms, "
          f"max {s['ms_max']:.0f} ms, by kind {s['kinds']}")
    t0 = ready[0]
    for g in gaps:
        print(f"  t+{(g['start_ns'] - t0) / 1e9:6.2f} s {g['ms']:6.0f} ms  {g['kind']:18s} pkts {g['packets']:5d} "
              f"lost {g['lost']:4d} frozen {g['frozen']:4d} idr ok {g['idr_ok']} failed {g['idr_failed']}")


if __name__ == "__main__":
    main()
