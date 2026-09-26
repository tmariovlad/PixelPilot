# G2G budget on the real link

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

Glass-to-glass budget per branch on the [real link](real-link.md). Branch D is the compositor wait ([compositor-phase.md](compositor-phase.md)); branch C uses the decoder settings from [decoder-levers.md](decoder-levers.md) and [real-link.md](real-link.md).

## G2G budget on the real link, branch by branch (2026-09-26)

**Method:**
- Quest side: one 9 s Perfetto trace at 166 fps with the app's per-packet marks (`ppxr_rtp_seq` / `ppxr_rtp_ts` in `VideoPlayer::onNewRTPData`, recorded only while tracing).
- Analysis: [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py) and [latch_analyze.py](../../scripts/quest-latch/latch_analyze.py).
- The air unit's RTP timestamp is its capture clock. arrival − capture gives the transport delay up to a constant. The air/headset clock drift, **+96 ppm**, is removed.
- Stream: 7225 packets, 1421 frames, **166.6 fps, 5.1 packets/frame, 0 packets lost** [PROVEN].

| Branch | mean | p50 | p95 | Tag |
|---|---|---|---|---|
| A. Air: LED → encoded frame leaves waybeam (t0→t2) | ~9.3 | | | [INFERRED: HIL t2 = 9.32 ms at 167 fps, OpenIPC `docs/KNOWLEDGE.md:21`; same config, air binary now `13b85893`] |
| B1. Transport floor (air egress → Quest) | ~1.9 | | | [INFERRED: HIL t2→t3 = 1.9 ms on APFPV; not measured on wfb] |
| B2. Transport excess over the best frame (frame complete) | 2.91 | 2.92 | 7.01 | [PROVEN] |
| C. Frame complete → decoded (parse + queue + decode, picture-order on) | 1.55 | 1.45 | 2.12 | [PROVEN] |
| D. Decoded → compositor latch | 3.10 | 2.67 | 6.82 | [PROVEN] |
| E. Latch → light (mid-flash, two halves) | 11.9 | | 10.2 / 13.5 | [INFERRED: measured latch lead + Quest 2 kernel flash offsets] |
| **Total G2G** | **≈ 30.7** | | **≈ 23–40 range** | [INFERRED: sum; the photodiode rig will check it] |

**Where B2 comes from (open):**
- A frame's ~5 packets arrive **evenly spaced ~0.65–0.7 ms apart**. Of the in-frame gaps, 3924 are 0.5–1 ms and 659 are < 50 µs. So a frame takes ~3.4 ms to arrive completely (spread mean 4.28, p50 3.72, p95 8.65 ms).
- Sometimes packets are held back and released in a clump (e.g. `[0, 5481, 5498, 5503, 5508] µs`).
- ~150-byte packets at MCS2 need only tens of µs of airtime, so ~0.68 ms per packet is pacing somewhere. Candidates:
  - air-side injection (wfb_tx / 8822EU driver);
  - Quest-side RX delivery (devourer USB);
  - contention with the Quest RTL's own uplink transmissions on the same channel (seen earlier: thousands of 177-byte frames).
- The HIL frame-based encoder emits a whole frame at t2 [INFERRED: FRAMEBASE bind], so the spread is most likely transport, not capture.
- Next: read `wfb_tx`'s per-second `PKT` counters on the air unit, and A/B the Quest's uplink off vs on.

**Other levers still open:** the phase lock (branch D, −2…3 ms, air side not built); the photodiode measurement for branch E and the total.
