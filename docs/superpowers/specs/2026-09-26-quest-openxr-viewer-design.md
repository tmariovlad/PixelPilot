# PixelPilot XR: native OpenXR low-latency viewer for Meta Quest 2 — design

- **Date:** 2026-09-26 · **Branch:** `xr-native` (fork `tmariovlad/PixelPilot` of `OpenIPC/PixelPilot@3d6ca17`)
- **Status:** approved in brainstorming (sections 1–2 approved by the owner, then "continue autonomously")
- **Research basis:** `c:/xampp/htdocs/ev300d/tasks/quest2-research-2026-09-26/00-INDEX-SYNTHESIS.md`
  (esp. `02-apk-low-latency-options.md` §2–§4 and `01-latency-numbers-and-measurement.md` §protocol)

## 1. Goal and success criteria

**Goal:** show the OpenIPC FPV stream on a Quest 2 with the lowest achievable latency, by presenting the
MediaCodec output **directly on a compositor-owned Android surface** (`XR_KHR_android_surface_swapchain`)
shown as a **head-locked quad** at **120 Hz**, while reusing everything useful PixelPilot already has
(devourer userspace RTL8812AU driver, wfb-ng, RTP parser, MediaCodec low-latency keys #113, SurfaceView-class
direct output, bounded packet queue #120, decode-latency statistics).

**Success criteria**
1. `assembleDebug` builds; unit tests (JVM + host gtest) pass.
2. On a Quest 2: the XR activity shows live video from an RTL8812AU on USB-C, with a stats panel.
3. **Measured** (photodiode + OWON, protocol in research `01`): XR path is faster than PixelPilot 2D on the
   same stream. Every latency lever is switchable so each one's effect can be measured, and only
   levers that help are kept on by default afterwards.

**Non-goals (v1):** MAVLink OSD, DVR, audio, object detection, in-VR settings UI, stereo/3D video.

## 2. Architecture

```
PixelPilot 2D (VideoActivity, unchanged flow): channel/key/codec settings ──[menu "Launch XR"]──► XrVideoActivity
                                                                                                   │
 RTL8812AU ─USB─► WfbLinkManager (reused) ─► wfb-ng ─RTP 127.0.0.1:5600─► VideoPlayer (videonative + new levers)
                                                                                                   │ nativeSetVideoSurface(surface, 0)
 new module `app/xr` (C++, own thread): OpenXR instance/session                                    ▼
   • xrCreateSwapchainAndroidSurfaceKHR ──► video Surface ─────────────► AMediaCodec renders straight into it
   • 2nd android-surface swapchain ──► stats Surface ◄── XrStatsRenderer (Java Canvas, ~4 Hz)
   • every frame: xrEndFrame with 2 layers (video quad/cylinder + stats quad) in VIEW space
   • xrRequestDisplayRefreshRateFB(pref), XR_EXT_performance_settings SUSTAINED_HIGH, android thread hints
   • XR_META_performance_metrics (if present) → stats
```

### Units (one responsibility each)

| Unit | Kind | Responsibility |
|---|---|---|
| `app/xr` (`XrSession.cpp/.h`, `XrLayers.cpp/.h`, `xr_jni.cpp`) | new Gradle library module, C++ | OpenXR instance/session/frame loop; creates the 2 surface swapchains; submits layers; refresh rate; perf hints; metrics. Knows nothing about video decoding. |
| `XrBridge.java` (in `app/xr`) | new, Java | JNI façade: `start(activity, config)`, `getVideoSurface()`, `getStatsSurface()`, `setVideoSize(w,h)`, `getRuntimeInfo()`, `stop()`. |
| `XrVideoActivity.java` | new, app | Android lifecycle; wires WfbLinkManager + VideoPlayer + XrBridge + XrStatsRenderer. |
| `XrStatsRenderer.java` | new, app | Draws the stats panel onto the stats Surface with `lockCanvas`, ≤4 Hz. |
| `LayerLayout.java` (in `app/xr`) | new, pure Java | Pure math: video aspect + FOV pref (distance fixed at 2 m) → quad/cylinder size/pose + stats panel below. JVM-tested. *(Implementation note 2026-09-26: planned as `XrLayout` in `app`; moved next to its only consumer `XrBridge`.)* |
| `LatencyExperiments.java` | new, videonative (Java) | **Single source of truth** for every latency lever (pref keys, defaults, parsing). Read by 2D + XR + decoder. JVM-tested. |
| `LinkStatusListener` | new interface | Decouples `WfbLinkManager` from `ActivityVideoBinding` (it only used the binding for status text). 2D impl = today's `tvMessage`; XR impl = stats panel. |
| `DecoderLevers` (`helper/AndroidMediaFormatHelper.h` + `VideoDecoder`) | modified, C++ | New optional decoder keys / codec selection / AU aggregation, driven by `LatencyExperiments`. |
| `AccessUnitAssembler.h` | new, videonative C++, pure | Joins the NALUs of one access unit, closed by the RTP marker bit. Host gtest. |

### Changes to existing code (all default to today's behaviour)
- `ParseRTP.cpp` / `NALU.hpp`: carry the RTP **marker bit** of the packet that completed a NALU (`NALU::endOfAccessUnit`). Pure data propagation.
- `VideoDecoder`: when `au_aggregation` is on, feed whole access units (from `AccessUnitAssembler`) instead of single NALUs; new keys; optional `createCodecByName` for a `*.low_latency` component.
- `WfbLinkManager`: constructor takes `LinkStatusListener` instead of `ActivityVideoBinding`.
- `VideoActivity`: menu item **"Launch XR"** + submenu **"Latency experiments"** (checkable items bound to `LatencyExperiments`).
- `AndroidManifest.xml`: `XrVideoActivity` (`MAIN` + `org.khronos.openxr.intent.category.IMMERSIVE_HMD` + `com.oculus.intent.category.VR`, own task, no fixed orientation; USB broadcasts via the runtime receiver `WfbLinkManager.register()`, no manifest USB filter); `com.oculus.supportedDevices` meta-data; OpenXR runtime query/permission (`org.khronos.openxr.permission.OPENXR`, `<queries>` for the runtime broker).

## 3. Data flow, lifecycle, errors

**Per-frame critical path (no Java, no app render loop on it):**
RTL8812AU → devourer → wfb-ng (FEC) → RTP loopback :5600 → UdpReceiver → ParseRTP (+marker) → [NALU | AU] →
AMediaCodec (levers) → `releaseOutputBuffer(render=true)` immediately → compositor-owned Surface
(BufferQueue default = replace-latest; **no** `SYNCHRONOUS`, `USE_TIMESTAMPS` only as a lever) →
Horizon compositor latches at next 120 Hz vsync → VIEW-space layer → LCD → backlight strobe.
The OpenXR loop only re-submits the layers each frame.

**Startup order (strict):** OpenXR instance+session → swapchain Surfaces exist → `VideoPlayer.nativeSetVideoSurface(videoSurface,0)`
→ `VideoPlayer.start()` → VPN permission + `WfbNgVpnService` → `WfbLinkManager.startAdapters()`.

**Session states:** `READY` → `xrBeginSession`, run loop · `VISIBLE`/`FOCUSED` → attach the decoder to the surface ·
drop to `SYNCHRONIZED` or `STOPPING` → `VideoPlayer.stop()` and release the decoder surface **before** `xrEndSession`
(extension spec: writing to the surface outside VISIBLE/FOCUSED is undefined) · `EXITING`/`LOSS_PENDING` → finish activity.
*(Implementation note 2026-09-26: attach moved from READY to VISIBLE/FOCUSED after re-reading the extension spec.)*
`onPause`/`onDestroy` → stop adapters + service (as `VideoActivity`), then destroy swapchains/session/instance.

| Situation | Behaviour |
|---|---|
| `XR_KHR_android_surface_swapchain` missing or creation fails | Toast + finish back to 2D. **No silent fallback** to a slower path (would invalidate measurements). |
| Requested refresh not supported | Use the highest supported ≤ requested; show the actual value on the panel. |
| No adapter / no USB permission | Status via `LinkStatusListener` on the panel; retried on USB attach (existing receiver). |
| Stream resolution changes | `XrBridge.setLayout(LayerLayout.compute(...))` → `xrUpdateSwapchainFB` surface size on the XR thread (if `XR_FB_swapchain_update_state_android_surface`) + new layer aspect. |
| Image upside-down | `XR_FB_composition_layer_image_layout` VERTICAL_FLIP (negative-height trick is broken on current Horizon OS). |
| No video yet | Video quad black; panel shows "no video" + link state. |

## 4. Latency levers (experiments) — `LatencyExperiments` is the single source of truth

| Pref key | Values (default) | Where applied | Why (research ref) |
|---|---|---|---|
| `low_latency_decoder` (existing) | bool (**true**) | decoder keys | #113 |
| `xr_refresh_hz` | 72/80/90/120 (**120**; highest supported ≤ requested; Quest 2 needs 120 Hz enabled in Settings) | `xrRequestDisplayRefreshRateFB` | `02` §2.2 |
| `dec_picture_order` | bool (**false**) | `vendor.qti-ext-dec-picture-order.enable=1` | `02` §2.4 |
| `dec_operating_rate` | bool (**false**) | `operating-rate` = `Short.MAX_VALUE` (value choice to verify against Moonlight source during implementation; ALVR uses INT32_MAX) | `02` §2.4 |
| `dec_prefer_low_latency_component` | bool (**false**) | pick `c2.qti.{avc,hevc}.decoder.low_latency` if listed | `02` §2.4 |
| `au_aggregation` | bool (**false**) | one access unit per input buffer | `02` §2.4 |
| `xr_use_timestamps` | bool (**false**) | `XR_FB_android_surface_swapchain_create` `USE_TIMESTAMPS` | `02` §2.1 C |
| `xr_layer_shape` | quad/cylinder (**quad**) | layer type | `02` §2.2 |
| `xr_perf_sustained_high` | bool (**true**) | `XR_EXT_performance_settings` CPU+GPU | `02` §2.2 |
| `xr_fov_deg` | float (**60°**, clamped 20–110) | `LayerLayout` | comfort (distance fixed at 2 m; `xr_distance_m` dropped as unused) |
| `xr_flip_vertical` | bool (**true**) | `XR_FB_composition_layer_image_layout` | image orientation (CitraVR: surfaces arrive flipped) |

New decoder levers default **off** so the 2D app behaves exactly as upstream; they are switched on for A/B,
and flipped to on only after a measurement shows a gain. Decoder levers apply to 2D and XR alike
(same decoder), so 2D-vs-XR comparisons isolate the presentation path.

## 5. Testing and measurement

- **JVM unit tests** (`./gradlew test`): `LatencyExperiments` (defaults, parsing, unknown values), `LayerLayout`
  (aspect → size, cylinder angle, edge cases 0/odd sizes).
- **Host gtest** (existing `videonative/src/main/cpp/tests` CMake): `AccessUnitAssembler` (marker closes AU,
  config NALUs, lost marker → flush on next AU start, oversize guard).
- **Build gate:** `assembleDebug` + `lint` for all modules.
- **On-device smoke (needs Quest via ADB):** install, launch 2D → "Launch XR", verify: session FOCUSED,
  refresh == requested (`dumpsys`/panel), video visible, panel updates, clean exit/re-enter, USB re-attach.
- **Latency measurement (not automatable here):** research `01` §protocol — photodiode on the lens + OWON,
  test app GPIO/USB-serial toggle at frame release; matrix {2D, XR} × {72, 90, 120} × each decoder lever, N ≥ 25.
  (The ESP32/LDR rig does not work through HMD optics.)

## 6. Risks

- Horizon OS may treat a surface-swapchain layer differently from spec (CitraVR proves it works on current OS). Mitigation: smoke test first.
- `low-latency` / vendor keys may be ignored by the XR2 Codec2 HAL → levers measured, not assumed.
- Quest not currently connected → everything up to on-device smoke is verified by build + tests only.
