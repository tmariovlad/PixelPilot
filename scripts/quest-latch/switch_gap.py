"""How long the picture is gone after a live air-unit mode switch (e.g. waybeam 1080p90 <-> 480p167), from ONE
Perfetto trace of the running XR app (capture with ../quest/ab_long.sh; the app is not restarted).

For every gap between decoded frames longer than --min-gap-ms (a switch), it reports:
  frozen_ms   last decoded frame before the gap -> first decoded frame after it (what the pilot sees: frozen/black)
  stream_ms   last decoded frame -> first RTP packet of the new stream (the air unit's part: waybeam restart)
  decoder_ms  first RTP packet of the new stream -> first decoded frame (the app's part: what the decoder
              rebuild on an SPS change, audit X23 (c), can make longer by waiting for a key frame)
  decode_ms   median frame complete -> decoded frame ready over the next --after-s seconds (a "stuck" decoder that
              holds ~16 frames shows tens of ms here; healthy is ~2-3 ms)
Compare an old and a new build over the same switches (N >= 2 each).

Usage: python3 switch_gap.py trace.pftrace [--min-gap-ms 500] [--after-s 5]
Needs the app's 'ppxr_rtp_seq' / 'ppxr_rtp_ts' counters and 'ppxr_frame_ready' slices (transport_long.pbtx).
"""
import argparse
import statistics as st
from bisect import bisect_left, bisect_right

from ab_segments import frames_from_packets, load_trace


def find_switch_gaps(ready, arrivals, min_gap_ns):
    """ready: sorted decoded-frame times; arrivals: sorted RTP packet arrival times (ns).
    Returns [(last_frame, first_rtp_after, first_frame_after)] for every gap between frames > min_gap_ns."""
    gaps = []
    for a, b in zip(ready, ready[1:]):
        if b - a <= min_gap_ns:
            continue
        # first packet of the new stream: the first arrival after the old stream went quiet. Packets of the old
        # stream still in flight right after the last frame are skipped by taking the last arrival gap > 100 ms.
        lo, hi = bisect_right(arrivals, a), bisect_left(arrivals, b)
        first_new = None
        prev = a
        for t in arrivals[lo:hi]:
            if t - prev > 100e6:
                first_new = t
            prev = t
        if first_new is None and lo < hi:
            first_new = arrivals[lo]
        gaps.append((a, first_new, b))
    return gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--min-gap-ms", type=float, default=500)
    ap.add_argument("--after-s", type=float, default=5)
    a = ap.parse_args()
    pkts, ready, _ = load_trace(a.trace)
    arrivals = [p[0] for p in pkts]
    frames, _ = frames_from_packets(pkts, ready)
    decode = sorted((f.last, f.ready - f.last) for f in frames if f.ready is not None)
    gaps = find_switch_gaps(ready, arrivals, a.min_gap_ms * 1e6)
    if not gaps:
        print("no gap longer than", a.min_gap_ms, "ms between decoded frames")
        return
    t0 = ready[0]
    print(f"{'at_s':>7} {'frozen_ms':>10} {'stream_ms':>10} {'decoder_ms':>11} {'decode_ms_after':>16}")
    for last, first_rtp, first_frame in gaps:
        lo = bisect_left(decode, (first_frame, 0))
        hi = bisect_left(decode, (first_frame + a.after_s * 1e9, 0))
        after = [d for _, d in decode[lo:hi]]
        dec = f"{st.median(after) / 1e6:.2f} (n={len(after)})" if after else "n/a"
        stream = f"{(first_rtp - last) / 1e6:.0f}" if first_rtp else "n/a"
        decoder = f"{(first_frame - first_rtp) / 1e6:.0f}" if first_rtp else "n/a"
        print(f"{(last - t0) / 1e9:7.1f} {(first_frame - last) / 1e6:10.0f} {stream:>10} {decoder:>11} {dec:>16}")


if __name__ == "__main__":
    main()
