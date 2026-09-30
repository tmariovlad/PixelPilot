# Stats pages: the data backend (per-segment latency + link), 2026-09-29

The in-headset menu's Stats pages (menu session, `app/xr/.../menu/StatsPages.java`) read a `StatsSnapshot` every
0.5 s from `XrVideoActivity.statsSource`. This file describes where each number comes from. **Status: built and
tested on the host and JVM; not yet installed or checked on the headset** (see §5).

Keywords: stats page, per-segment latency, G2G estimate, RTP sidecar, waybeam, clock sync, NTP offset, MCS, RSSI dBm,
SNR, pre-FEC, post-FEC, IDR, FrameTimeline, rtp_ts, latență pe segmente, legătură.

## 1. Pieces

| Piece | Where | Does | Tests |
|---|---|---|---|
| Data model | `app/xr/.../stats/StatsSnapshot`, `Segment`, `StatsSource` | Numbers only; NA / NaN / n=0 = unknown | `StatsSnapshotTest` |
| Sidecar client | `app/.../stats/SidecarProtocol`, `SidecarClient`, `ClockSync` | SUBSCRIBE every 2 s to `10.5.0.10:5602` over the wfb tunnel; parses MSG_FRAME (+ ENC_INFO / TRANSPORT trailers); SYNC every 1 s → air↔Quest offset (lowest-RTT of the last 16) | `SidecarProtocolTest`, `ClockSyncTest`, `SidecarClientTest` (fake sidecar on 127.0.0.1) |
| RTP tag to the decoder | `videonative/.../RtpTag.h`, `parser/ParseRTP`, `NALU`, `AccessUnitAssembler`, `VideoDecoder` | Every NALU carries its packet's (ssrc, RTP ts) and a CLOCK_MONOTONIC completion time; an AU keeps its own picture's tag even when a lost marker closes it at the next picture | `ParseRTP_test`, `H26XParser_test`, `AccessUnitAssembler_test` |
| Decoded frames | `videonative/.../FrameTimeline.h`, JNI `VideoPlayer.drainFrameTimes()` | Input PTS → tag; the output's PTS finds the frame; a frame fed as slices completes at its last slice; reset when the decoder is released (codec switch) | `FrameTimeline_test` (8), `QuestFrameTest` |
| Latency window | `app/.../stats/LatencyWindow` | Pairs air and Quest frames by (ssrc, ts); per-segment p50/p95 over 2 s | `LatencyWindowTest` (8) |
| RX rate | `wfbngrtl8812/.../RxRateHistogram.h`, `WfbNgLink.takeRxRate()`, `stats/RxRate` | Most frequent (rate code, bw, STBC, LDPC, SGI) of the video packets per window; decoded to MCS / NSS | `RxRateHistogram_test` (5), `LinkWindowTest` |
| Link window | `app/.../stats/LinkWindow` | Loss, FEC, RSSI/SNR from the wfb stats windows | `LinkWindowTest` (8) |
| Collector | `app/.../stats/StatsCollector`, `StatsWiring`, `GridDisplayEstimate`, `CounterRate` | The StatsSource: a 0.5 s tick drains frames, takes the rate and the lever counters, builds the snapshot | `StatsCollectorTest` (4) |

## 2. Latency segments (per frame, matched by ssrc + RTP timestamp)

| Segment | Definition | Clock | Tag |
|---|---|---|---|
| encode | `frame_ready_us − capture_us` | air CLOCK_MONOTONIC only | [PROVEN clock: waybeam f8742fe `src/star6e_video.c:138-161`] |
| airSend | `last_pkt_send_us − frame_ready_us` | air only | [PROVEN clock: `src/rtp_sidecar.c:216,236`] |
| link | Quest frame complete − `last_pkt_send_us` mapped to the Quest clock | both, via ClockSync | offset error ≤ RTT/2 [INFERRED: NTP bound] |
| decode | MediaCodec output release − frame complete | Quest only | [PROVEN: code] |
| toDisplay | release → next predicted display on the XR grid (`predictedDisplayTime` + k·period) | Quest | **ESTIMATE**: the compositor latch is not visible in the app ([display-latency.md](display-latency.md)) |
| total | sum of the five, only for frames where all are known | — | "G2G est." without the sensor readout and the panel |

