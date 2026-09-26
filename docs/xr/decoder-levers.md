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
