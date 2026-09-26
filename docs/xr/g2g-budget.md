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
- **Levers (air side, OpenIPC project):** fewer bytes per frame (bitrate 8000 → 4000 halves the packets), a higher MCS in the same room, and FEC k/n (block length and parity ratio). How to A/B them without the photodiode: change them live on the air unit (bitrate through waybeam's API, FEC through `wfb_setfec`; no RTP restart, so the capture-clock constant stays fixed) inside **one** long trace and compare capture → arrival directly. Tools: [ab_long.sh](../../scripts/quest/ab_long.sh) (capture) and [ab_segments.py](../../scripts/quest-latch/ab_segments.py) (analysis; offline check [test_ab_segments.py](../../scripts/quest-latch/test_ab_segments.py)); procedure in [scripts/quest/README.md](../../scripts/quest/README.md). Live-applicability is from the waybeam code (f8742fe, read by the OpenIPC session, not tested live): `video0.bitrate` is live, FEC k/n is live through `wfb_setfec`.
- **Closed: sub-frame (slice) sending.** `sliceSend: true` raised encode capture → NAL from 4 ms to 27–30 ms and dropped 119 fps to 45–60, whatever the slice size (sliceRows 40/23/1); `sliceRows` alone with `sliceSend: false` is inert (5–6 ms @ 119 fps) [PROVEN: OpenIPC `repos/tasks/hil-build/40-latency-measured-softonly.md:289-315`, HB-50, live on `.132`, 2026-06-27]. It could not be A/B'd from the Quest anyway: each waybeam start draws a new random RTP timestamp base, SSRC and sequence (`rtp_session.c:15,26-28`). Only a waybeam build that changes the per-slice output would reopen it. `lowDelay` on Star6E stops VENC (0 fps), so it is not a lever either.

**Other levers still open:** the phase lock (branch D, −2…3 ms, air side not built); the photodiode measurement for branch E and the total. Bitrate and FEC ratio are now measured: see [the in-trace A/B below](#air-unit-levers-measured-in-one-trace-2026-09-27-slot-2).

**How far this can go on Quest 2 (2026-09-27):** C (~1.5 ms) and E (~11.9 ms, panel backlight strobe) are fixed, ~13.4 ms together. With every lever above (B2 → ~1 ms, D → ~1 ms with the phase lock; A stays ~9.3 ms now that slice sending is closed) the total lands around **25–27 ms** [INFERRED: sum of the rows above with the lever estimates]. **20 ms is not reachable on Quest 2**: the sensor readout alone at ~167 fps takes several ms on top of the fixed 13.4 ms.

> **Baseline change, 2026-09-27 (later):** the air unit was switched persistently to **1080p90** (sensor mode 2, bitrate 8000; backup `/etc/waybeam.json.bak-640x480-20260927` on the air unit). Every number on this page is for **640×480 @ 167 fps**. At 1080p90 and 8 Mbit/s, expect ~8 packets per frame (~5.5 ms transport spread at MCS2), a compositor wait of ~4.2 ms instead of ~3.0 (a 90 fps source is slower than the 120 Hz display), and +0.8–1 ms of decode (see [decoder-levers.md](decoder-levers.md#codec-component-and-resolution-2026-09-26)), i.e. several ms more G2G [INFERRED: same arithmetic as above]. Tag any new measurement with the air mode.

## Air-unit levers measured in one trace (2026-09-27, slot 2)

**Setup.** Air unit at **640×480 @ 166.6 fps**, H.264 CBR, wfb-ng MCS2 / 20 MHz, STBC + LDPC, FEC 4/6 unless stated; air unit and headset in the same room, fixed. The lever was switched by a timed loop on the air unit (12 s per step, A B A C A B A C A, so N = 2 per non-baseline state), and one 140 s Perfetto trace covered the whole loop. [ab_segments.py](../../scripts/quest-latch/ab_segments.py) fits the air/headset clock drift on the baseline steps only (+73 / +75 ppm), drops 2 s around every switch, and reads each step against that line. So the Δ columns are absolute changes in capture → frame complete ("last") and capture → decoder output ("decoded") [PROVEN: method checked offline by [test_ab_segments.py](../../scripts/quest-latch/test_ab_segments.py)]. Step alignment: bitrate from the packets/frame steps (`--fit-offset`, +0.98 s), FEC from the app's own `wfb-ng SESSION` log lines (+0.98…0.99 s); both agree.

**Bitrate** (`video0.bitrate`, live through waybeam's API) [PROVEN: [data](data/measurements-2026-09-27-quest2-bitrate-ab.csv), [air step log](data/steps-2026-09-27-bitrate.txt)]:

| kbit/s | packets/frame | frame spread on air | Δ capture → decoded, mean | Δ per repeat | frame complete p95 |
|---|---|---|---|---|---|
| 8000 (baseline) | 5.11 | 4.21 ms | 0 | | 5.70 |
| 4000 | 3.13 | 1.83 ms | **−2.74 ms** | −2.3 / −3.0 | 0.46 (−5.2) |
| 2000 | 2.02 | 0.54 ms | **−4.46 ms** | −4.1 / −4.8 | −1.03 (−6.7) |

- The first packet of a frame moves by only −0.3…−0.7 ms; the rest of the gain is the frame's spread on the radio shrinking with its size. This confirms that B2 is airtime (see above) [INFERRED: "first" vs "last" columns in the data].
- Frame rate stayed 166.6 fps at every step; 67 of 98 855 packets were lost in the whole run.
- Cost: picture quality at 2–4 Mbit/s was not assessed.

**FEC** (`wfb_setfec` over wfb_tx's control port, no restart) [PROVEN: [data](data/measurements-2026-09-27-quest2-fec-ab.csv), [air step log](data/steps-2026-09-27-fec.txt)]:

| k/n | Δ capture → decoded, mean | Δ per repeat |
|---|---|---|
| 4/6 (baseline) | 0 | |
| 4/5 | **−1.53 ms** | −1.2 / −1.7 |
| 8/12 | −0.35 ms | −0.7 / −0.0 |

- 4/5 sends a third less parity, so the radio is free sooner for the next frame. It can repair 1 lost packet per 5 instead of 2 per 6; loss per state was not measured (112 of 116 107 packets lost in the whole run, same room).
- 8/12 vs 4/6 is inside the step-to-step spread of the baseline itself (0.2–1.6 ms), so block length is not a lever here [PROVEN: data].

**Updated budget at 640×480 @ 167 fps:** 30.7 ms − 4.5 ms (2000 kbit/s) ≈ 26 ms; with the phase lock (−2.4 ms measured on the Wi-Fi rig, [compositor-phase.md](compositor-phase.md)) ≈ 24 ms [INFERRED: the inferred total above minus measured deltas; the bitrate and FEC gains are not additive, both shrink the same airtime].

**Seen during the slot, not explained:** once, after the air unit restarted from 1080p90 to 640×480 while the app ran, the decoder took 78 ms per frame, the app lost ~65 RTP packets/s and arrivals lagged up to 0.9 s, until the app was restarted [PROVEN: logcat `Decoding:78.7`, trace `ab_check640`]. Five further switches in both directions, on the old build and on a build that rebuilds the decoder on every SPS change, all decoded normally (1.4–2.0 ms), so that cause is **not proven** and the build was not kept; the patch is in [patches/decoder-reconfigure-on-sps-change.patch](patches/decoder-reconfigure-on-sps-change.patch). See [troubleshooting.md](troubleshooting.md#more-traps-hit-on-2026-09-2627).

## MCS × bitrate at 1080p90, measured in one trace (2026-09-27, slot 3)

**Question:** can the 1080p90 stream carry more bitrate for picture quality, and what does that cost in latency?

**Setup.** Air unit at **1920×1080 @ 90 fps** (sensor mode 2, 2×2 binning, full field of view), H.264 CBR, wfb-ng 20 MHz, long GI, STBC + LDPC, FEC 4/6, in the same room as the headset. Same method as slot 2 above: one 240 s Perfetto trace ([ab_long.sh](../../scripts/quest/ab_long.sh)), a timed loop on the air unit with 12 s steps. The loop ran `m2b8 m3b12 m2b8 m4b16 m2b8 m4b12 m2b8 m3b12 m2b8 m4b16 m2b8`, where mN = MCS N and bK = K Mbit/s; N = 2 for m3b12 and m4b16, N = 1 for m4b12.
- The MCS was changed live with `wfb_tx_cmd 9000 set_radio` (all radio fields resent). `get_radio` before and after was identical, and `wfb_tx` kept the same PID. The bitrate was changed live through waybeam's API.
- On the way up the loop set MCS first, then bitrate; on the way down, bitrate first. Each step label was written after the second command. This ran on the OpenIPC side (session openipc-…-3a).
- Drift fitted on m2b8: +70 ppm. The step offset was fitted from packets/frame (+0.57 s against the +1.01 s measured with the clocks, which were only accurate to ±36 ms, adb RTT 72 ms).

[PROVEN: [data](data/measurements-2026-09-27-quest2-mcs-ab.csv), [air step log](data/steps-2026-09-27-mcs.txt), [loss per step](data/loss-2026-09-27-mcs.txt) from [ab_loss.py](../../scripts/quest-latch/ab_loss.py)]

| state | packets/frame | frame spread | Δ capture → frame complete | Δ capture → decoded | per repeat | lost after FEC | frames not decoded |
|---|---|---|---|---|---|---|---|
| MCS2, 8 Mbit/s (baseline) | 8.58 | 7.83 ms | 0 | 0 | | 0.10 % | 5 / 4582 |
| MCS3, 12 Mbit/s | 12.66 | 9.49 ms | +2.41 | **+2.64 ms** | +2.53 / +2.74 | 0.24 % | 1 / 1542 |
| MCS4, 16 Mbit/s | 16.83 | 9.29 ms | +1.55 | **+1.76 ms** | +1.75 / +1.75 | 0.16 % | 0 / 1545 |
| MCS4, 12 Mbit/s | 12.72 | 6.91 ms | −1.40 | **−1.23 ms** | (N = 1) | 0.16 % | 0 / 771 |

- **The latency follows airtime per frame, not bitrate alone** [INFERRED: the spread column tracks the Δ columns].
  - MCS4 at 12 Mbit/s carries 1.5× the baseline bitrate and is still 1.2 ms faster, because each frame spends less time on the radio.
  - MCS3 at 12 Mbit/s is the worst point: 50 % more bytes at only 33 % more PHY rate.
  - This agrees with slot 2, where a lower bitrate at a fixed MCS saved time for the same reason.
- **Loss:** every state lost ≤ 0.24 % of packets after FEC, and the higher rates left no frame undecoded. So on the bench MCS4 carries 16 Mbit/s cleanly [PROVEN: loss file].
- **Range was not tested.** MCS4 needs more SNR than MCS2, so its range is shorter [INFERRED: 802.11n MCS SNR requirements, not measured here]. Check it at flying distance before using MCS4 in the air.
- **Picture quality:** the visual comparison in the headset is recorded below once done.
- **Frame rate** stayed 90.5 fps at every step.