**Clocks.** On the air build (`13b85893` = waybeam `f8742fe`, per the OpenIPC repo's
`repos/tasks/au-plans-2026-09-27/au10-impl/00-AU10-IMPL.md:54`) every sidecar timestamp is `wb_monotonic_us()` =
CLOCK_MONOTONIC (`src/timing.c:8`), including frame_ready, last_pkt_send and the SYNC t2/t3; capture_us is the PTS
converted to CLOCK_MONOTONIC per frame. The header's "CLOCK_MONOTONIC_RAW" comments are stale [PROVEN in code;
not yet checked live]. On the Quest, System.nanoTime, `clock_gettime(CLOCK_MONOTONIC)` (RtpTag, decoder output) and
the XR grid (converted with `xrConvertTimeToTimespecTimeKHR`) are the same clock [INFERRED].

**"Frame complete"** is when the frame's last RTP packet is handed to the parser, after the reorder queue, so the
link segment includes airtime, FEC and reordering. With AU aggregation off (the default) each slice is fed as it
completes; the frame completes at its last slice.

## 3. Link and decoder fields

| Field | Source | Formula | Tag |
|---|---|---|---|
| pDataPct / postFecPct | wfb video stats window (WfbNGStats) summed over 2 s | (fec_rec + lost) / (delivered + lost); lost / (delivered + lost), as `scripts/quest-latch/link_audit.py` p_data | [PROVEN: code] |
| fecRecPerS / holesPerS | same | per second over the window; holes = packets lost after FEC | [PROVEN: code] |
| rssiA/BDbm, snrA/BDb | WfbNGStats rssi_a/b, snr_a/b (window means of devourer's raw PHY status) | dBm = raw − 110, dB = raw / 2, as devourer does (`src/LinkHealth.cpp:8-9`) | [PROVEN: devourer's convention] |
| mcs / nss / bwMhz / sgi / stbc / ldpc | RxRateHistogram of the video packets | Realtek rate code: 0x0C + n HT, 0x2C + n VHT (devourer `ieee80211_radiotap.h:188-236`), 9-bit halmac 0x80 / 0x100 | [PROVEN: code] |
| decErr | WfbNGStats count_p_dec_err | sum over the window | [PROVEN: code] |
| fpsDecoded | DecodingInfo.currentFPS | — | [PROVEN: code] |
| undecodedPerS | air frames (sidecar) − decoded frames, per second | NaN without the sidecar | [PROVEN: code] |
| idrReqOk/FailedPerS, frozenSlicesPerS | VideoPlayer.leverCounters() (IdrRequester, FreezeUntilIdr) | rate of the cumulative counters over 2 s | [PROVEN: code] |
| frameKbP50, pktsPerFrameP50, idrPerS | sidecar ENC_INFO trailer / seq_count | median / IDR frames per second | [PROVEN: code] |

## 4. Limits

