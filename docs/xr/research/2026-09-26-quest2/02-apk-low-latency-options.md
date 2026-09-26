# Quest 2 FPV viewer — lowest-latency APK options (OpenIPC → wfb-ng → devourer → MediaCodec)

> **Date:** 2026-09-26 · **Scope:** research only (no device on hand — no Quest was attached to ADB during this
> work, so **no number below was measured by me on a Quest**). Primary sources = Khronos OpenXR spec sources,
> Meta docs/SDK, and the source code of PixelPilot, PixelPilot_quest, FPVue_xr, ALVR, WiVRn, Moonlight, CitraVR.
> **Target:** 20 ms glass-to-glass (G2G) total. **Device:** Meta Quest 2 (Snapdragon XR2, fast-switch LCD).
>
> Tags: `[PROVEN: source]` = read in the spec/doc/code · `[INFERRED: from …]` = deduced from proven facts ·
> `[SPECULATION]` = hypothesis; says what would confirm it.

> ⚠️ **CORRECTION 2026-09-26 (orchestrator):** the ESP32+LDR G2G rig does **NOT** work through goggle/HMD optics (`maxIntensity=0` behind the lenses) [PROVEN: `C:/xampp/htdocs/openipc-low-latency-and-others-video/.claude/skills/display-mode/SKILL.md` §notes]. Wherever this report says "ESP32 G2G rig", use instead: a fast photodiode (BPW34/OPT101) at the Quest lens + OWON VDS1022I, or the 480 fps native slow-mo. See [01-latency-numbers-and-measurement.md](01-latency-numbers-and-measurement.md) for the protocol.

## Sources collected locally (all shallow clones / raw fetches)

