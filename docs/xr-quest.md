# Quest native XR mode (experimental)

A second activity, `XrVideoActivity`, shows the stream **inside an OpenXR session** instead of as a flat
2D panel. MediaCodec decodes straight into a compositor-owned Android surface
(`XR_KHR_android_surface_swapchain`) shown as a head-locked layer, so there is no app render pass and no
Android window compositing between the decoder and the headset compositor.

Design and reasoning: [spec](superpowers/specs/2026-09-26-quest-openxr-viewer-design.md) ·
[implementation plan](superpowers/plans/2026-09-26-quest-openxr-viewer.md).

> Status (2026-09-26): builds and passes its unit tests. **Not yet run on a headset** — nothing below about
> behaviour on Quest is verified until the smoke checklist has been done.

## Build and install

```bash
export JAVA_HOME='C:\Program Files\Java\jdk-17'      # JDK 17; newer JDKs break AGP 8.5
# local.properties: sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk   (forward slashes)
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Host unit tests for the decoder helpers (`AccessUnitAssembler`, `DecoderLevers`, `BufferedPacketQueue`)
need a Linux toolchain with CMake ≥ 3.14, e.g. WSL:

```bash
cmake -S app/videonative/src/main/cpp/tests -B /tmp/ppxr-tests && cmake --build /tmp/ppxr-tests -j8 \
  && (cd /tmp/ppxr-tests && ctest --output-on-failure)
```

JVM tests: `./gradlew :app:videonative:testDebugUnitTest :app:xr:testDebugUnitTest`.

## Use

1. Start PixelPilot normally once (2D) so the VPN permission and `gs.key` are in place.
2. Plug the RTL8812AU into the Quest's USB-C.
3. Menu → **Video → Launch XR (Quest)**. The 2D activity pauses (it releases the adapter), the XR
   activity takes it over.
4. Video appears as a head-locked screen with a stats panel below it. Leave with the Meta button.

Everything tunable lives in **Video → Latency experiments** (single source:
`app/videonative/.../LatencyExperiments.java`):

| Item | Pref key | Default | Applies |
|---|---|---|---|
| Decoder: decode order (qti) | `dec_picture_order` | off | app restart (2D and XR) |
| Decoder: max operating rate | `dec_operating_rate` | **on for Meta headsets**, off elsewhere | app restart |
| Decoder: low-latency component | `dec_prefer_low_latency_component` | off | app restart |
| Decoder: whole access units | `au_aggregation` | off | app restart |
| XR refresh | `xr_refresh_hz` | 120 | next XR start |
| XR size | `xr_fov_deg` | 60° | next XR start |
| XR: curved layer | `xr_layer_shape` | quad | next XR start |
| XR: present by timestamp | `xr_use_timestamps` | off | next XR start — **currently expected to be inert**: buffer timestamps are the decoder-input time, always ≤ the compositor's display time, so "latest buffer with timestamp ≤ display time" picks the same buffer as mailbox. Kept as a control; making it meaningful needs PTS = target display time (separate experiment). |
| XR: CPU/GPU sustained high | `xr_perf_sustained_high` | on | next XR start |
| XR: flip image vertically | `xr_flip_vertical` | on | next XR start |
| XR: schedule video threads as XR workers | `xr_thread_hints` | on | next XR start — registers the UDP/UDS receive-and-feed threads and the decoder output thread with `xrSetAndroidApplicationThreadKHR` (renderer worker). wfb-ng's own RX/FEC threads are not covered yet. |

The existing **Low latency** item (`low_latency_decoder`, default on) is unchanged.
A decoder that rejects the extra decoder keys is reconfigured with the base set; the stats panel line
`dec:` shows the codec name and the levers it actually accepted.

## Smoke checklist (first run on a headset)

`adb logcat -s PixelPilotXr pixelpilot-xr pixelpilot`:

- [ ] `OpenXR ready: N extensions enabled` — if instead `OpenXR runtime lacks XR_KHR_android_surface_swapchain`, the XR mode cannot work on this runtime.
- [ ] `requested 120 Hz -> 120 Hz` and the panel's first line shows `XR 120.0 Hz`. On Quest 2, 120 Hz must be enabled under Settings → System → Display; otherwise the runtime offers at most 90 and the log shows `-> 90 Hz`.
- [ ] `session state … -> 5` (FOCUSED) followed by `video attached to the compositor surface`.
- [ ] Video visible, **right way up** (if upside-down or mirrored: toggle *XR: flip image vertically*).
- [ ] Stats panel updates (~4 Hz), `dec:` line shows a codec name.
- [ ] Meta button → `video detached` before the session ends; back in → `video attached` again.
- [ ] Unplug / replug the adapter: panel shows the link status, video resumes.
- [ ] Exit and relaunch from the 2D menu twice (no crash, no "already started").

## Measuring (the point of this mode)

The ESP32 + LDR G2G rig does **not** work through HMD optics (the backlight flashes ~1 ms per frame).
Use a fast photodiode (BPW34 / OPT101) at the lens + scope, or native 480 fps slow motion. Protocol and
background: `c:/xampp/htdocs/ev300d/tasks/quest2-research-2026-09-26/01-latency-numbers-and-measurement.md`.

Matrix, same air unit and stream, N ≥ 25 per point, order shuffled:

- presentation: PixelPilot 2D vs XR
- refresh: 72 / 90 / 120 Hz (XR)
- each decoder lever on/off (one at a time, then the combination of the ones that helped)
- `xr_use_timestamps` on/off

Keep a lever's default on only after a measurement shows it helps; record results next to this file.

## First on-device results (Quest 2, 2026-09-26, Horizon OS build UP1A.231005.007.A1)

Stream: recorded x265 RTP (720p) replayed over **Wi-Fi** from a PC to `udp://<quest>:5600` (no RTL8812AU), debug build `com.openipc.pixelpilot.xr` installed next to the user's release PixelPilot 0.21.0.

