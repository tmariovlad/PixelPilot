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
- ~~~150-byte packets at MCS2 need only tens of µs of airtime, so ~0.68 ms per packet is pacing somewhere.~~ **Corrected 2026-09-27:** the packets are **~1357 B**, not ~150 B. The 150 B figure came from the configured bitrate; the air unit's `wfb_tx` `PKT` counters show ~844–928 pkt/s at ~1250–1357 B, i.e. 9.2 Mbit/s [PROVEN: [real-link.md § TX power](real-link.md#tx-power-and-radio-settings-through-walls-2026-09-27); `/tmp/wfbtx.log` `PKT 0:928:1152537:1393:…` read on 2026-09-27]. `/etc/waybeam.json` asks for `video0.bitrate: 8000`, so the rate is what the config requests.
- **The ~0.68 ms spacing is airtime at MCS2.** A ~1400 B MPDU at MCS2 / 20 MHz (19.5 Mbit/s) takes ~575 µs, plus ~36 µs HT preamble and ~100 µs DIFS + mean backoff ≈ 0.7 ms per packet. ~5 packets per frame then take ~3.4 ms to arrive, as measured [INFERRED: arithmetic from the measured packet size and rate]. No hidden pacing is needed to explain it.
- **FEC parity lands inside the next frame.** `wfb_tx` sends a block's parity packets right after its k-th data packet (`wfb-ng/src/tx.cpp:617-640`). With ~5–5.6 data packets per frame and k = 8 (then 4), blocks straddle frames, so 2–4 parity packets (~1.4–2.8 ms of airtime) interrupt the following frame [INFERRED: code + packet counts]. A likely source of the clumps and of the 7 ms p95 [SPECULATION: not yet traced per packet].
- The receiver adds no wait: it forwards data packets in order as soon as they arrive (`wfb-ng/src/rx.cpp:754`) [PROVEN: code].
- The HIL frame-based encoder emits a whole frame at t2 [INFERRED: FRAMEBASE bind], so the spread is transport, not capture.
- **Levers (air side, OpenIPC project):** fewer bytes per frame (bitrate 8000 → 4000 halves the packets), a higher MCS in the same room, FEC k aligned to the packets per frame, and waybeam's `sliceSend` / `lowDelay`, which let a frame's first slices leave before encoding ends. How to A/B them without the photodiode: change them live through waybeam's API (no RTP restart, so the capture-clock constant in [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py) stays fixed) and compare capture → arrival directly. Tools: [ab_long.sh](../../scripts/quest/ab_long.sh) (capture) and [ab_segments.py](../../scripts/quest-latch/ab_segments.py) (analysis; offline check [test_ab_segments.py](../../scripts/quest-latch/test_ab_segments.py)); procedure in [scripts/quest/README.md](../../scripts/quest/README.md). From the waybeam code (f8742fe, read by the OpenIPC session, not tested live): `video0.bitrate` applies live, FEC k/n changes live through `wfb_setfec`; `sliceRows`/`sliceSend` need a waybeam restart, and `lowDelay` on Star6E stops VENC (0 fps), so it is not a lever.

**Other levers still open:** the phase lock (branch D, −2…3 ms, air side not built); the photodiode measurement for branch E and the total.

**How far this can go on Quest 2 (2026-09-27):** C (~1.5 ms) and E (~11.9 ms, panel backlight strobe) are fixed, ~13.4 ms together. With every lever above (B2 → ~1 ms, D → ~1 ms with the phase lock, A trimmed by sliced low-delay encoding) the total lands around **23–27 ms** [INFERRED: sum of the rows above with the lever estimates]. **20 ms is not reachable on Quest 2**: the sensor readout alone at ~167 fps takes several ms on top of the fixed 13.4 ms.

> **Baseline change, 2026-09-27 (later):** the air unit was switched persistently to **1080p90** (sensor mode 2, bitrate 8000; backup `/etc/waybeam.json.bak-640x480-20260927` on the air unit). Every number on this page is for **640×480 @ 167 fps**. At 1080p90 and 8 Mbit/s, expect ~8 packets per frame (~5.5 ms transport spread at MCS2), a compositor wait of ~4.2 ms instead of ~3.0 (a 90 fps source is slower than the 120 Hz display), and +0.8–1 ms of decode (see [decoder-levers.md](decoder-levers.md#codec-component-and-resolution-2026-09-26)), i.e. several ms more G2G [INFERRED: same arithmetic as above]. Tag any new measurement with the air mode.