| Local path | What | Revision |
|---|---|---|
| `C:/xampp/htdocs/pixelpilot-xr/repos/PixelPilot` | OpenIPC/PixelPilot | `3d6ca17` (2026-09-02) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/PixelPilot_quest` | gpratas-pereira/PixelPilot_quest (native OpenXR fork) | `e605749` (2025-11-05) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/FPVue_xr` | gehee/FPVue_xr (StereoKit/OpenXR prototype) | `c0ccfba` (2024-05-05) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/ALVR` | alvr-org/ALVR | `99d8948` (2026-09-24) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/LiveVideo10ms` | Consti10/LiveVideo10ms | `f1b148a` (2023-04-02) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/Meta-OpenXR-SDK` | meta-quest/Meta-OpenXR-SDK | `bbed2f2` (2026-02-12) |
| `C:/xampp/htdocs/pixelpilot-xr/repos/OpenXR-SDK-Source` | KhronosGroup/OpenXR-SDK-Source (registry `xr.xml`) | shallow HEAD |
| `C:/xampp/htdocs/pixelpilot-xr/repos/openxr-spec-snippets/*.adoc` | raw spec chapters from KhronosGroup/OpenXR-Docs `main` (not a clone; curl of individual `.adoc` files) | 2026-09-26 |
| scratchpad (session temp) | CitraVR `GameSurfaceLayer.cpp`/`Common.h`, WiVRn `android_decoder.cpp`, Moonlight `MediaCodecHelper.java`, Qualcomm `omx_vdec_extensions.hpp` (msm8998) — fetched via `gh api` / googlesource | 2026-09-26 |

> Path note (2026-09-26): these clones were moved from `c:/xampp/htdocs/ev300d/repos/` to `C:/xampp/htdocs/pixelpilot-xr/repos/` (git-ignored). The `PixelPilot` and `LiveVideo10ms` clones were deleted afterwards; their URL + commit are recorded in `C:/xampp/htdocs/pixelpilot-xr/repos/REMOVED-CLONES.txt`.

---

## 0. TL;DR

1. **PixelPilot today is a plain 2D Android app** — no OpenXR code at all; video goes MediaCodec → `SurfaceView`
   → Android SurfaceFlinger → Horizon OS 2D-panel system → VR compositor → display.
   `[PROVEN: grep for openxr/xrCreate/com.oculus in PixelPilot/app = 0 hits; VideoActivity.java:407-433;
   activity_video.xml:8; manifest has no com.oculus.intent.category.VR]`
2. **The shortest presentation path Horizon OS offers to an app** is a **native OpenXR app** that creates an
   **Android Surface swapchain** (`XR_KHR_android_surface_swapchain`), hands that `Surface` straight to
   `AMediaCodec_configure()`, and submits it every frame as a **head-locked quad layer in `VIEW` space**, at
   **120 Hz** (`xrRequestDisplayRefreshRateFB`). The decoder writes into a BufferQueue owned by the compositor; in the
   default (non-synchronous) mode the queue **always replaces the last buffer**, so the compositor latches the
   newest decoded frame at composition time — no app GPU pass, no SurfaceFlinger pass, no panel-shell pass.
   `[PROVEN: khr_android_surface_swapchain.adoc:23-24,54-71; fb_android_surface_swapchain_create.adoc:38-46]`
3. **Estimated Quest-side latency** (last video packet in → photons), before any measurement:
   **~14–26 ms (≈20 ms mean) at 120 Hz for the surface-swapchain path**, vs **~29 ms mean for a native app that
   samples a SurfaceTexture/ImageReader and re-renders (PixelPilot_quest / ALVR style)**, vs **~40–70 ms for the
   2D-panel path (PixelPilot)**. The 2D-panel figure is the weakest estimate (`[SPECULATION]`, Horizon's panel
   internals are not documented). See §3.
4. **Consequence for the 20 ms G2G target:** even the best Quest 2 path spends ~15–20 ms *inside the headset*
   (decode + wait for compositor latch + LCD scanout + backlight strobe), leaving ~0–5 ms for sensor readout,
   ISP, encode and the air link. **20 ms total G2G is not reachable on a Quest 2** `[INFERRED: §3 budget]`; a
   realistic Quest 2 floor is ~30 ms total. The Quest is still worth a native app because it plausibly removes
   **~15–45 ms** versus PixelPilot's 2D panel `[SPECULATION until A/B measured with the G2G rig]`.
5. **Effort:** the smallest route is to modify **PixelPilot_quest** (already native OpenXR + PixelPilot's
   `videonative` + `wfbngrtl8812` modules): replace its `SurfaceTexture` + eye-buffer rendering with
   `xrCreateSwapchainAndroidSurfaceKHR` + a `VIEW`-space quad + 120 Hz request. That is a change of ~150–300 lines of
   C++ `[INFERRED: from openxr_app.cpp:1338-1500, 2898-2942]`. A clean-room minimal viewer on current upstream
   PixelPilot modules is ~1–2 kLOC and ~3–6 days `[SPECULATION]`. The Windows toolchain is already installed
   (Android Studio, NDK 26.1.10909125, CMake 3.22.1) `[PROVEN: ls Android/Sdk/ndk, /cmake]`.

---

## 1. Existing apps — what each one actually does

### 1.1 PixelPilot (OpenIPC) — 2D panel, MediaCodec → SurfaceView

- **Architecture:** devourer (userspace RTL8812AU) → wfb-ng aggregator → **RTP over loopback UDP 127.0.0.1:5600**
  → `UdpReceiver` → NALU parser → `AMediaCodec`. `[PROVEN: PixelPilot/app/wfbngrtl8812/src/main/cpp/WfbngLink.cpp:59,67;
  videonative/src/main/cpp/VideoPlayer.cpp:164]`
- **Presentation:** decoder configured with an `ANativeWindow` from a Java `Surface`
  (`ANativeWindow_fromSurface`, `AMediaCodec_configure(codec, format, window, …)`), output released with
  `AMediaCodec_releaseOutputBuffer(codec, index, true)` immediately on dequeue.
  `[PROVEN: VideoDecoder.cpp:65, :154, :283]` The Surface comes from a **`SurfaceView`** (default) or a
  **`TextureView`** (only when object detection is on — the code comment itself says it costs "a GPU composition
  pass and an extra frame of latency"). `[PROVEN: VideoActivity.java:407-433; activity_video.xml:8-29]`
  PixelPilot's "VR mode" is **two side-by-side SurfaceViews with two decoders** (Cardboard-style SBS), not OpenXR.
  `[PROVEN: VideoActivity.java:398-403; VideoDecoder.cpp:120-125 feeds idx 0 and 1]`
- **Decoder tuning (already good):** `low-latency=1`, `vendor.low-latency.enable=1`,
  `vendor.qti-ext-dec-low-latency.enable=1`, hisi/rtc vendor keys, `priority=0`, user-switchable.
  `[PROVEN: helper/AndroidMediaFormatHelper.h:9-22; VideoDecoder.h:89,116]`
  **Missing vs. other low-latency players:** `vendor.qti-ext-dec-picture-order.enable=1` (Moonlight sets it),
  `operating-rate` (ALVR sets `INT32_MAX`), explicit selection of a `*.low_latency` codec component, and
  AU-level input (it queues **one NALU per input buffer** with flag 0 / CODEC_CONFIG, no
  `BUFFER_FLAG_PARTIAL_FRAME`). `[PROVEN: VideoDecoder.cpp:208-232]` — see §2.4.
- **Output thread:** blocking `dequeueOutputBuffer` with 17 ms timeout at nice −16; returns as soon as a frame is
  ready, so polling adds ~0. `[PROVEN: VideoDecoder.h:138; VideoDecoder.cpp:266-283]`
- **Built-in decode-latency stat:** `decodingTime = now − presentationTimeUs`, where PTS = steady-clock time the
  NALU was queued → usable on a Quest to measure the decode term directly. `[PROVEN: VideoDecoder.cpp:231-233, 285-288]`
- **Packet reorder queue** bounded to 20 ms age / 15 packets (commit #120, 2026-09-02).
  `[PROVEN: BufferedPacketQueue.h:10-30]` (Only costs latency on a sequence gap.)
- **On Quest:** runs as a flat 2D panel ("non vr mode"). `[PROVEN: PixelPilot/README.md:28, :137-138]`
- **Latency data on Quest:** none published. `[PROVEN: absence — no Quest G2G figure in README/issues searched]`

### 1.2 PixelPilot_quest (gpratas-pereira) — native OpenXR, but eye-buffer path

- A PixelPilot fork (last push 2025-11-05) that adds an `OpenXrNativeActivity` + `app/xr` native module.
  `[PROVEN: gh forks listing; PixelPilot_quest/app/src/main/java/com/openipc/pixelpilot/OpenXrNativeActivity.java]`
- Video path: **`SurfaceTexture` → `GL_TEXTURE_EXTERNAL_OES`** → `updateTexImage()` inside the XR render loop →
  app renders the video into **projection-layer eye swapchains** in **`LOCAL` (world-locked) space**, plus
  UI/overhead quad layers. `[PROVEN: app/xr/src/main/cpp/openxr_app.cpp:1217-1228, 1338-1420, 1500 (videoPlayer.addAndStart(surface)),
  2041 (updateTexImage), 2560 (LOCAL), 2898-2942 (projection layer)]`
- Enables `XR_FB_display_refresh_rate` but **never calls `xrRequestDisplayRefreshRateFB`** → runs at the
  runtime default. `[PROVEN: openxr_app.cpp:2258-2271; grep "RequestDisplayRefreshRate" = 0 hits]`
- Also carries unrelated baggage (Node.js "rewards" backend, Meta Spatial SDK activity). `[PROVEN: CLAUDE.md:8-11, 80-90]`
- **Why it matters:** it is the closest existing codebase to the optimal design — the decoder already receives a
  `jobject Surface` from native code, so swapping the SurfaceTexture Surface for a surface-swapchain Surface is local.

### 1.3 FPVue_xr (gehee) — native OpenXR via StereoKit, CPU copy path (worst of the native options)

- Decoder is configured **without a surface** (`AMediaCodec_configure(codec, format, nullptr, …)`), output read back
  with `AMediaCodec_getOutputBuffer`, converted **NV21→BGR→RGBA with OpenCV on the CPU**, uploaded with
  `tex_set_colors` each StereoKit frame and drawn on a world-space plane mesh.
  `[PROVEN: FPVue_xr/app/src/main/cpp/videonative/VideoDecoder.cpp:129,217-229; app.cpp:52-64,176-180]`
- Channel hard-coded 149, "only intended for developers"; last upstream commit 2024-05-05; forks
  (vertexodessa 2024-10, carabidulebabat/fpvuexrcara 2025-02) add channel selector / DVR, not a new video path.
  `[PROVEN: README.md; app.cpp:109; gh commits of forks]`

### 1.4 Consti10 FPV-VR / LiveVideo10ms — "SuperSync" front-buffer rendering

- LiveVideo10ms (the decoder PixelPilot's `videonative` descends from) reports 8–11.5 ms "avgTotalDecodingTime" on
  2018-era phones. `[PROVEN: LiveVideo10ms/README.md:8-18]`
- FPV-VR measured ~130 ms G2G on an old phone and notes SurfaceFlinger can add up to ~3 display frames; its low
  latency came from **its own front-buffer renderer with vertex-displacement distortion** ("SuperSync", in RenderingX)
  because Daydream's async-reprojection path had no video-texture support.
  `[PROVEN: github.com/Consti10/FPV_VR README; github.com/Consti10/RenderingX feature list]`
- **Does not apply on Quest.** An OpenXR app never owns the display surface: it submits layers via `xrEndFrame`, and
  the runtime compositor produces the displayed image. `[PROVEN: OpenXR rendering chapter — frame submission via
  xrWaitFrame/xrBeginFrame/xrEndFrame, rendering.adoc:768-800,1095-1102]` There is no OpenXR or Meta extension
  for front-buffer / scanline racing (`grep -i "latency|front_buffer" xr.xml` → no such extension).
  `[PROVEN: OpenXR-SDK-Source/specification/registry/xr.xml]` Even if there were, on the Quest 2 LCD the backlight
  is strobed for a fraction of the frame **after** the liquid crystal settles, so racing the scanline would not bring
  photons earlier. `[INFERRED: fast-switch LCD with backlight strobing — uploadvr.com/quest-2-lcd-display-detailed-specs
  (Meta, Display Week 2022)]`

### 1.5 Other OpenXR video clients used as references

| App | Decode → present | Relevance |
|---|---|---|
| **ALVR** client (Quest) | MediaCodec → `AImageReader` (PRIVATE, GPU_SAMPLED, up to 10 images) → AHardwareBuffer → GLES re-render into **projection-layer** swapchains in `STAGE` space, with the PC render pose; frame queue capped by `max_buffering_frames=2`. Default MediaCodec keys: `operating-rate=INT32_MAX`, `priority=0`, `vendor.qti-ext-dec-low-latency.enable=1`; `low-latency` left commented ("Quest 1 and 2 might not be capable"). `[PROVEN: ALVR/alvr/client_core/src/video_decoder/android.rs:95-140,245-300,360-400; session/src/settings.rs:1725-1726,1853-1876; client_openxr/src/stream.rs:378-520]` | Shows the tuned **app-renders-video** path; it needs that path because it reprojects with the PC pose and un-warps foveated encoding — an FPV feed needs neither. Its stats explicitly say the vsync-queue term "cannot be measured by ALVR and should be reported by the VR runtime". `[PROVEN: client_core/src/statistics.rs:89-91]` |
| **WiVRn** client | MediaCodec → `AImageReader` + `acquireLatestImage` → Vulkan; `operating-rate=fps`, `priority=0`; the qti low-latency key is commented out. `[PROVEN: WiVRn client/decoder/android/android_decoder.cpp:119-150,291]` | Same class as ALVR. |
| **CitraVR** (3DS emulator on Quest) | Emulator renders into a **surface created by `xrCreateSwapchainAndroidSurfaceKHR`**, shown as quad/cylinder layers; uses `XR_FB_composition_layer_image_layout` VERTICAL_FLIP because "the out-of-spec negative size.height trick … newer Horizon OS compositors render as nothing". `[PROVEN: CitraVR GameSurfaceLayer.cpp:335-360,515-545; utils/Common.h:52-56]` | **Working, current Quest reference for the surface-swapchain + quad path**, including a real-world gotcha. |
| **Wolvic** browser, **Godot 4.4+** `OpenXRCompositionLayer(use_android_surface)` | Both create Android-surface swapchains for video. `[PROVEN: gh code search hits Igalia/wolvic app/src/openxr/cpp/OpenXRSwapChain.cpp; godotengine/godot modules/openxr/extensions/openxr_composition_layer_extension.cpp; GodotVR/godot_openxr_vendors fb_android_surface_swapchain_create]` | More references. |
| **Meta Unity `OVROverlay` "Is External Surface"** | "feed external video directly into the compositor"; Meta's *Independence* sample renders to the surface from a Java thread and "the compositor layer continues animating smoothly … even when the main application drops frames". `[PROVEN: developers.meta.com/horizon/documentation/unity/unity-ovroverlay/ ; …/unity-sample-compositor-layers/]` | **Proves the compositor latches surface-layer content independently of the app's frame loop.** |
| **Moonlight-android**, **QOpenHD** | Plain 2D Android apps on Quest (same path class as PixelPilot). QOpenHD "works with Quest 2 but only in 2D mode" (issue #299, 2022, no maintainer answer). `[PROVEN: github.com/OpenHD/QOpenHD/issues/299]` | No VR path; Moonlight's decoder-key logic is a useful reference (§2.4). |
| **Virtual Desktop** | Closed source; no primary documentation of its decode→compositor path found. `[SPECULATION: nothing verifiable]` | — |

**Search result:** no OpenIPC/wfb-ng **native OpenXR app with a surface-swapchain video layer** exists on GitHub as of
2026-09-26 (searched repo names/descriptions, PixelPilot forks list, FPVue_xr forks, code search for
`xrCreateSwapchainAndroidSurfaceKHR` + wfb/devourer). `[PROVEN: gh search/forks queries, 0 matches]` The two native
attempts are FPVue_xr (CPU copy) and PixelPilot_quest (SurfaceTexture + eye buffer).

---

## 2. Design of the optimal APK on Horizon OS

### 2.1 Presentation paths compared (what happens to one decoded frame)

**A — 2D panel app (PixelPilot).**
`MediaCodec` → SurfaceView BufferQueue → **SurfaceFlinger** latches at its vsync and composites the app window →
**Horizon 2D-panel system** consumes that output and draws it as a panel → **VR compositor** → LCD.
- The first two hops are standard Android `[PROVEN: VideoDecoder.cpp:154,283 + AOSP SurfaceView semantics]`.
- The hand-off from SurfaceFlinger to the VR compositor is **undocumented by Meta** (I found no primary doc of whether a
  2D panel is drawn by a shell app into its eye buffers or submitted as its own compositor layer, nor at what rate
  the panel's virtual display runs). `[PROVEN: absence in Meta android-apps docs fetched]` At minimum it adds one
  SurfaceFlinger latch + composition, and the "hardware overlay plane" benefit that PixelPilot's comment claims for
  phones does not exist, because the output is not a physical display. `[INFERRED: VideoActivity.java:413-415 comment
  is about phone HWC; on Quest the panel is shown inside a VR scene composited by the VR compositor]`

**B — native OpenXR, app samples video and re-renders (PixelPilot_quest, ALVR, WiVRn, FPVue_xr).**
`MediaCodec` → SurfaceTexture/ImageReader owned by the app → app's frame loop (`xrWaitFrame` → `updateTexImage` →
GPU draw into swapchain) → `xrEndFrame` with `displayTime = predictedDisplayTime` → compositor (reprojection) → LCD.
The frame waits for the *app's* next loop iteration, then for the app frame to be displayed (Phase Sync makes the
app finish "right before our compositor needs the completed frame"), i.e. roughly one extra app frame versus C.
`[PROVEN: Phase Sync = default OpenXR frame timing — developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/
(2020-12-07); INFERRED: extra ≈1 frame from the loop structure in openxr_app.cpp:2729-2942 and ALVR stream.rs:378-520]`
World-locked layers (LOCAL/STAGE) are also reprojected against head motion, which for FPV makes the image "swim"
relative to the head instead of staying fixed like goggles. `[INFERRED: spaces.adoc:175-179 + rendering.adoc:1335-1341]`

**C — native OpenXR, Android Surface swapchain + head-locked quad (recommended).**
`xrCreateSwapchainAndroidSurfaceKHR` returns an `XrSwapchain` **and** a `jobject Surface`; the Surface "must be valid
to be used with ordinary Android APIs for submitting images", and the swapchain "must be valid to be referenced in
XrSwapchainSubImage structures to show content on the screen". The app may **not** acquire/wait/release images of
this swapchain — only destroy it. `[PROVEN: khr_android_surface_swapchain.adoc:54-71]`
→ pass the Surface to `ANativeWindow_fromSurface` → `AMediaCodec_configure(…, window, …)` exactly as PixelPilot
does today. Every app frame, submit an `XrCompositionLayerQuad` whose `space` is a `VIEW` reference space
("rendering small head-locked content such as a reticle … will stay at a fixed point on head-mounted displays";
for head-locked content "the VIEW reference space would provide the highest quality layer reprojection").
`[PROVEN: spaces.adoc:169-179; rendering.adoc:1339-1341]`
- **Default BufferQueue mode = replace-latest (mailbox).** The SYNCHRONOUS flag exists to make the queue *keep*
  multiple buffers "instead of always replacing the last buffer", i.e. the default replaces. **Do not set it.**
  `[PROVEN: fb_android_surface_swapchain_create.adoc:38-42]`
- **USE_TIMESTAMPS** makes the compositor pick "the most recent buffer whose presentation timestamp is not greater than
  the expected display time" — a smoothness tool; for FPV leave it off (or use it only if judder is unacceptable).
  `[PROVEN: fb_android_surface_swapchain_create.adoc:43-46]`
- Compositor samples the surface **independently of the app frame rate** (Meta *Independence* sample). `[PROVEN:
  unity-sample-compositor-layers doc]` → the app loop only has to keep resubmitting the layer; its own timing
  (Phase Sync) no longer sits on the video path.
- No app GPU copy and a single resample by the compositor (compositor layers are the documented route for sharp
  video/text). `[PROVEN: Meta compositor-layers docs (search result excerpt "Compositor layers are much sharper against an
  eye-buffer layer"); INFERRED: zero-copy because the producer is the decoder and the consumer is the compositor]`

### 2.2 OpenXR / Meta features — what helps, what does not

| Feature | Use it? | Evidence |
|---|---|---|
| `XR_KHR_android_surface_swapchain` | **Yes — core of the design.** Create with `format/sampleCount/faceCount/arraySize/mipCount = 0`; size is producer-controlled. | `[PROVEN: khr_android_surface_swapchain.adoc:60-65,85-93]` |
| `XR_FB_android_surface_swapchain_create` | Only to explicitly pass flags = 0; never SYNCHRONOUS. | `[PROVEN: fb_android_surface_swapchain_create.adoc:38-46,80-85]` |
| `XR_FB_swapchain_update_state_android_surface` | Yes, to set/query the surface dimensions when the stream resolution changes (keeps `imageRect` correct). | `[PROVEN: fb_swapchain_update_state_android_surface.adoc overview]` |
| `XR_FB_composition_layer_image_layout` (VERTICAL_FLIP) | **Yes if the image is upside-down** — negative height no longer works on current Horizon OS. | `[PROVEN: CitraVR utils/Common.h:52-56]` |
| `XR_FB_display_refresh_rate` → `xrRequestDisplayRefreshRateFB(120.0f)` | **Yes — biggest single lever on the display term.** Quest 2 supports 72/80/90/96/100/120 Hz (60 Hz media apps only); request the exact value, don't index. | `[PROVEN: developers.meta.com/horizon/documentation/unity/unity-set-disp-freq/; fb_display_refresh_rate.adoc overview]` |
| Phase Sync | Automatic in OpenXR; irrelevant for path C (video bypasses the app loop). | `[PROVEN: Phase Sync blog 2020-12-07]` |
| Late latching | **Not applicable.** It re-writes pose uniforms before GPU use, needs Vulkan + multiview; a head-locked video layer has no pose-dependent rendering. | `[PROVEN: developers.meta.com/horizon/documentation/unreal/unreal-late-latching/ (search excerpt)]` |
| `XR_FB_composition_layer_settings` | Only quality (super-sampling / sharpening flags); adds compositor GPU work, no latency benefit. Optional, test cost. | `[PROVEN: fb_composition_layer_settings.adoc: "processing options such as sharpening or super-sampling"]` |
| `XR_KHR_composition_layer_cylinder` | Alternative to quad for large FOV (less edge distortion); same latency class. | `[PROVEN: xr.xml]` |
| `XR_EXT_performance_settings`, `XR_KHR_android_thread_settings` | Yes: CPU/GPU `SUSTAINED_HIGH`, mark decoder-feed/output threads as real-time-ish. Used by Meta's own sample. | `[PROVEN: Meta-OpenXR-SDK XrCompositor_NativeActivity.c:2362-2411]` |
| `XR_META_performance_metrics` | Yes for instrumentation (`/perfmetrics_meta/compositor/gpu_frametime`, `dropped_frame_count`, `app/motion_to_photon_latency`). | `[PROVEN: meta_performance_metrics.adoc:20-37]` |
| Any "low-latency video layer" / front-buffer extension | **Does not exist** in the OpenXR registry (999 extensions). | `[PROVEN: grep xr.xml]` |
| `XR_FB_space_warp` | No (synthesises frames for the app's eye buffers; irrelevant to a surface layer). | `[INFERRED: extension purpose]` |

### 2.3 Frame timing: latency vs judder

- With a mailbox surface layer, the latency of a frame = decode + wait until the compositor's next latch (uniform
  0…T, T = refresh period) + compositor-to-photon. `[INFERRED: §2.1 C]`
- Camera fps ≠ display Hz (or same nominal rate but independent clocks) → the latch phase drifts: latency saws between
  min and min+T and occasionally a frame is shown twice or dropped. Matching nominal rates (air unit 120 fps ↔ Quest
  120 Hz) minimises visible judder; the latency distribution stays U(0,T). `[INFERRED]`
- `USE_TIMESTAMPS` + PTS = arrival + fixed offset would regularise presentation at the cost of that offset — the
  opposite of what FPV wants; keep it as an A/B option only. PixelPilot's PTS already come from `steady_clock`
  (CLOCK_MONOTONIC, same base as XrTime on Android) so it would be a small change. `[PROVEN: VideoDecoder.cpp:231-233;
  INFERRED: XrTime↔CLOCK_MONOTONIC via XR_KHR_convert_timespec_time]`
- `releaseOutputBuffer(index, true)` immediately on dequeue (what PixelPilot does) is correct for a mailbox layer;
  `releaseOutputBufferAtTime` only matters with USE_TIMESTAMPS. `[INFERRED]`

### 2.4 MediaCodec low-latency settings (decoder term)

| Setting | Status in PixelPilot | Evidence / note |
|---|---|---|
| `KEY_LOW_LATENCY` (`"low-latency"`, API 30+): decoder "must return decoded frames as soon as possible … without waiting for further input" | set | `[PROVEN: source.android.com/docs/core/media/low-latency-media; AndroidMediaFormatHelper.h:14]`. Quest 2 now runs an Android 12L+/14 base (API ≥ 32) so the key is accepted by the framework; whether the XR2 codec honours it is unverified. `[PROVEN: Wikipedia Quest 2 — Android 10 → 12L target API 32 → Android 14 "Meta Horizon OS 2"; SPECULATION: codec support]` |
| `vendor.qti-ext-dec-low-latency.enable=1` | set | Also ALVR's default on Quest `[PROVEN: settings.rs:1873-1875]` |
| `vendor.qti-ext-dec-picture-order.enable=1` → **decode-order output** (`QOMX_VIDEO_DECODE_ORDER`) | **missing** | `[PROVEN: hardware/qcom/media msm8998 omx_vdec_extensions.hpp:34,111-112; Moonlight MediaCodecHelper.java:558-565 sets it together with low-latency]`. OpenIPC streams are I/P only, so decode order = display order and this removes any DPB/reorder hold. XR2 uses Codec2 (`c2.qti.*`); whether the C2 HAL maps this key is `[SPECULATION]` — check `getSupportedVendorParameters()` / logcat. |
| `operating-rate` (`INT32_MAX` or the fps) | **missing** | ALVR `INT32_MAX`, WiVRn `ceil(fps)` `[PROVEN: settings.rs:1867; android_decoder.cpp:143]`. Keeps the codec clocked up. |
| `priority=0` (realtime) | set | `[PROVEN: AndroidMediaFormatHelper.h:22]` |
| Separate **`c2.qti.{avc,hevc}.decoder.low_latency`** component | **not selected** (`createDecoderByType` picks the default) | Moonlight: "On some Qualcomm devices (like Pixel 4), there are separate low latency decoders (like c2.qti.hevc.decoder.low_latency) that advertise FEATURE_LowLatency while the standard ones do not." `[PROVEN: MediaCodecHelper.java:900-910]` Presence on XR2 `[SPECULATION]` → list codecs on the Quest and use `AMediaCodec_createCodecByName` if present. |
| One AU per input buffer (or `BUFFER_FLAG_PARTIAL_FRAME` on all but the last NAL) | per-NALU, flag 0 | `[PROVEN: VideoDecoder.cpp:208-232]`. With multi-slice frames a decoder may only know a picture is complete when the next AU starts (+1 frame). `[SPECULATION — test: compare decodingTime with AU-aggregated input]` |
| Async mode (`AMediaCodec_setAsyncNotifyCallback`) | sync, blocking dequeue | Blocking dequeue already wakes on availability → expected gain ≈0. `[INFERRED: VideoDecoder.cpp:271]` |

---

## 3. Latency estimate per path (Quest-side only: last packet of a frame received → photons)

**Assumptions** (all to be replaced by measurements):
- rx/wfb/RTP/loopback ≈ 0.5 ms `[SPECULATION]`; decode D ≈ 4–8 ms (mean 6) for 720p/1080p H.265 on XR2 with
  low-latency keys `[SPECULATION — measure with PixelPilot's decodingTime on the Quest]`.
- T = refresh period: 8.33 ms @120, 11.1 @90, 13.9 @72.
- Compositor latch → photons ≈ 1.0–1.3 T: compositor GPU work just before vsync ("TimeWarp takes a small amount of
  CPU time, then a length of GPU time in the run up to true VSync"), then LCD scanout (~T), LC settle, backlight strobe
  "for a fraction of the frame". `[PROVEN: developers.meta.com/horizon/blog/understanding-gameplay-latency-for-oculus-quest-oculus-go-and-gear-vr/ (2019-04-11);
  uploadvr Quest 2 LCD (Meta Display Week 2022); INFERRED: 1.0–1.3 T]`

| Path | Structure (mean) | @120 Hz | @90 Hz | @72 Hz | Confidence |
|---|---|---|---|---|---|
| **C** native OpenXR + surface swapchain + VIEW quad | 0.5 + D + 0.5T + ~1.15T | **~20 ms** (range ~14–26) | ~25 ms | ~30 ms | `[INFERRED]` structure from spec; numbers `[SPECULATION]` |
| **B** native OpenXR + SurfaceTexture/ImageReader + app render (PixelPilot_quest, ALVR-style) | 0.5 + D + 0.5T (app latch) + ~2.2T (app frame + compositor + display) | ~29 ms | ~37 ms | ~44 ms (PixelPilot_quest runs at runtime default, likely 72 Hz `[SPECULATION]`) | `[INFERRED/SPECULATION]` |
| **B′** FPVue_xr (B + CPU NV21→RGBA + upload) | B + 2–5 ms | ~32 ms | ~40 ms | ~47 ms | `[SPECULATION]` |
| **A** 2D panel (PixelPilot) | 0.5 + D + SF latch 0.5T_sf + SF composition ~T_sf + panel/shell latch 0.5T + ~1.2–2.2T | ~35–45 ms | ~40–50 ms | ~45–70 ms (worse if the panel's virtual display is 60 Hz) | `[SPECULATION]` — Horizon's panel pipeline is undocumented |

**Take-aways**
- C beats B by ~1 frame and A by ~2–4 frames. At 120 Hz that is ~8 ms and ~15–25 ms respectively. `[INFERRED]`
- The refresh-rate lever multiplies everything that is expressed in T: going 72→120 Hz saves ~10 ms on C and ~15–25
  ms on A/B. `[INFERRED]`
- **20 ms total G2G is out of reach on Quest 2:** C alone is ~14–26 ms after the last packet, before counting
  exposure/readout (≥ part of an 8.3 ms frame at 120 fps), ISP, encode and air time. `[INFERRED]` A realistic
  Quest 2 total is ~30–35 ms with path C at 120 Hz. `[SPECULATION]`
- The only way to know A (and thus the gain) is to **measure**: same air unit, same stream, PixelPilot 2D vs a C
  prototype, 72/90/120 Hz, with the project's ESP32 G2G rig (`/g2g-latency` skill), N ≥ 25 samples per point.

**Cheap on-device probes that would harden the estimates** (no root):
- `adb shell dumpsys SurfaceFlinger` / `dumpsys display` while PixelPilot runs → which display (physical vs
  virtual) hosts the app and at what refresh rate; `dumpsys SurfaceFlinger --latency <layer>` for SF timing.
- Enumerate codecs (`adb shell dumpsys media.player`, or `MediaCodecList` in a debug build) → does
  `c2.qti.hevc.decoder.low_latency` exist; which vendor parameters are supported.
- In the native prototype: `XR_META_performance_metrics` compositor counters, and PixelPilot's `decodingTime`.

---

## 4. Effort — building a minimal native OpenXR FPV viewer

### 4.1 Option ranking by effort

| Route | What to do | Effort `[SPECULATION]` | Risk |
|---|---|---|---|
| **R1. Patch PixelPilot_quest** | In `openxr_app.cpp`: enable `XR_KHR_android_surface_swapchain` (+ `XR_FB_android_surface_swapchain_create`, `XR_FB_composition_layer_image_layout`); replace the SurfaceTexture creation (lines ~1338-1420) with `xrCreateSwapchainAndroidSurfaceKHR`; pass that Surface to the existing `videoPlayer.addAndStart(surface, 0)` (line 1500); drop `updateTexImage` + video eye-buffer rendering (~2041, 2898-2940); create a `VIEW` reference space and submit one `XrCompositionLayerQuad`; call `xrRequestDisplayRefreshRateFB(120)`. Keep UI quads as separate layers. | ~150–300 LOC, 1–2 days | Fork is ~10 months behind upstream PixelPilot (misses e.g. #120 queue bound); carries backend/Spatial-SDK baggage. |
| **R2. New minimal NativeActivity app on upstream PixelPilot modules** | Reuse `app/videonative` and `app/wfbngrtl8812` as Gradle library modules (they already are) + a ~800–1500 LOC OpenXR NativeActivity: instance/session (GLES binding just to satisfy session creation), surface swapchain, VIEW quad, refresh rate, perf settings, event loop; Java glue for `UsbManager` permission → fd for devourer (see FPVue_xr `rtl8812UsbPath`, PixelPilot `WfbLinkManager`). | 3–6 days | Cleanest, tracks upstream; needs the USB-permission/Activity lifecycle glue done right. |
| **R3. Upstream it into PixelPilot as an "XR" activity** | R2, but as a second launcher activity inside PixelPilot (manifest `com.oculus.intent.category.VR` on that activity only). | R2 + review | Best long-term; depends on maintainers. |
| R4. FPVue_xr / StereoKit | Would need StereoKit surface-layer support; its current path is CPU copy. | high | Not recommended. |

### 4.2 Concrete starting points

- **Khronos loader + headers:** `org.khronos.openxr:openxr_loader_for_android` (Maven) or the headers in
  `OpenXR-SDK-Source`; Meta runtime accepts the Khronos loader (Meta docs mention Khronos loader support for OS v62+).
  `[PROVEN: developers.meta.com/horizon/documentation/native/android/mobile-openxr/ ("OS versions v62 or later")]`
- **Meta sample to copy session/perf/refresh-rate boilerplate:** `Meta-OpenXR-SDK/Samples/XrSamples/XrCompositor_NativeActivity`
  (single C file, quad + cylinder layers, refresh-rate FB functions, perf settings, android thread settings;
  `compileSdk 32`, `ndkVersion 27.0.12077973`, `minSdk 26`, arm64 only). It does **not** use the Android surface
  swapchain. `[PROVEN: XrCompositor_NativeActivity.c:123-124,2287-2411; Projects/Android/build.gradle]`
- **Surface-swapchain + quad reference:** CitraVR `GameSurfaceLayer.cpp` (creation at :515-545, per-eye quad at
  :335-360, vertical-flip layout in `utils/Common.h:52-56`). `[PROVEN]`
- **Decoder + wfb-ng + devourer:** upstream PixelPilot `app/videonative` (decoder takes an `ANativeWindow` — no change
  needed) and `app/wfbngrtl8812` (outputs RTP to 127.0.0.1:5600). `[PROVEN: VideoDecoder.cpp:65,154; WfbngLink.cpp:67]`
- **Manifest for an immersive activity:** `android.intent.category.LAUNCHER` + `com.oculus.intent.category.VR`,
  `com.oculus.supportedDevices`, `android.hardware.usb.host`, USB_DEVICE_ATTACHED filter — FPVue_xr's manifest is a
  working template. `[PROVEN: FPVue_xr/app/src/main/AndroidManifest.xml:19-60]`
- **Windows build:** Android Studio + NDK 26.1.10909125 + CMake 3.22.1 are already installed on PC-VLAD and match
  PixelPilot's `ndkVersion`. `[PROVEN: ls /c/Users/vlad_/AppData/Local/Android/Sdk/{ndk,cmake}; PixelPilot/app/build.gradle:55]`
  (Meta's sample pins NDK 27.0.12077973 — change the pin or install it.)
- **Gotchas to plan for:** surface must stop being written before `xrEndSession` (spec: undefined otherwise)
  `[PROVEN: khr_android_surface_swapchain.adoc:73-79]`; decoder reconfigure on resolution change → update surface
  dimensions via `XR_FB_swapchain_update_state_android_surface`; keep the XR frame loop running every frame even
  though it renders nothing heavy.

---

## 5. Ranked recommendations

1. **Build path C (R1 first as a 1–2 day proof, then R2/R3):** native OpenXR, `XR_KHR_android_surface_swapchain`
   (mailbox, no SYNCHRONOUS, no USE_TIMESTAMPS), head-locked `VIEW`-space quad, `xrRequestDisplayRefreshRateFB(120)`,
   perf level SUSTAINED_HIGH. Expected gain vs PixelPilot 2D: ~15–45 ms `[SPECULATION]`.
2. **Run the air unit at 120 fps to match 120 Hz** (minimises judder), and A/B single-slice frames or
   AU-aggregated decoder input (§2.4) to remove any "is the picture complete?" wait. `[INFERRED; gain SPECULATION]`
3. **Decoder keys in PixelPilot upstream (helps every path, trivial):** add `vendor.qti-ext-dec-picture-order.enable=1`,
   `operating-rate`, and prefer a `*.low_latency` component when present. Verify each with PixelPilot's decodingTime
   on the Quest (bracket: keys off / keys on; N≥3 runs each). `[PROVEN keys exist in Qualcomm/Moonlight/ALVR code; gain SPECULATION]`
4. **Measure before arguing further:** ESP32 G2G rig, same stream: PixelPilot-2D vs C prototype × {72, 90, 120} Hz;
   plus `dumpsys SurfaceFlinger/display` to document the 2D-panel pipeline. This converts §3 from speculation to proof.
5. **Do not pursue:** front-buffer/SuperSync ports, late latching, FPVue_xr's CPU-copy path, or SurfaceTexture→eye-buffer
   rendering (PixelPilot_quest as-is) — each is either impossible on Horizon OS or ~1 frame slower than C.
6. **Set expectations:** Quest 2 cannot meet 20 ms G2G total; path C at 120 Hz is the floor (~30 ms total
   `[SPECULATION]`). For the 20 ms target a directly driven display (monitor/goggle panel) remains necessary.

---

## 6. Audit of prior notes (June 2026)

Audited files:
`C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/hardware-research/07-meta-quest-2-display.md` (07) and
`C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/research/47-quest2-compositor-bypass-deep-research.md` (47).

### Right
- PixelPilot runs on Quest 2/3 in non-VR mode; userspace devourer means no root/kernel module. (07 TL;DR, §1)
  `[PROVEN: README.md:28,137-138]`
- The VR compositor is always in the path; an app cannot render directly to the display. (07 §3, 47 §4)
  `[PROVEN: OpenXR frame-submission model; no front-buffer extension in xr.xml]`
- Raising the refresh rate is a real lever; prefer 90/120 over 72. (07 §3, 47 §3) `[INFERRED §3]`
- 20 ms G2G is not achievable with Quest 2; a directly driven display is needed for that target. (47 conclusion 1)
  — right conclusion, partly for wrong reasons (see below). `[INFERRED §3]`
- Compositor layers are the right primitive for video (47 §4 "nuanță bună") — right in principle, but see "Wrong".

### Wrong
- **"PixelPilot decodes into a SurfaceView which Horizon OS promotes to a compositor layer with late-latching"** and
  **"PixelPilot already uses the compositor-layer path"** (07 header + TL;DR + §3 table; 47 §3, §4, conclusion 2).
  PixelPilot contains **zero** OpenXR code and no VR activity; its SurfaceView is composited by Android
  SurfaceFlinger into the 2D panel. `[PROVEN: grep openxr/xrCreate/com.oculus in PixelPilot/app = 0; manifest lines 1-80]`
  The cited sources (Android XR Extensions docs, WebXR Layers spec, a Carmack quote) describe *other* platforms/APIs
  and do not document Horizon OS 2D panels.
- **Late latching as a latency reducer for this video.** Late latching re-writes head-pose uniforms before the GPU
  uses them; it requires Vulkan + multiview and does nothing for a decoded video frame. `[PROVEN: Meta late-latching doc]`
- **"Plausibly well under 10 ms" display tax for PixelPilot** (07 header, §5 table). No evidence; the 2D-panel path has
  at least one SurfaceFlinger composition plus the VR compositor and the LCD scanout/strobe — the compositor→photon
  part alone is ~1 frame (~8–14 ms). `[INFERRED §3]`
- **"120 Hz experimental"** on Quest 2 (07 §2 table, 47 §3). Current Meta docs list 120 Hz as a supported rate on
  Quest 2 (plus 80/96/100). `[PROVEN: unity-set-disp-freq doc]`
- **"Only real path = force 120 Hz + compositor layer (what PixelPilot already does)"** (47 TL;DR). It misses the
  native-OpenXR surface-swapchain path entirely, which is the actual way to put decoded video on a compositor layer.

### Unsupported (not verifiable from primary sources, or cited to secondary sources)
- Latency budget rows sourced to vrarwiki ("Compositor + TimeWarp ~1-2 ms", "scanout 2-25 ms") (07 §3) — secondary,
  generic, not Quest-specific.
- `debug.oculus.phaseSync` property (47 §3): not in Meta's system-properties page I fetched (which lists refreshRate,
  texture size, cpu/gpuLevel, foveation.dynamic, capture props). `debug.oculus.refreshRate` does exist but whether it
  affects a 2D panel app is undocumented. `[PROVEN: developers.meta.com/horizon/documentation/unity/ts-systemproperties/]`
- "ASW does not run on the 2D layer" (47 §4) — plausible, not shown for panels.
- Root / bootloader / custom-OS findings (47 §1-2) — outside this task; not re-verified.
- Resolution "1832×1920 per eye" (07 §2) is the marketing figure; Meta's Display Week data give ~1720×1890 usable per eye.
  `[PROVEN: uploadvr Quest 2 LCD article]`
- The "+10–16 ms eye-buffer upper bound" — an eye-buffer path (B) costs ~2 frames after the app latch, not 1; so it is
  not an upper bound either. `[INFERRED §3]`

### Missed
- The **`XR_KHR_android_surface_swapchain` + head-locked quad** design (zero-copy decoder → compositor, latest-buffer
  latch, independent of app frame rate) and its companion FB extensions.
- Existing native attempts: **PixelPilot_quest** (OpenXR, SurfaceTexture→eye buffers, world-locked, no 120 Hz request)
  and **FPVue_xr** (StereoKit, CPU NV21→RGBA copy).
- ALVR/WiVRn/CitraVR/Moonlight reference implementations and their decoder keys; the missing
  `vendor.qti-ext-dec-picture-order.enable`, `operating-rate`, and `*.low_latency` component selection in PixelPilot.
- The fast-switch **LCD backlight strobe** timing, which also rules out any scanline-racing trick on Quest 2.
- A concrete measurement plan to separate SurfaceFlinger/panel cost from compositor cost (dumpsys + A/B prototype).
- Quest 2 now runs an Android 12L/14 base (API ≥ 32), so `KEY_LOW_LATENCY` (API 30) is available at framework level.

---

## Open questions / hypotheses (what would confirm them)

- `[SPECULATION]` XR2 exposes `c2.qti.hevc.decoder.low_latency` → confirm by codec enumeration on the Quest.
- `[SPECULATION]` Quest 2 decode time 4–8 ms at 720p120 H.265 → PixelPilot `decodingTime` overlay on the Quest.
- `[SPECULATION]` 2D panel pipeline = SurfaceFlinger → virtual display → shell/compositor, possibly 60–72 Hz →
  `dumpsys SurfaceFlinger`, `dumpsys display` while PixelPilot runs.
- `[SPECULATION]` Path C ≈ 20 ms Quest-side at 120 Hz; A–C gap 15–45 ms → ESP32 G2G rig A/B, N ≥ 25 per point,
  bracketed over 72/90/120 Hz.
- `[SPECULATION]` Per-NALU input costs a frame on multi-slice streams → compare decodingTime with AU-aggregated input.

## References (web)
- Khronos OpenXR spec sources: https://github.com/KhronosGroup/OpenXR-Docs/tree/main/specification/sources/chapters (files copied to `repos/openxr-spec-snippets/`)
- https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_KHR_android_surface_swapchain.html
- https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/
- https://developers.meta.com/horizon/blog/understanding-gameplay-latency-for-oculus-quest-oculus-go-and-gear-vr/
- https://developers.meta.com/horizon/documentation/unity/unity-set-disp-freq/
- https://developers.meta.com/horizon/documentation/unity/unity-ovroverlay/
- https://developers.meta.com/horizon/documentation/unity/unity-sample-compositor-layers/
- https://developers.meta.com/horizon/documentation/unreal/unreal-late-latching/
- https://developers.meta.com/horizon/documentation/unity/ts-systemproperties/
- https://developers.meta.com/horizon/documentation/native/android/mobile-openxr/
- https://source.android.com/docs/core/media/low-latency-media
- https://android.googlesource.com/platform/hardware/qcom/media/+/refs/heads/main/msm8998/mm-video-v4l2/vidc/vdec/src/omx_vdec_extensions.hpp
- https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/
- https://en.wikipedia.org/wiki/Quest_2
- https://github.com/Consti10/FPV_VR · https://github.com/Consti10/RenderingX
- https://github.com/amwatson/CitraVR · https://github.com/WiVRn/WiVRn · https://github.com/moonlight-stream/moonlight-android
- https://github.com/gpratas-pereira/PixelPilot_quest · https://github.com/gehee/FPVue_xr · https://github.com/OpenIPC/PixelPilot
- https://github.com/OpenHD/QOpenHD/issues/299