- XR path works: `OpenXR ready: 12 extensions`, session reaches FOCUSED, `requested 120 Hz -> 120 Hz (result 0)`, video attached to the compositor surface, frames decoded [PROVEN: logcat].
- Decoder on Quest 2 = `OMX.qcom.video.decoder.hevc`; no `c2.qti.*.low_latency` component exists (the LLC lever falls back to the default).
- **Decoder levers, steady-state decode time (queue → output release), N = 3 shuffled rounds, ~425 decoded frames each** (raw: [measurements-2026-09-26-quest2-decoder-levers.csv](measurements-2026-09-26-quest2-decoder-levers.csv)):

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

### Which low-latency key slows the Quest 2 decoder? (key isolation, 2026-09-26)

Same stream and method as above, one key at a time via `dec_debug_key_mask`; every run printed the keys the
decoder was really configured with (read back from the `Configuring decoder` log line). N = 3 shuffled rounds
(raw: [measurements-2026-09-26-quest2-key-isolation.csv](measurements-2026-09-26-quest2-key-isolation.csv)):

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

### Clean-stream recheck: LL keys + operating rate is fastest (2026-09-26)

These streams arrive almost whole (~670 of 720 frames decoded per 12 s run), unlike the 1-slice stream above. The 720p/1080p test streams are single-slice x264/x265 at 60 fps. N = 3 shuffled rounds per stream, and every run's applied keys were checked. Raw data: [measurements-2026-09-26-quest2-lever-recheck.csv](measurements-2026-09-26-quest2-lever-recheck.csv). The CSV has no per-run rows for H.265 720p; only its summary was kept.

| Config | H.264 720p | H.265 720p | H.265 1080p |
|---|---|---|---|
| no keys | 1.96 (1.93–1.99) | 2.34 (2.18–2.63) | 3.57 (3.37–3.92) |
| LL (upstream) | 2.01 (1.95–2.11) | 2.31 (2.28–2.35) | 3.31 (3.21–3.47) |
| OR only (previous Quest default) | 1.88 (1.80–1.99) | 1.95 (1.92–1.97) | 2.59 (2.49–2.74) |
| **LL + OR (new default)** | **1.56 (1.51–1.61)** | **1.79 (1.78–1.79)** | **2.32 (2.10–2.43)** |

- LL + OR is the fastest configuration on all three streams, and its frame counts match the other configs, so no frames are held back [PROVEN: the CSV plus the per-run `Configuring decoder` log lines]. The gain over OR-only is 0.16–0.32 ms. That is small, but the ranges barely overlap on any stream.
- The earlier "LL adds 1.2 ms" result came from a stream that was missing most of its packets. The decoder behaves differently on such a stream (concealment and many incomplete frames) [INFERRED]. That result does not describe a real link.
- Verified on the device after the change, with empty prefs: keys `LL+vLL+qti+hisi+rtc+OR` → 1.57 / 1.72 / 2.24 ms (H.264 720p / H.265 720p / H.265 1080p), with 0 errors [PROVEN: logcat, 2026-09-26].

### Codec, component and resolution (2026-09-26)

Setup: OR-only defaults at the time, 12 s single-slice streams, N = 3 shuffled rounds. Every run's component and keys were checked. Raw data: [measurements-2026-09-26-quest2-codecs.csv](measurements-2026-09-26-quest2-codecs.csv).

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

## Open questions (to settle on the device)

- Does the Horizon compositor treat the surface swapchain as replace-latest (mailbox) when
  `USE_TIMESTAMPS` is off, as the spec implies?
- Is the Android surface image upside-down without the vertical flip on current Horizon OS (CitraVR says yes)?
- Does the XR2 expose `c2.qti.{avc,hevc}.decoder.low_latency`, and does its Codec2 HAL honour
  `vendor.qti-ext-dec-picture-order.enable`? (The `dec:` line shows which component was created.)
- Do the Meta performance-metric paths return values on Quest 2 (`n/a` on the panel means no)?
