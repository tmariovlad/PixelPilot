# Decoder levers on Quest 2 (measured)

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

MediaCodec decode time on Quest 2 per lever, in the order the measurements were made. Later sections correct earlier ones (the corrections are marked in place). The lever table itself is in the [guide](../xr-quest.md#use).

## First on-device results (Quest 2, 2026-09-26, Horizon OS build UP1A.231005.007.A1)

Stream: recorded x265 RTP (720p) replayed over **Wi-Fi** from a PC to `udp://<quest>:5600` (no RTL8812AU), debug build `com.openipc.pixelpilot.xr` installed next to the user's release PixelPilot 0.21.0.

- XR path works: `OpenXR ready: 12 extensions`, session reaches FOCUSED, `requested 120 Hz -> 120 Hz (result 0)`, video attached to the compositor surface, frames decoded [PROVEN: logcat].
- Decoder on Quest 2 = `OMX.qcom.video.decoder.hevc`; no `c2.qti.*.low_latency` component exists (the LLC lever falls back to the default).
- **Decoder levers, steady-state decode time (queue → output release), N = 3 shuffled rounds, ~425 decoded frames each** (raw: [measurements-2026-09-26-quest2-decoder-levers.csv](data/measurements-2026-09-26-quest2-decoder-levers.csv)):

  | Config | mean ms | min | max |
  |---|---|---|---|
  | stock (all keys off) | 8.93 | 8.91 | 8.95 |
  | LL (upstream default) | 10.15 | 10.13 | 10.17 |
  | LL + decode order | 10.15 | 10.08 | 10.21 |
  | **LL + max operating rate** (drops `priority=0`) | **4.99** | 4.97 | 5.00 |
  | LL + low-latency component (absent → default) | 10.19 | 10.09 | 10.34 |
  | LL + whole access units | 10.13 | 10.12 | 10.14 |

  Operating rate halves the decode term (−5.2 ms vs LL). The upstream LL key set is 1.2 ms *slower* than no keys on this decoder; whether that comes from `priority=0` (which the OR config drops) is the next bracket: {stock+OR, LL−priority}. → **Answered below: not `priority`, but the low-latency mode itself.** [PROVEN for this stream/decoder; untested at other resolutions/bitrates]
- `xr_thread_hints`: the runtime rejects every hint with `-1000003001` (`XR_ERROR_ANDROID_THREAD_SETTINGS_FAILURE_KHR`) → lever currently **inert on Quest 2**.
- Picture corruption seen in the headset with the P-frame test stream: ~70 % of its packets never arrived (425 of ~1440 frames decoded, reassembly 32–42 ms). An all-intra stream at ~3× the packet rate arrived complete (1080/1080 frames, reassembly 1.8 ms, decode 2.5 ms) → consistent with **Quest Wi-Fi power save** dropping/bunching a light UDP stream [INFERRED], not a decoder fault. Irrelevant with the RTL8812AU on USB-C; for Wi-Fi tests keep the radio busy.

## Which low-latency key slows the Quest 2 decoder? (key isolation, 2026-09-26)

Same stream and method as above, one key at a time via `dec_debug_key_mask`; every run printed the keys the
decoder was really configured with (read back from the `Configuring decoder` log line). N = 3 shuffled rounds
(raw: [measurements-2026-09-26-quest2-key-isolation.csv](data/measurements-2026-09-26-quest2-key-isolation.csv)):

| Config (keys applied) | mean ms | min–max |
|---|---|---|
| none | 8.95 | 8.90–8.98 |
| `low-latency` only | **10.18** | 10.12–10.22 |
| `vendor.qti-ext-dec-low-latency.enable` only | **10.19** | 10.15–10.22 |
| `vendor.low-latency.enable` only | 8.92 | 8.91–8.94 |
| `priority`=0 only | 8.97 | 8.94–8.99 |
| upstream set (all 6) | 10.13 | 10.07–10.19 |
| upstream set without `priority` | 10.15 | 10.09–10.24 |
| **`operating-rate` only** | **4.59** | 4.56–4.62 |
| upstream set without `priority` + `operating-rate` | 5.00 | 4.98–5.03 |

- The slowdown comes from the Qualcomm "low-latency mode", which both the AOSP `low-latency` key and the qti key switch on (+1.2 ms each, not additive) [PROVEN]. `priority=0` and `vendor.low-latency.enable` do nothing here [PROVEN]. The earlier guess that `priority=0` was the cause was **wrong**.
- Without low-latency mode the decoder does not hold frames back (a held frame would cost ~16.7 ms at 60 fps; decode stays ~9 ms) [INFERRED from the numbers], so on this I/P-only stream the mode buys nothing and costs 1.2 ms. Why it is slower (e.g. less internal pipelining) is [SPECULATION].
- ~~Meta-headset defaults since this run: low-latency keys off, max operating rate on → 4.59 ms vs 10.15 ms upstream (−5.6 ms decode).~~ **Corrected 2026-09-26 by the clean-stream recheck below:** that stream lost ~70 % of its packets, and the "+1.2 ms from the LL keys" does not reproduce on complete streams. Low-latency keys are back **on** for every device, and operating rate stays on for Meta headsets.

## Clean-stream recheck: LL keys + operating rate is fastest (2026-09-26)

These streams arrive almost whole (~670 of 720 frames decoded per 12 s run), unlike the 1-slice stream above. The 720p/1080p test streams are single-slice x264/x265 at 60 fps. N = 3 shuffled rounds per stream, and every run's applied keys were checked. Raw data: [measurements-2026-09-26-quest2-lever-recheck.csv](data/measurements-2026-09-26-quest2-lever-recheck.csv). The CSV has no per-run rows for H.265 720p; only its summary was kept.

| Config | H.264 720p | H.265 720p | H.265 1080p |
|---|---|---|---|
| no keys | 1.96 (1.93–1.99) | 2.34 (2.18–2.63) | 3.57 (3.37–3.92) |
| LL (upstream) | 2.01 (1.95–2.11) | 2.31 (2.28–2.35) | 3.31 (3.21–3.47) |
| OR only (previous Quest default) | 1.88 (1.80–1.99) | 1.95 (1.92–1.97) | 2.59 (2.49–2.74) |
| **LL + OR (new default)** | **1.56 (1.51–1.61)** | **1.79 (1.78–1.79)** | **2.32 (2.10–2.43)** |

- LL + OR is the fastest configuration on all three streams, and its frame counts match the other configs, so no frames are held back [PROVEN: the CSV plus the per-run `Configuring decoder` log lines]. The gain over OR-only is 0.16–0.32 ms. That is small, but the ranges barely overlap on any stream.
- The earlier "LL adds 1.2 ms" result came from a stream that was missing most of its packets. The decoder behaves differently on such a stream (concealment and many incomplete frames) [INFERRED]. That result does not describe a real link.
- Verified on the device after the change, with empty prefs: keys `LL+vLL+qti+hisi+rtc+OR` → 1.57 / 1.72 / 2.24 ms (H.264 720p / H.265 720p / H.265 1080p), with 0 errors [PROVEN: logcat, 2026-09-26].

## Codec, component and resolution (2026-09-26)

Setup: OR-only defaults at the time, 12 s single-slice streams, N = 3 shuffled rounds. Every run's component and keys were checked. Raw data: [measurements-2026-09-26-quest2-codecs.csv](data/measurements-2026-09-26-quest2-codecs.csv).

| Stream | default (OMX.qcom) ms | c2.qti ms |
|---|---|---|
| H.264 540p | **1.52** | 2.56 (only ~480 frames) |
| H.264 720p | **1.78** | 2.82 (only ~480 frames) |
| H.264 1080p | **2.36** | 3.32 (only ~480 frames) |
| H.265 540p | **1.59** | 2.58 |
| H.265 720p | **2.00** | 3.05 |
| H.265 1080p | **2.65** | 3.61 |

- The default OMX component beats `c2.qti.*` on every stream by about 1 ms. `c2.qti.avc.decoder` also delivers ~30 % fewer frames [PROVEN]. Keep `dec_component` empty.
- `c2.android.*` software decoders are not available to apps on Horizon OS, so they are not in the matrix.
- H.264 is 0.1–0.3 ms faster than H.265 at the same resolution. Going from 540p to 1080p adds 0.8–1.1 ms of decode [PROVEN].
- **Multi-slice H.264** (x264 `--tune zerolatency` uses sliced threads) makes PixelPilot send each slice as its own "frame". Such a stream needs **whole access units** (`au_aggregation`) or a single-slice encoder setting. The OpenIPC air unit's majestic encoder is single-slice by default [SPECULATION: not checked on the air unit].
- Decode is now ~1.5–2.5 ms. On Quest 2 the fixed display and compositor terms dominate G2G (up to 8.3 ms of refresh wait at 120 Hz plus the panel scan-out and backlight strobe). The next real gain can only be measured with the photodiode and the RTL8812AU.

## Live H.264 ↔ H.265 switch without an app restart (2026-09-29, code; device check pending)

**Before:** the decoder took its MIME type (`video/avc` / `video/hevc`) from the stream only when it was first configured. After an air-side codec switch it kept the old MediaCodec, and H.265 NALUs went into the H.264 decoder until the XR app was restarted. The old "TODO: switching between h264 / h265 requires re-setting the surface" in `VideoDecoder::interpretNALU` said the same [PROVEN: code before this change]. OpenIPC's `codec-h264-h265/00-H264-H265-timing.md` §3 says the Quest "needs NO restart … picks the decoder MIME packet by packet". That was wrong for the decoder: the parser followed the payload type per packet, but the MediaCodec did not.

**Now:**
- [CodecSwitch.h](../../app/videonative/src/main/cpp/CodecSwitch.h) reports the first NALU (or packet) of a different codec: RTP payload 96 = H.264, 97 = H.265. It never fires on the very first NALU.
- The parser (`H26XParser::parse_rtp_stream`) drops the old codec's half-built NALU on a switch. Without this, the first H.265 fragment end completed the stale H.264 bytes into a NALU flagged H.265. An H.264 slice header `0x41` reads as H.265 type 32, a VPS [PROVEN: host test failed before the fix].
- The decoder (`VideoDecoder::interpretNALU`) releases both MediaCodecs, forgets the saved SPS/PPS/VPS and the access-unit buffer, then configures the new codec from its first key frames. This also happens when nothing was configured yet, because an H.264 SPS/PPS next to an H.265 VPS looks like a complete H.265 set [PROVEN: host test].
- The output windows stay, so the new decoder is created on the same surface, the XR swapchain. Release and re-create under the feed lock is the mechanism of the withdrawn X23 (c) rebuild. That rebuild ran on the headset through 4 live mode switches, with healthy decode after each and ~35 ms more than an in-place adaptation [PROVEN: [UX audit, final slot item 4](research/2026-09-27-xr-ux-audit.md#final-slot-on-the-headset-2026-09-27)].
- The decoder summary line counts the switches: `| codec switch N (now H.265)`. Logcat has `codec changed to H.26x, rebuilding the decoder`.
- The app writes `ppxr_rtp_pt`, the payload type once per frame, into a system trace. `transport_analyze.py` prints the codec runs of a segment (`rtp_seq.codec_segments`), so a trace proves which codec it carried.

**Expected freeze** [INFERRED]: the air's waybeam restart (~3 s without frames, as for a mode switch) plus ~50–85 ms from the first new packet to the first decoded frame (item 4 above: 45–131 ms with a rebuild). The pilot sees about the same gap as for a mode switch.

**Tests** (host, WSL 22.04): `CodecSwitch` 6, `CodecSwitchKeyFrames` 3 (models the reset order on the real `KeyFrameFinder`), `H26XParser` 3; all 89 videonative gtests pass. `:app:videonative` builds, including `libVideoNative.so`. The release/re-create itself only runs on the device.

**Not covered:** a DVR recording across a switch. The MP4 writer is initialised once with the first codec (`VideoPlayer.cpp`, `mp4_h26x_write_init`), so the file breaks after a switch.

### Measuring H.264 vs H.265 (slot plan, for the menu's "+X ms")

The RTP timestamp base is random at every waybeam start (OpenIPC `00-H264-H265-timing.md` §2), and a codec switch is a waybeam restart. Capture → arrival therefore cannot be compared across a switch, not even inside one trace. The W3c per-segment method avoids it ([g2g-budget.md](g2g-budget.md#field-of-view-against-latency-480p167-vs-720p120-vs-1080p90-scaled-w3c-2026-09-27), [w3_budget.py](../../scripts/quest-latch/w3_budget.py)); the codec takes the place of the mode:

| Term | Source | Per codec? |
|---|---|---|
| capture, readout, ISP | same sensor mode for both codecs | cancels |
| encode, packetise + send (`s_air`) | air sidecar, per frame ([sidecar_log.py](../../scripts/quest-latch/sidecar_log.py)), 60 s per segment. `ready − capture` crosses clocks (RAW vs MONO), so only the **difference** within one air boot is valid | **yes** |
| spread on the radio | Quest trace, `transport_analyze.py` "frame packet spread" | yes (bytes per frame, same bitrate) |
| complete → decoded | Quest trace, `transport_analyze.py` "frame complete -> decoded frame ready"; MediaCodec part from logcat `Decoding:` in the segment output | **yes** (H.265 +0.1–0.3 ms on clean streams, table above) |
| decoded → latch, panel | compositor | cancels |

- **Order:** h264 → h265 → h265 → h264 (palindrome, N = 2) at one mode, all other air settings fixed, one air boot, O112 pin on. The encode was bimodal without the pin ([g2g-budget.md](g2g-budget.md)).
- **One segment:** the air switches the codec and runs the sidecar for 60 s. On the Quest, `NO_RESTART=1 mode_segment.sh h265_a`. `NO_RESTART` keeps the app, so the segment measures the decoder rebuilt by the live switch, the one the pilot will use. The output shows `live switch: codec changed to H.265`, and the `codec:` line from the trace confirms the payload type.
- **Budget:** `w3_budget.py air.tsv out/mode_h264_*.txt out/mode_h265_*.txt`. The air rows carry `mode = h264 / h265`, with the same `readout_ms`, `isp_lo`, `isp_hi` and `fov_h`/`fov_v` for both. The trade-off line then gives H.265's extra latency against H.264, the "+X ms" for the menu.
- **Which modes:** at least Race 480p167. Also Wide 1080p90 → 848×480 if the menu shows the cost per mode, since H.265 decode grows with resolution (table above). First check that H.265 holds 167 fps on the air. OpenIPC lists a general VENC fps cap regardless of codec (`00-H264-H265-timing.md` §3), and Race runs above it only on the patched `mi_venc`.

## GDR / no-IDR cold start (OpenIPC O118 S0, 2026-10-01): H.264 starts without an IDR, H.265 does not

The tests of openipc repo `repos/tasks/intra-refresh-slices-2026-09-29/R4-quest-decoder.md` (T1–T5), run on the Quest with the air off. [o118_s0.py](../../scripts/quest/o118_s0.py) replays the intra-refresh streams of `rtp_gen_gdr.sh` over Wi-Fi, one XR relaunch per run, APK 086a64aa, default levers. The `*_noidr.rtp` cuts start at an SPS before a non-IDR frame and hold **no IDR at all** (`rtp_gdr.py`: idr=0, SPS every 30 frames; 684/690 access units at 720p60, 990/1015 at 1080p90). The user's prefs were backed up and restored byte for byte. Data: [o118-s0-2026-10-01.txt](data/o118-s0-2026-10-01.txt).

| test | result | numbers [PROVEN: data file] | verdict |
|---|---|---|---|
| **T1 H.264** cold start without an IDR | outputs from the start | 666–683 of 684 frames (N=3, 720p60), 935 of 990 (1080p90); first output 25–51 ms after the decoder's configure (2–3 frames at 60 fps); 0 errors | **GO** |
| **T1 H.265** cold start without an IDR | **no output at all** | 0 frames in all 5 runs (720p60 × 3, 1080p90, `dec_component=c2.qti.hevc.decoder`); the control with an IDR (the full stream) decodes 671 | **NO-GO**: an H.265 join needs an IRAP (join-IDR, R4's fallback B3) |
| T1 H.264 with `c2.qti.avc.decoder` | starts, poorly | 150 frames, first output 101 ms | the default (OMX) component stays |
| T2 look of the unrefreshed band | not run | needs stills at frames k = 1…N+2; a screencap takes ~1 s, longer than a 0.5 s refresh cycle | open (a slow-mo through the lens or a decoder-side dump) |
| T3 heal time after loss | not run | needs stills compared with a PC decode at the same RTP ts | open |
| **T4** 4 slices, `au_aggregation` off / on | off: 4 outputs per frame; on: 1 | off 2664 outputs for 666 frames (the "broken frames" trap, confirmed at the output count; no stills); on 665 frames, decode 1.82 ms ≈ single-slice 1.5–1.9 | **PASS**: keep AU aggregation for multi-slice |
| **T5** rebuild into a GDR-only stream | H.265 (with IDR) → H.264 no-IDR: output 22–23 ms after the rebuild's configure | 1271–1272 frames for 671 + 684 sent: ~84 frames (~1.4 s) are lost around the switch (cause not investigated) | **PASS for H.264**; H.264 → H.265 no-IDR fails as T1 H.265 |

- **Consequence for the air's GDR (intra refresh) lever:** with H.264 the Quest can join and rebuild on a GDR-only stream with no IDR ever sent. With H.265 it cannot, and the app would need one IDR request per join/rebuild (R4 §B3). That costs one IDR per (re)start, not one per loss [INFERRED from T1].
- The first frames after a GDR-only start are damaged until one refresh cycle has passed (expected); their look is T2, still open.
