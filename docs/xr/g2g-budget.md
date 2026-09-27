# G2G budget on the real link

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

Glass-to-glass budget per branch on the [real link](real-link.md). Branch D is the compositor wait ([compositor-phase.md](compositor-phase.md)); branch C uses the decoder settings from [decoder-levers.md](decoder-levers.md) and [real-link.md](real-link.md).

## Recommendations and numbers (summary, 2026-09-27)

**The number.** The recommended setup (**REC**: 640×480 @ 167 fps, 2000 kbit/s, FEC 4/8, MCS2) gives **27.4–32.7 ms** glass-to-glass. The original setup (1080p90, 8000 kbit/s, FEC 4/6) gives 46.6–51.9 ms, so REC is **19.2 ms faster (−37 %)**. It is also more robust: loss 0.1 % instead of 2.1 %, no undecoded frames instead of 1.2 %, and 2 radio packets per frame instead of 8.4. Measured per segment, N = 2, palindromic ([before / after](#before--after-the-original-setup-vs-the-recommended-one-2026-09-27-final)). The range comes from two inferred terms: the ISP and the panel.

**Field of view (W3c):** 480p167 shows only 33 % × 44 % of the sensor. A wider view costs **+4.9 ms** at 720p120 scaled to 848×480 (66 × 66 %, ~1.5× softer), **+6.3 ms** at 720p120 native (66 × 66 %, the same sharpness), or **+9.1 ms** at 1080p90 scaled to 848×480 (99 × 98 %, ~2.2× softer). With the O112 pin, 480p167 now starts at 26.7 ms ([W3c](#field-of-view-against-latency-480p167-vs-720p120-vs-1080p90-scaled-w3c-2026-09-27)).

**The 20–25 ms target is not reached on Quest 2.** About 12 ms of REC's 27.4 ms floor is fixed: the panel (latch → light, 10.2 ms minimum) and the air → Quest floor (1.9 ms).

**What worked:**
- **Mode 480p167** over 720p120 / 1080p90: −7 / −16 ms at the same bitrate ([W3](#mode-choice-for-minimum-latency-1080p90-vs-720p120-vs-480p167-w3-2026-09-27)).
- **Bitrate 2000 kbit/s and FEC 4/8:** another ~−3 ms at 480p167, almost all from a shorter frame spread on the radio ([slot 2](#air-unit-levers-measured-in-one-trace-2026-09-27-slot-2), [before / after](#before--after-the-original-setup-vs-the-recommended-one-2026-09-27-final)).
- **Decoder keys** (picture-order, low-latency, operating-rate): without picture-order, the Qualcomm decoder holds ~16 frames (~95 ms) on this stream ([real-link.md](real-link.md), [decoder-levers.md](decoder-levers.md)).
- **App fixes with no latency cost:**
  - the tunnel pump no longer busy-loops (whole app 124 % → 27 % CPU, [troubleshooting](troubleshooting.md#more-traps-hit-on-2026-09-2627));
  - the uplink takes 76 % less airtime (4 reports/s × FEC 1/3), and keyframe requests now go out within 20 ms, not 100 ms ([link-envelope.md](link-envelope.md));
  - robustness fixes for the display turning off, stale statistics and link restarts ([troubleshooting](troubleshooting.md)).

**What did not work (closed):**
- **Phase lock, AU-04.** At 480p167 the source is faster than the 119.70 Hz display, so there is nothing to lock. Even an ideal lock at 119.7 fps was +1.2 ms slower at 8 Mbit/s ([compositor-phase.md](compositor-phase.md#phase-lock-steering-the-source-onto-the-compositor-latch-proof-of-concept-2026-09-26), W3b).
- **Slice sending.** Encode went from 4 to 27–30 ms and the rate fell to 45–60 fps ([above](#g2g-budget-on-the-real-link-branch-by-branch-2026-09-26), HB-50).
- **Decoder rebuild on SPS change (X23 c).** On live mode switches, the decoder part of the gap was slower with the rebuild (84 vs 50 ms mean), and the 78 ms stall it targeted did not occur on either build. It was removed in `501094a` ([final slot](research/2026-09-27-xr-ux-audit.md#final-slot-on-the-headset-2026-09-27)).
- **Tunnel downlink FEC 1/3 vs 1/2.** Same latency, and 0 vs 4 lost packets, which is not significant (p = 0.07). The tunnel stays on 1/2, with 1/3 kept as an option ([troubleshooting](troubleshooting.md#more-traps-hit-on-2026-09-2627), W1 tunnel entry).

**Still open, with estimates:**
- **O112, bimodal encode on the air unit.** About a quarter of frames at 1080p, and about half at 480p, take ~2 ms longer, in bursts. With every frame in the fast mode, REC would start at **~26.8 ms** (−0.6 ms on average, up to −2 ms on the slow frames) [INFERRED]. A likely cause is encoder and ISP threads sharing a CPU [SPECULATION]. Pinning the threads needs the user's OK ([plan](plan-2026-09-27-optimize.md)).
- **Panel and total, photodiode.** The panel term (10.2–13.5 ms) and the total are still [INFERRED] from kernel flash offsets and the per-segment sum. A photodiode at the lens (BPW34 / OPT101 + scope) or 480 fps slow motion would turn the budget into one measured number. That changes no latency, but it would confirm or correct the ±2.7 ms range ([compositor-phase.md](compositor-phase.md)). There is no ESP32 rig yet.
- **Picture quality at 480p / 2000 kbit/s** has not been assessed. The user should check it before making REC the default.
- **Latch wait (~3.1 ms)** has no known lever at 480p167: the compositor takes the newest frame, and a lock does not apply.

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

**Updated budget at 640×480 @ 167 fps:** 30.7 ms − 4.5 ms (2000 kbit/s) ≈ 26 ms; with the phase lock (−2.4 ms measured on the Wi-Fi rig, [compositor-phase.md](compositor-phase.md)) ≈ 24 ms [INFERRED: the inferred total above minus measured deltas; the bitrate and FEC gains are not additive, both shrink the same airtime]. *(Correction 2026-09-27, later: the phase lock does not apply at 480p167, since the source is faster than the display (AU-04 closed, W3b), and the measured REC total is 27.4–32.7 ms; see [the summary](#recommendations-and-numbers-summary-2026-09-27).)*

**Seen during the slot, not explained:** once, after the air unit restarted from 1080p90 to 640×480 while the app ran, the decoder took 78 ms per frame, the app lost ~65 RTP packets/s and arrivals lagged up to 0.9 s, until the app was restarted [PROVEN: logcat `Decoding:78.7`, trace `ab_check640`]. Five further switches in both directions, on the old build and on a build that rebuilds the decoder on every SPS change, all decoded normally (1.4–2.0 ms), so that cause is **not proven** and the build was not kept; the patch is in [patches/decoder-reconfigure-on-sps-change.patch](patches/decoder-reconfigure-on-sps-change.patch). (Correction 2026-09-27, later: the patch was later put in the code (`c0f41f2`, X23 c). On 4 live switches per build it made the decoder part of the gap slower (84 vs 50 ms mean), and the stall did not occur on either build, so it was removed again in `501094a`; [final slot](research/2026-09-27-xr-ux-audit.md#final-slot-on-the-headset-2026-09-27).) See [troubleshooting.md](troubleshooting.md#more-traps-hit-on-2026-09-2627).

## MCS × bitrate at 1080p90, measured in one trace (2026-09-27, slot 3)

**Question:** can the 1080p90 stream carry more bitrate for picture quality, and what does that cost in latency?

**Setup.** Air unit at **1920×1080 @ 90 fps** (sensor mode 2, 2×2 binning, full field of view), H.264 CBR, wfb-ng 20 MHz, long GI, STBC + LDPC, FEC 4/6, in the same room as the headset. Same method as slot 2 above: one 240 s Perfetto trace ([ab_long.sh](../../scripts/quest/ab_long.sh)), a timed loop on the air unit with 12 s steps. The loop ran `m2b8 m3b12 m2b8 m4b16 m2b8 m4b12 m2b8 m3b12 m2b8 m4b16 m2b8`, where mN = MCS N and bK = K Mbit/s; N = 2 for m3b12 and m4b16, N = 1 for m4b12.
- The MCS was changed live with `wfb_tx_cmd 9000 set_radio` (all radio fields resent). `get_radio` before and after was identical, and `wfb_tx` kept the same PID. The bitrate was changed live through waybeam's API.
- On the way up the loop set MCS first, then bitrate; on the way down, bitrate first. Each step label was written after the second command. This ran on the OpenIPC side (session openipc-…-3a).
- Drift fitted on m2b8: +70 ppm. The step offset was fitted from packets/frame (+0.57 s against the +1.01 s measured with the clocks, which were only accurate to ±36 ms, adb RTT 72 ms).

[PROVEN: [data](data/measurements-2026-09-27-quest2-mcs-ab.csv) with loss and undecoded frames per step (columns `lost_pct`, `undecoded` from [ab_segments.py](../../scripts/quest-latch/ab_segments.py)), [air step log](data/steps-2026-09-27-mcs.txt)]

| state | packets/frame | frame spread | Δ capture → frame complete | Δ capture → decoded | per repeat | lost after FEC | frames without a decoded mark (`undecoded`) |
|---|---|---|---|---|---|---|---|
| MCS2, 8 Mbit/s (baseline) | 8.58 | 7.83 ms | 0 | 0 | | 0.10 % | 5 / 4582 |
| MCS3, 12 Mbit/s | 12.66 | 9.49 ms | +2.41 | **+2.64 ms** | +2.53 / +2.74 | 0.24 % | 1 / 1542 |
| MCS4, 16 Mbit/s | 16.83 | 9.29 ms | +1.55 | **+1.76 ms** | +1.75 / +1.75 | 0.16 % | 0 / 1545 |
| MCS4, 12 Mbit/s | 12.72 | 6.91 ms | −1.40 | **−1.23 ms** | (N = 1) | 0.16 % | 0 / 771 |

- **The latency follows airtime per frame, not bitrate alone** [INFERRED: the spread column tracks the Δ columns].
  - MCS4 at 12 Mbit/s carries 1.5× the baseline bitrate and is still 1.2 ms faster, because each frame spends less time on the radio.
  - MCS3 at 12 Mbit/s is the worst point: 50 % more bytes at only 33 % more PHY rate.
  - This agrees with slot 2, where a lower bitrate at a fixed MCS saved time for the same reason.
- **Loss:** every state lost ≤ 0.24 % of packets after FEC, and at the higher rates no frame lacked a decoded mark (`undecoded` = no `ppxr_frame_ready` within 20 ms of the frame's last packet; a late decode counts too, and a dropped frame can take the next frame's mark, so it is an approximate count). So on the bench MCS4 carries 16 Mbit/s cleanly [PROVEN: `lost_pct` / `undecoded` columns of the data].
- **Range was not tested.** MCS4 needs more SNR than MCS2, so its range is shorter [INFERRED: 802.11n MCS SNR requirements, not measured here]. Check it at flying distance before using MCS4 in the air.
- **Picture quality:** the visual comparison in the headset is recorded below once done.
- **Frame rate** stayed 90.5 fps at every step.

## Mode choice for minimum latency: 1080p90 vs 720p120 vs 480p167 (W3, 2026-09-27)

**Why a budget and not one number:** every mode switch restarts waybeam, which draws a new random RTP timestamp base, so capture → arrival on the Quest cannot be compared between modes. Each mode's glass-to-glass is therefore summed from segments that do not need it ([w3_budget.py](../../scripts/quest-latch/w3_budget.py), offline tests [test_w3_budget.py](../../scripts/quest-latch/test_w3_budget.py)):

| Segment | Source | Tag |
|---|---|---|
| Capture phase: an event waits on average half a frame period for the next exposure (from the measured fps; added 2026-09-27 later, see the correction below) | arithmetic | [INFERRED] |
| Sensor readout, counted in full (active lines × 1H, 1H = HMAX 365 / 74.25 MHz ≈ 4.9 µs) | IMX415 registers, driver 6e637e75 (OpenIPC `repos/tasks/hil-build/coord-pixelpilot-xr-2026-09-27/w3-readout-per-mode.md`) | [PROVEN] |
| ISP + VPE/SCL (whole frame, not line-pipelined; scales weakly with pixels) | OpenIPC SoC analysis (`…/w3-isp-per-mode.md`); no per-frame timestamp exists to measure it | [INFERRED], a range |
| VENC input → last packet sent (encode + send) | waybeam sidecar, per frame, air clock, 60 s per segment | [PROVEN] |
| First packet air → Quest | HIL t2→t3, 1.9 ms, same for every mode | [INFERRED] |
| Frame spread on the radio, frame complete → decoded, decoded → compositor latch | Perfetto trace on the Quest, 9 s per segment ([mode_segment.sh](../../scripts/quest/mode_segment.sh)) | [PROVEN] |
| Latch → light (backlight strobe) | 10.2–13.5 ms, same for every mode ([compositor-phase.md](compositor-phase.md)) | [INFERRED] |

**Setup:** Quest on the balcony (loss ~2.2–2.4 %), canonical build cd5fa436, prefs and decoder keys checked in every segment (picture-order and operating-rate on). Air unit: wfb MCS2, FEC 4/6, 12 dBm, **8000 kbit/s in every mode**, GOP 2 s; only mode/size/fps changed. Order [2] → [6] → [7] → [7] → [6] → [2] (N = 2 per mode, palindromic so a drift over time cancels); the app was restarted in every segment (a live resolution change once left the decoder holding frames, see [troubleshooting.md](troubleshooting.md)). Mode [9] 720p137 was left out: it needs a live sensor parameter and its expected gain over [6] is below the ISP uncertainty.

| Mode | capture phase | readout | ISP | encode+send (median, a / b) | spread | decode | latch wait | pkt/frame | loss | **total G2G** |
|---|---|---|---|---|---|---|---|---|---|---|
| **[7] 640×480 @ 166.5 fps** | 3.00 | 2.34 | 1.5–3.5 | 2.13 / 2.13 | 4.26 | 2.00 | 3.10 | 5.01 | 2.2 % | **30.4 – 35.7 ms** |
| [6] 1280×720 @ 119.2 fps | 4.19 | 3.52 | 2.0–4.0 | 3.66 / 3.69 | 5.78 | 2.44 | 3.78 | 6.39 | 2.4 % | 37.5 – 42.8 ms |
| [2] 1920×1080 @ 90.4 fps | 5.53 | 5.31 | 2.0–4.0 | 6.53 / 6.53 | 8.02 | 3.13 | 3.86 | 8.43 | 2.4 % | 46.5 – 51.8 ms |

[PROVEN per segment: [air TSV](data/w3-2026-09-27-air.tsv), Quest outputs `data/w3-2026-09-27-quest-<mode>_<rep>.txt`, [budget](data/w3-2026-09-27-budget.txt); the ranges carry only the [INFERRED] ISP and panel terms.]

- **Correction 2026-09-27 (later):** the first version of this table left out the capture phase (an event waits half a frame period for the next exposure: 3.0 / 4.2 / 5.5 ms). It mostly depends on fps, so it matters exactly when modes differ in fps; the totals were 27.4–32.7 / 33.3–38.6 / 40.9–46.2 ms. The verdict is unchanged and the margins grew.
- **Verdict: 480p167 is the lowest-latency mode, by ~7 ms over 720p120 and ~16 ms over 1080p90.** Its range lies wholly below the others even with the conservative rule (independent ISP ranges; the ISP error is largely common to all modes, so the real margins are, if anything, cleaner). It is also the most robust at a fixed bitrate: fewest packets per frame and the lowest loss.
- Every segment moves the same way as the frame shrinks: readout, encode (6.3 → 3.5 → 2.0 ms), the frame's spread on the radio, decode, and the latch wait (a 166 fps source overruns the 119.70 Hz display, so the compositor takes the newest frame and drops ~29 % of them; the wait falls to ~3.1 ms).
- Repeatability: encode+send a/b differ by ≤ 0.03 ms, the Quest segments by ≤ 0.3 ms.
- Cross-check against the branch estimate at the same mode (top of this page, ≈ 30.7 ms): the air side here (capture 3.0 + readout 2.34 + ISP 1.5–3.5 + encode/send 2.13 = 9.0–11.0 ms) matches branch A (HIL LED → encoded, 9.3 ms). The ~2 ms higher total comes from the Quest side: this budget counts the frame's whole spread on the radio (4.26 ms), the earlier one only its excess over the best frame (B2, 2.91 ms) [INFERRED: the two definitions].
- Not assessed: picture quality at 480p vs 720p/1080p at the same 8 Mbit/s. The bitrate lever from slot 2 (2000–4000 kbit/s: −2.7…−4.5 ms at 480p167) applies on top.
- Air unit left at 1080p90 (the prior default); changing the default mode is the coordinator's / user's decision.
- Phase lock: not applicable at 480p167 (source faster than the display), and W3b showed that 480p at 119.7 fps with even an ideal lock is ~1.2 ms slower than 480p167 without one, so the air-side lock (AU-04) is closed ([compositor-phase.md](compositor-phase.md#phase-lock-steering-the-source-onto-the-compositor-latch-proof-of-concept-2026-09-26)).

## Before / after: the original setup vs the recommended one (2026-09-27, final)

**Question:** how much glass-to-glass do the measured levers buy together? **BASE** = the setup the work started from: 1080p90, 8000 kbit/s, FEC 4/6. **REC** = the recommendation: 480p167 (W3), 2000 kbit/s (slot 2), FEC 4/8 (W2 envelope). Both at MCS2, 12 dBm, GOP 2 s. The method is the W3 per-segment budget above ([w3_budget.py](../../scripts/quest-latch/w3_budget.py)). Order: BASE → REC → REC' → BASE (palindromic, N = 2). waybeam was restarted in every segment, the XR app too ([mode_segment.sh](../../scripts/quest/mode_segment.sh)). Quest on the balcony, canonical build 7b8baadb, picture-order and operating-rate on in every segment. The air side was run by the OpenIPC session: switch, sidecar s_air, `isperr_new=0` in every segment. It ended on PRE (480p167 / 8000 / FEC 4/6).

| Setup | capture phase | readout | ISP | encode+send (median, a / b) | spread | decode | latch wait | pkt/frame | loss | undecoded | **total G2G** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **REC** 480p167 / 2000 / FEC 4/8 | 3.00 | 2.34 | 1.5–3.5 | 3.18 / 2.01 | 1.12 | 1.64 | 3.07 | 1.98 | 0.10 % | 0 % | **27.4 – 32.7 ms** |
| BASE 1080p90 / 8000 / FEC 4/6 | 5.53 | 5.31 | 2.0–4.0 | 6.52 / 6.49 | 7.97 | 3.05 | 4.08 | 8.38 | 2.06 % | 1.2 % | 46.6 – 51.9 ms |

[PROVEN per segment: [air TSV](data/ba-2026-09-27-air.tsv), Quest outputs `data/ba-2026-09-27-quest-<setup>_<rep>.txt`, [budget](data/ba-2026-09-27-budget.txt). The ranges carry only the [INFERRED] ISP and panel terms (10.2–13.5 ms), plus the 1.9 ms air → Quest floor.]

- **Result: REC is 19.2 ms faster than BASE (−37 %), 27.4–32.7 ms against 46.6–51.9 ms.** The ranges do not overlap. By segment: frame spread on the radio −6.9, encode+send −3.9, readout −3.0, capture phase −2.5, decode −1.4, latch wait −1.0, ISP −0.5 ms [INFERRED: difference of the rows]. REC is also the more robust setup: 2 packets per frame instead of 8.4, loss 0.1 % instead of 2.1 %, and no frame left undecoded. BASE left 1.2 % undecoded.
- **Against W3's 480p167 at 8000 kbit/s (30.4–35.7 ms), the lower bitrate and FEC 4/8 buy another ~3 ms.** Almost all of it is spread (4.26 → 1.12 ms), because 2 packets per frame go out faster than 5. That matches slot 2 (−2.7…−4.5 ms).
- **Encode is bimodal on the air unit [PROVEN: sidecar per frame, base b, n = 8137].** 76 % of frames take 6.0–6.5 ms and 24 % take 8.0–9.0 ms, with nothing in between. The slow frames come in bursts of 1–10+, are not periodic by frame id, and the 10 s medians are stable. At 480p the slow fraction is near 50 %, so the median jumps between the two modes from one waybeam instance to the next: rec a 3.07 ms against rec b 1.90 ms, same config, same p95 of 3.57 ms. The first reading, "2000 kbit/s costs +1.1 ms of encode", was withdrawn for this reason. The table therefore uses the mean of a and b (2.59 ms). With every frame in the fast mode, REC would start at ~26.8 ms [INFERRED: s_air 2.0 instead of 2.59]. The cause of the bursts is an open air-side lever of −1…−2 ms [SPECULATION: a beat against another periodic load such as DMA/bus or CPU]; it is on the OpenIPC session's list.
- **The 20–25 ms target is not reached.** In REC's 27.4 ms floor, the fixed parts are the panel (10.2 ms, latch → light) and the air → Quest floor (1.9 ms). What remains reachable: the encode bursts (−0.6 ms on average, up to −1.5 ms), and the latch wait (3.1 ms, since a 166 fps source overruns the 119.70 Hz display and needs no phase lock, W3b). Getting below 25 ms would take a shorter panel path than this Quest 2 offers [INFERRED: floor minus fixed terms].
- **Not assessed:** picture quality at 480p / 2000 kbit/s. Setting REC as the default is the coordinator's / the user's decision.

## Field of view against latency: 480p167 vs 720p120 vs 1080p90 scaled (W3c, 2026-09-27)

**Question:** 480p167 is a narrow crop of the sensor, 33 % × 44 %. What does a wider view cost in latency? The three modes that run: **a480** = [7] 640×480 @ 167 fps (REC); **c720** = [6] 1280×720 @ 119.2 fps; **d1080s** = [2] 1920×1080 @ 90 fps binned, scaled in the VPE to 848×480 for encode. All at 2000 kbit/s, FEC 4/8, MCS2, 12 dBm, with the O112 thread pin active, so the encode is no longer bimodal. Same method as W3 and before / after: [w3_budget.py](../../scripts/quest-latch/w3_budget.py), order a → c → d → d → c → a (N = 2), waybeam and the app restarted in every segment, the air unit's sidecar running in parallel with each Quest trace. c720 runs within 1 % of the display rate, so its latch wait is the long-run mean, half a period (4.18 ms; measured 3.95 / 4.05). **RES_4 1472×816 @ 150 (FOV 76 × 75 %) was dropped:** with native encode, VENC ran at 0.48 fps with MainScl DropCnt +734 in 10 s, the same failure as the historical RES_4 [PROVEN: OpenIPC session, air 1790532076].

| Mode | FOV (sensor share) | encode size | capture | readout | ISP (+VPE) | encode (median) | spread | decode | latch wait | pkt/frame | loss | undecoded | **total G2G** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **a480** 480p167 | 33 × 44 % | 640×480 | 3.00 | 2.34 | 1.5–3.5 | 1.87 | 1.05 | 1.69 | 3.10 | 1.79 | 0.06 % | 0.03 % | **26.7 – 32.0 ms** |
| c720 720p120 | 66 × 66 % | 1280×720 | 4.19 | 3.54 | 2.0–4.0 | 3.38 | 1.48 | 2.05 | 4.18 | 2.08 | 0.14 % | 0.10 % | 33.0 – 38.3 ms |
| d1080s 1080p90 → 848×480 | 99 × 98 % | 848×480 | 5.53 | 5.31 | 2.0–5.0 | 2.28 | 2.02 | 1.88 | 4.09 | 2.50 | 0.46 % | 0.32 % | 35.3 – 41.6 ms |

[PROVEN per segment: [air TSV](data/w3c-2026-09-27-air.tsv), Quest outputs `data/w3c-2026-09-27-quest-<mode>_<rep>.txt`, [budget](data/w3c-2026-09-27-budget.txt). FOV and readout from the IMX415 mode table (OpenIPC `repos/tasks/research/imx415-fov-modes-2026-09-27.md`). The ranges carry the [INFERRED] ISP (for d1080s widened by the VPE scale, < 1 ms by source) and panel terms.]

- **The trade-off:**
  - c720 costs **+6.3 ms** for **3.0×** the field-of-view area;
  - d1080s costs **+9.1 ms** for **6.7×**, i.e. the whole sensor;
  - from c720 to d1080s: +2.8 ms for 2.2× more area.

  All three ranges are disjoint (own ranges without the shared panel term: a480 < c720 < d1080s) [PROVEN: `decide`, budget file].
- **Where d1080s's latency goes:**
  - the longer frame period at 90 fps: capture phase +2.5 ms against a480;
  - the full-height readout: +3.0 ms.

  The VPE downscale costs no visible encode time. Encode at 848×480 takes 2.28 ms, against 1.87 ms at 640×480 and 3.38 ms at 1280×720, so a small encode size is what keeps d1080s close to c720.
- **Detail per degree (angular resolution):** a480 has 640 px over 33.1 % of the sensor width, 19.3 px per %; c720 has 19.2 px per %; d1080s has only **8.6 px per %** [INFERRED: arithmetic]. d1080s shows the whole scene but ~2.2× softer; c720 keeps a480's sharpness over 3× the area. The screenshots per mode are with the session that took them (pixelpilot-xr-22).
- **Robustness:** d1080s lost more (0.46 %, 5 and 13 gaps) than c720 (0.14 %) and a480 (0.06 %). Its frames are 2.5 packets against 1.8 [PROVEN]. Whether that is the mode or the time of day is not settled at N = 2 [SPECULATION].
- **With the O112 pin, encode is unimodal**: a480 encode p95 1.92 ms, against 3.57 ms without the pin. a480's floor drops from 27.4 (before / after) to **26.7 ms** [PROVEN: air rows].
- **Extra arm e720s: 720p120 scaled in the VPE to 848×480** (FOV 66 × 66 %, the cheaper 848×480 encode). Separate palindrome a480 → e720s → e720s → a480 (N = 2), same settings. Viability check: VENC 119.25 fps, DropCnt 0 [PROVEN: OpenIPC session, air 1790533103].

  | Mode | FOV | encode size | capture | readout | ISP (+VPE) | encode | spread | decode | latch wait | pkt/frame | loss | undecoded | **total G2G** |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | a480 (this arm) | 33 × 44 % | 640×480 | 3.00 | 2.34 | 1.5–3.5 | 1.87 | 1.21 | 1.69 | 3.08 | 1.80 | 0.17 % | 0.07 % | 26.9 – 32.2 ms |
  | **e720s** 720p120 → 848×480 | 66 × 66 % | 848×480 | 4.19 | 3.54 | 2.0–5.0 | 2.14 | 1.24 | 1.85 | 4.18 (uniform; measured 3.68 / 3.85) | 2.08 | 0.45 % | 0.19 % | **31.3 – 37.6 ms** |

  [PROVEN per segment: [air TSV](data/w3c-e720s-2026-09-27-air.tsv), Quest outputs `data/w3c-e720s-2026-09-27-quest-<mode>_<rep>.txt`, [budget](data/w3c-e720s-2026-09-27-budget.txt).]
  - Against a480: **+4.9 ms for 3.0× the area.** a480 reproduced within 0.2 ms of the main arm.
  - **Against c720, same field of view:** the measured segments are ~1.7 ms shorter. Encode+send is 2.24 against 3.49 ms, spread 1.24 against 1.48, and decode 1.85 against 2.05. The ISP range is wider because of the VPE scale (< 1 ms by source), so the total ranges overlap: 31.3–37.6 against 33.0–38.3 ms. e720s is **~0.7–1.7 ms faster** than c720 [INFERRED: measured segments minus the VPE uncertainty]. The price is detail: 12.8 px per % of sensor width, against 19.2 for c720 (~1.5× softer), still sharper than d1080s (8.6).
  - Loss 0.45 % comes from one burst in e720s_a (17 gaps, a transport max of 36 ms). e720s_b lost 2 of 2231 [PROVEN]. So it is not attributed to the mode.
- **Reading:** for the lowest latency, a480 (26.7–32.0 ms, narrow view). For 3× the view, e720s (+4.9 ms, ~1.5× softer) or c720 (+6.3 ms, as sharp as a480). For the whole scene, d1080s (+9.1 ms, ~2.2× softer). Which one to use is the user's choice. The numbers above are the whole cost of each.