- The sidecar must be enabled on the air (`outgoing.sidecarPort` 5602 in waybeam's config). Without it the air segments
  are NaN, and the page shows "n/a (no sidecar)" after 2 s [INFERRED: StatsPages behaviour per the menu session].
- toDisplay is an estimate (§2); the photons come later still (see [display-latency.md](display-latency.md)).
- The sidecar travels in the same wfb tunnel as the reports: when the link is bad, both the frames and the sidecar thin
  out together.
- Only decoder 0 (the one on the XR surface) is tracked.

## 5. Headset check (to do; needs a slot with the air on)

1. Install the build with these commits; open the menu's Stats pages.
2. `matchedFrames` > 0 and `clockSynced`: the sidecar arrives and matches the decoded frames.
3. Plausibility against measured numbers: encode ~4 ms, decode ~1.5 ms ([decoder-levers.md](decoder-levers.md)),
   latch wait ~3 ms ([display-latency.md](display-latency.md) slot T); the link segment compared with
   [g2g-budget.md](g2g-budget.md).
4. MCS / RSSI against the air's configured MCS and the HUD's RSSI column.

## 6. Recording what the page shows, and joining a PC sidecar capture

- **PPXR_STATS lines.** While a Stats page is on screen (and for 2.5 s after), or always with the `general` pref
  `stats_log = true` (for slots), the app logs one line every 2 s with tag `PPXR_STATS`: fixed-order `k=v` pairs, unknown
  values `-`, `t` = the Quest's CLOCK_MONOTONIC ms (`app/.../stats/StatsLine.java` is the one definition of the keys).
  Capture it **detached** ([ab_detached.sh](../../scripts/quest/ab_detached.sh) now includes the tag; a streamed adb
  logcat over the Quest's Wi-Fi disturbs the link it measures, see [uplink-t4-analysis.md](uplink-t4-analysis.md)), then
  `python3 scripts/quest-latch/stats_log.py <logcat file> out.tsv` ([stats_log.py](../../scripts/quest-latch/stats_log.py),
  test `test_stats_log.py`).
- **PC-side sidecar with absolute times.** [sidecar_log.py](../../scripts/quest-latch/sidecar_log.py) now also writes the
  absolute air `capture_us` / `ready_us` / `send_us` (air CLOCK_MONOTONIC) and, from a SYNC exchange at the start and every
  10 s, `air_minus_pc_us` + `sync_rtt_us` (lowest RTT of the last 6). With ab_detached's `quest_minus_pc_ms`, an air time
  maps to the Quest's wall clock as `air − air_minus_pc_us + quest_minus_pc_ms·1000`, so a PC capture joins a Quest trace
  of the same window. The first 10 columns are unchanged. (A capture made with the old script, e.g.
  `scripts/quest/out/sidecar_probe_1080p90_h264_30M.tsv`, has only the deltas and cannot be joined.)

## 7. A live queue signal for rate control (research for openipc-1f, 2026-10-01; no code yet)

openipc-1f designs air-side rate control for the 40 ms ceiling over capacity: the bitrate must drop *before* the knee, because over capacity nothing in wfb_tx or the driver holds 40 ms ([link-envelope](link-envelope.md), age-guard gate: floor ~130 ms). This section is what the Quest can feed it.

- **Delay rises before loss** [INFERRED from PROVEN steps in [link-envelope](link-envelope.md)]. At the MCS7 knee, m7b20f48 (3710 pkt/s) queued +20 ms at 0.22 % loss after FEC, and MCS6 long GI at 25 Mbit/s read +55 ms at the same loss as MCS7. A delay signal therefore leads the loss signal.
- **What the app has live** [PROVEN: code]:
  - `link` per frame = complete on the Quest − the air's `last_pkt_send` (ClockSync), folded over a 2 s window every 500 ms (`StatsCollector.java:18-19`, `LatencyWindow.java:18,124`).
    - Caveat: it needs the sidecar's record of each frame, which travels down the same congested link. Under congestion the signal therefore lags by about the delay it measures.
  - Per decoded frame (ssrc, RTP timestamp, complete ns, decoded ns), drained from native to Java (`QuestFrame.java:12-26`, `RtpTag.h:13-15`).
    - From these, the **relative one-way delay** = complete − RTP ts / 90 kHz, minus its running minimum, is the queueing delay with no sidecar and no clock sync. It is the standard delay-based congestion signal and what `ab_segments.py`'s drift line does offline. Clock drift (+71 ppm measured) moves it by only 0.07 ms/s, so a minimum over a few seconds holds.
    - Limit: only the completion time is tagged, not the first packet's arrival. A large frame (scene change, IDR) completes later without any queue, so a p90 over completion mixes in frame size. A first-packet time in `RtpTag` would separate the two (a small native change).
  - Holes, pre-/post-FEC loss and RSSI per 2 s window (`LinkWindow.java:48-52`).
- **Where it fits in the alink report** [PROVEN: the parser, openipc repo `tools/alink-air/src/parse.c:52-99`, `parse.h:44`; constraints from openipc-1f]. The app sends `%ld:%d:%d:%d:%d:%d:%f:0:-1:%d:%s` = 11 fields (`WfbngLink.cpp:680-682`).
  - The parser takes up to 16 fields in a line of at most 255 bytes, and reads field 11 as an optional pre-FEC %.
  - New numeric fields therefore go at 12–15. Fields 0/1/3/4/9 must stay integers, and recovered = lost = 300 is the link-dead sentinel.
  - The other programs in the local repos that use this line send it and do not parse it (aviateur `wfbng_link.cpp:460`; OpenIPC-air_manager does not read it) [PROVEN: grep]. Upstream alink_drone's parser is not in any local repo, so whether extra fields break it is [SPECULATION].
- **Latency of the feedback path**:
  - Measurement: one window of ~250 ms (30–40 frames at 120–167 fps).
  - Java → native hand-off: a new JNI setter, like `nativeSetFecThresholds` (`WfbNgLink.java:21`).
  - Report slot: 0–250 ms at 4 reports/s (`UplinkSchedule.h:30`). A change can go out at once as "news", as IDR requests and fec_change do (`UplinkSchedule.h:41-44`, polled every 20 ms).
  - Tunnel one-way: ~2.5–3 ms [INFERRED: ClockSync round trip 4.8–5.9 ms over the same tunnel, PPXR_STATS `rtt` 2026-09-30].
  - alink: reads at once, and its policy ticks every 100 ms (`config.c` tick_ms, openipc-1f).
  - **Total ~0.3–0.6 s**, or ~0.3–0.4 s with the change sent as news.

### 7.1 Offline check: relative one-way delay per frame (item 5 for openipc-1f, 2026-09-30)

This tests the signal proposed above against today's traces.
- **Tool:** [owd.py](../../scripts/quest-latch/owd.py) (test `test_owd.py`, 9 tests).
- **Signal, per frame:** `first` = first-packet arrival − RTP ts, and `last` = completion − RTP ts. Each is made
  relative to its own trailing running minimum over W seconds, as a live receiver would compute it.
- **Windows:** 250 ms, cut per step, inside the steps' guard bands.
- **Data:** [HDP](data/owd-2026-09-30-hdp.txt), [L6](data/owd-2026-09-30-l6.txt), [-Y slot](data/owd-2026-09-30-y.txt),
  [S2](data/owd-2026-09-30-s2.txt), and the MCS knee run g56 ([all states](data/owd-2026-09-30-g56.txt),
  [knee loss profile](data/owd-2026-09-30-g56knee.txt)). The exact command is in each file's first line.

**Clock drift is +0.069…+0.073 ms/s in all five captures** [PROVEN: the median per-step slope of the per-second
minimum]. Per step, because a waybeam restart moves the RTP base between steps (a whole-run fit read up to −1658
ms/s). The trailing minimum therefore lags by about drift × W: the W = 10 s floor sits ~0.6 ms above W = 2 s in every
capture.

**(a) Clean-link floor** (W = 2 s, `first`, ms). Per state: the median of the 250 ms window p50, then the median /
p90 / p99 of the window p90.

| capture, state | windows | p50 | p90 median | p90 p90 | p90 p99 |
|---|---|---|---|---|---|
| L6 race 167 fps, f320 / f216 / f384 | 484 / 242 / 121 | 0.67–0.68 | 0.93–0.95 | 1.74–2.26 | 8.0–8.2 |
| -Y slot race, r14n / r14y / r24n / r24y | 630–722 | 0.62–0.73 | 0.73–0.97 | 1.16–1.38 | 2.7–5.3 |
| S2 race, r480 / r360 | 2404 each | 1.15 / 0.96 | 1.32 / 1.11 | 1.69 / 1.59 | 4.0 / 7.9 |
| g56 1080p90, clean m7b16f48 / m7b20f46 | 210 / 216 | 0.33–0.36 | 1.39–1.50 | 2.7–2.9 | 3.1–8.6 |
| HDP 720p120 25M q7, p2400 / p3000 / p3900 | 1440 each | 0.58–0.65 | 1.06–1.09 | 4.6–5.2 | 5.4–5.7 |
| **knee** g56 m7b20f48 (+19.8 ms queue) | 209 | 8.22 | **10.10** | 14.64 | 18.2 |

- A typical clean window has p90 ≈ 1 ms. One window in ten reaches 1.2–2.3 ms on race, and ~5 ms on HDP's 25M.
- The 1-in-100 window reaches 3–8.6 ms.
- At 4 windows/s, a single-window threshold under ~9 ms would fire every ~25 s on a clean link. A threshold therefore
  needs persistence (several consecutive windows) or a per-mode floor [INFERRED from the table].
- **Caveat:** HDP ran with the race wfb_tx flags (`-Y`, no `-R`) against an APK without the RX drain
  ([link-envelope](link-envelope.md) HDP caveat). Its higher p90 p90 may be frames held behind gaps until the next
  frame [SPECULATION].

**(b) Payload and frame size** [PROVEN: HDP file].
- `first` median is flat across payloads: 0.65 / 0.60 / 0.58 ms at 2400 / 3000 / 3900.
- Its p95 rises 4.02 → 4.71 → 4.78 ms. That is +0.69 ms at 3000, like lnk95's +0.72, but only +0.76 at 3900, where
  lnk95 rose +1.54 ([hdp-fit](data/hdp-fit-2026-09-30.txt)).
- `last` p95 carries the completion tail: 3.90 → 8.23 → 8.79 ms.
- **First-packet removes the frame-size effect.** The slope of relative OWD vs packets per frame is:
  - `first`: −0.24…+0.13 ms/packet in every capture (~0 on HDP: +0.005…+0.012);
  - `last`: +0.16…+1.7 ms/packet.
- As openipc-1f noted, `first` still includes the air's encode time, since the RTP ts is the capture time.

**(c) Does delay lead post-FEC loss?**
- **No transient rise before individual loss bursts** [PROVEN: loss-locked mean in 50 ms bins over the second before
  each burst, vs 20 shifted-onset controls]:
  - HDP, 796 bursts / 2579 packets: every pre-onset bin is within the control range (one bin at −300 ms is 0.99 vs
    the controls' max 0.97, about what 20 bins give by chance). The only rise is +0…+50 ms, after the loss (frames
    held behind the gap).
  - g56 knee states, 329 bursts: the same, at W = 2 s and at W = 60 s.
  - So at these operating points the loss is radio loss. It is not preceded by a queue spike.
- **Over capacity, the queue is standing, and a short running minimum hides it** [PROVEN: g56]. Median of the window
  p50 of `first`:

| state (queue vs the clean drift line, link-envelope) | W = 2 s | W = 10 s | W = 60 s |
|---|---|---|---|
| m6b25f46 (+55 ms) | 3.1 | 4.9 | **59.9** |
| m7b20f48 (+19.8 ms) | 8.1 | 15.4 | **22.2** |
| m7b25f46 (clean) | 1.3 | 1.9 | 4.6 |

  - A live signal needs a base older than the queue: a long-window minimum with the drift subtracted (the drift is
    stable, +0.07 ms/s, so it can be estimated), or the minimum held since the last rate decrease.
  - W = 2 s still separates m7b20f48 (p90 median 10.1 ms) from the clean states, but not m6b25f46 (4.5 ms).
- **Lead time from a switch into over-capacity: N = 1.** In g56's m7b20f48 step, the W = 2 s window p50 passed 3 ms
  0.07 s after the switch, and the first post-FEC loss came 1.98 s later. Every other step's first losses fall within
  0.2 s of the switch, where the reconfiguration itself drops packets, so they cannot time a lead. Measuring the lead
  properly needs a slow bitrate ramp through the knee, without a switch [SPECULATION until run].

### 7.2 The live signal: reference algorithm and test vectors for the app's port (2026-09-30)

§7.1 showed that a short running minimum hides a standing queue. openipc-1f adopted a base held since the last rate
decrease, with the drift subtracted, plus persistence over N windows. The Quest-side value it consumes is computed
by the reference `owd.LiveBase` in [owd.py](../../scripts/quest-latch/owd.py). A port (pixelpilot-xr-25's RtpTag
first-packet + owd50/owd95 in PPXR_STATS) must match it on the vectors below.

**Algorithm**, per frame, causal. `v` = first-packet arrival − RTP ts (ms), `t` = arrival (ns):
- `rel = (v − d·t) − min over the trailing window of (v − d·t)`, where `d` is the air/Quest clock drift (ms per s).
- `d` = Theil-Sen slope of the per-10 s block minima of `v` over the last 300 s:
  - Until 6 blocks are complete, the prior 0.07 ms/s is used (§7.1: +0.069…+0.073 in five captures).
  - `d` changes only when a block completes; the window minimum is then rebuilt with the new `d`.
  - After that bootstrap, a block joins the fit only if its minimum is at most 2 ms above the current line. A
    standing queue lifts the minima; without this gate, a 150 s queue was learnt as drift and read 15 ms instead of
    50 (test `test_a_queue_longer_than_the_window_...`).
- **Reset:** a step of more than 1000 ms between consecutive frames (the RTP base moved: a waybeam restart) clears
  all state, drift back to the prior.

**Unbounded window: keep the hull, not the history** (added after reviewing the app's port, 2026-09-30). With a plain window list, the unbounded instance would hold every frame since the reset (0.3–0.6 M per hour at 90–167 fps) and rescan them on each drift update. The minimum of `v − d·t` over any point set lies on its lower convex hull for every `d`, so `LiveBase` keeps only that hull (monotone chain; frames arrive in time order) and the running minimum. The outputs are identical: both vector files regenerate byte for byte. `test_the_unbounded_base_keeps_a_bounded_state` checks that 100k frames leave < 200 points.

**Which window.** The value sent to the air should use the **unbounded** window (`window_s = inf`: the minimum
since the last reset, drift-corrected). The air then applies its own minimum since the last rate decrease on top. A
Quest-side window of 60 s would already have absorbed a queue standing longer than 60 s, and the air could not get
it back [PROVEN: synthetic vector, 250–400 s: W = 60 s median 0.71 ms vs W = ∞ 50.5 ms].

**Limits** [INFERRED from the algorithm]:
- A floor rise of more than 2 ms that is not a queue (e.g. a mode change with a slower encoder, without an RTP
  restart) is treated as a queue until the next reset. So a mode change should reset the base.
- A queue that stands longer than the 300 s horizon leaves fewer than 6 blocks on the line, and the fit
  bootstraps from the queued minima. The rate control must never let a queue stand that long.

**Test vectors** in [testdata/owd/](../../scripts/quest-latch/testdata/owd/), written by
[owd_vectors.py](../../scripts/quest-latch/owd_vectors.py). CSV columns: `t_ns, first_ms, rel_w60_ms, rel_winf_ms`,
with `#` header lines giving the parameters.
- `synthetic.csv`: 6000 frames at 10 fps. Drift 0.06 ms/s (so `d` must be learnt), a 0–1 ms ripple, +50 ms standing
  250–400 s, and a +5000 ms RTP jump at 500 s.
- `g56_m6.csv`: 10,947 real frames of g56's first two steps. m7b25f46, clean: median 1.45 ms. Then m6b25f46: median
  55.6 ms at W = 60 s and at W = ∞, matching link-envelope's +55 ms.
- `test_owd.py` checks that `synthetic.csv` still equals the reference's output (tolerance 1e-8).
- A port should match `rel_*` to about 1e-6 ms, float vs double.



### 7.3 The app's live signal (branch `owd`, 2026-10-01; reviewed by pixelpilot-xr-36, not installed yet)

- **First-packet time per frame** [PROVEN: host tests 121/121]. `RtpTag.firstNs` = when the first packet of the frame's RTP timestamp reached the parser (`FirstArrival` in `RtpTag.h`, set per packet in `ParseRTP::noteCurrentPacket`). `FrameTimes.firstNs` = the earliest over the frame's inputs, and the Stats drain packs 5 longs per frame (`VideoPlayer.cpp` nativeDrainFrameTimes, `QuestFrame.java`).
- **LiveBase.java** is a method-for-method port of §7.2's `owd.LiveBase`. It matches the reference to 1e-6 ms on every frame of both vector files (synthetic.csv 6000 frames; g56_m6.csv 10,947 real frames), for the 60 s and the unbounded window [PROVEN: `LiveBaseTest`].
- **OwdWindow.java** feeds it v = first-packet arrival − RTP timestamp / 90 kHz (32-bit unwrap; reset on a new SSRC) and folds the stats window [PROVEN: `OwdWindowTest`, 7 tests; mutants on the unwrap and the SSRC reset are killed].
- **PPXR_STATS** gains `owd50`/`owd95` (60 s base, `owdw=60`), `owdu50`/`owdu95` (unbounded base, since the last reset: the value for the air's rate control, per §7.2) and `owdd` (the learnt drift, ms/s).
- **The unbounded base keeps a bounded state** [PROVEN: `LiveBaseTest.theUnboundedBaseKeepsABoundedState`, the twin of test_owd.py's]. It stores only the lower convex hull of (t, v) (owd.py 8b5b879): 100,000 frames with a wrong prior leave < 200 points, where the first port kept all 100,004. The outputs are unchanged, and the vectors still match to 1e-6.
- **Where `firstNs` is taken: after the reorder queue** [PROVEN: `VideoPlayer.cpp` onNewRTPData]. The offline `owd.py` reads the trace counters `ppxr_rtp_seq/ts`, which fire on raw arrival, *before* `BufferedPacketQueue`. The live `firstNs` is taken in the parser, after the queue releases the packet. So the live value includes any reorder hold on a frame's first packet (a wait for a missing earlier packet): ~0 on a clean link, but different under loss. The live cross-check must look for exactly that. Stamping `firstNs` at raw arrival would be a small follow-up if rate control needs it without the hold.
- **Not wired into the alink report yet.** That waits for openipc-1f's design (fields 12–15). The first check on the headset is a live capture cross-checked against `owd.py` on the same trace.
