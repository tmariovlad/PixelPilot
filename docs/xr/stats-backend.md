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
