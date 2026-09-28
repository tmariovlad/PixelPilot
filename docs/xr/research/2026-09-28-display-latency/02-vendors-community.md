# Decode → photon on Quest: what streaming vendors and the community do, and what they measured

Date: 2026-09-28. Researched from scratch on the internet and in cloned source code. Question: how do low-latency
video streaming apps on Meta Quest (mainly Quest 2) shorten the time from "decoded frame" to "photons on the
panel", and what has anyone actually measured? Our setup, for comparison: H.264 MediaCodec decodes straight into an
`XR_KHR_android_surface_swapchain` surface shown as a head-locked quad; the FPV source runs at ~167 fps; we request
120 Hz.

**Evidence tags.** [PROVEN: url] means seen in source code (path + line), in an official doc/spec, or in a published
measurement whose method is stated. [INFERRED: ...] gives the reasoning chain. [SPECULATION] is a guess with a note on
what would settle it. Each section keeps **OFFICIAL / SOURCE** evidence apart from **ANECDOTAL** evidence (forum,
Reddit, press write-ups of in-app overlays, collaborator comments).

**Pinned source versions** (all source links are permalinks):
- ALVR `dc84d6835d4125226f9698f1f052629852d86e31` (2026-09-27): <https://github.com/alvr-org/ALVR/tree/dc84d6835d4125226f9698f1f052629852d86e31>
- WiVRn `754ba4f6e128fb68b47f052422323b41f033f4a0` (2026-09-27): <https://github.com/WiVRn/WiVRn/tree/754ba4f6e128fb68b47f052422323b41f033f4a0>
- OpenXR-Docs `5a82d45bc9e0adbaa24b6c4a3e5b6d50e08c887d` (2026-09-02): <https://github.com/KhronosGroup/OpenXR-Docs/tree/5a82d45bc9e0adbaa24b6c4a3e5b6d50e08c887d>
- moonlight-android `b48494cb96bff23d8886c4775cc4f39a1075495d`: <https://github.com/moonlight-stream/moonlight-android/tree/b48494cb96bff23d8886c4775cc4f39a1075495d>
- ALVR wiki `87954190fd64bb719e9de25e639330044cb63ae5`: <https://github.com/alvr-org/ALVR/wiki>

---

## TL;DR

1. **None of the big streamers use the Android-surface swapchain.** ALVR and WiVRn both decode into an
   `AImageReader` (`PRIVATE` format, GPU-sampled `AHardwareBuffer`), sample that buffer in their own GPU pass, and
   submit a **projection layer** at the pose the frame was rendered for, so the runtime's timewarp corrects head
   rotation [PROVEN: §1, §2]. That design needs an app render pass, so it has at least one app frame
   (render → compositor) that our direct-to-compositor path does not have [INFERRED: §1.2, §2.2]. For a
   **head-locked** FPV picture, reprojection buys nothing: the video carries no head pose.
2. **The only lever the vendors pull on the decode → display wait is phase: make the frame arrive just before the
   headset uses it.** WiVRn's server pacer moves its render/encode start so that "decoded" lands a p99.5 margin plus
   1 ms before the headset's blit, and nudges the phase by 1/10 of the error on every feedback
   [PROVEN: WiVRn `pacer.cpp` L65-69, L113, L161]. Meta's Phase Sync does the same inside the headset for app-rendered
   frames and is officially credited with −10 ms on Quest 2 (Oculus Home) [PROVEN: Meta blog]. ALVR has
   "frame submission timing phase sync" on its roadmap only [PROVEN: ALVR wiki]. **This is the technique that
   carries over to our layer** (an air-side phase lock). Our own PPXR1 proof of concept is the same idea.
3. **Buffering is traded against smoothness everywhere, and the low-latency end always drops stale frames.**
   ALVR keeps a running-average target of `max_buffering_frames` = 2 by default and pops the oldest decoded image when
   the average goes over it; its wiki says latency grows linearly with this setting [PROVEN]. Moonlight's lowest-latency
   pacing drains the decoder and renders only the newest buffer [PROVEN]. On an Android-surface swapchain the default
   (non-`SYNCHRONOUS`) BufferQueue already "always replac[es] the last buffer" [PROVEN: OpenXR spec], so we get the
   drop-stale behaviour for free. `SYNCHRONOUS` would add queueing; `USE_TIMESTAMPS` only helps when the producer
   sends future timestamps.
4. **Published Quest 2 decode → photon numbers do not exist.** The nearest third-party numbers are end-to-end
   motion-to-photon (MTP) figures from a 120 fps camera: **Quest 2 at 120 Hz, Link over USB, a minimal custom OpenXR
   app: 32.1 ± 1.4 ms and 31.3 ± 2.3 ms; Virtual Desktop over Wi-Fi at 120 Hz: 42.7 ± 2.4 ms while VD's own overlay
   said 30 ms** [PROVEN: Greendayle README, method stated]. In-app overlays (VD, ALVR, WiVRn) report a *predicted*
   display time, not photons: ALVR's `vsync_queue` and WiVRn's `displayed` are both just `predictedDisplayTime`
   [PROVEN: source]. No FPV-on-Quest project has published a measurement.
5. **120 Hz on Quest 2.** Meta's current doc lists 120 Hz as supported on Quest 2 and names no user setting
   [PROVEN: Meta doc]. Carmack said in 2022 it would become default-on [PROVEN: UploadVR quote]. A forum summary
   (April 2024) says the Quest 2 toggle still exists [ANECDOTAL]. Thermal throttling can drop any rate above 72 Hz to
   72 Hz [PROVEN: Meta doc]. Apps in Quest-1 compatibility mode only see 60/72 Hz [ANECDOTAL: Meta forum]. The only
   safe check is to read `predictedDisplayPeriod` and listen for `XrEventDataDisplayRefreshRateChangedFB`, as WiVRn does.

---

## 1. ALVR (alvr-org/ALVR): Quest client

### 1.1 Decoder → GPU path — OFFICIAL / SOURCE

- **Decoder output target is an `AImageReader`, not a Surface swapchain.** The reader is created with
  `ImageFormat::PRIVATE`, usage `GPU_SAMPLED_IMAGE`, max 10 images, and MediaCodec is configured onto
  `image_reader.window()` [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L369-L376>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L176-L182>].
- **Every decoded buffer is released with its own PTS as the render time** (`release_output_buffer_at_time(buffer,
  presentation_time_ns)`); the "PTS" is really the server's target vsync timestamp in ns
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L313-L322>].
- **Decoded images go into a queue.** The image listener pushes each acquired image; if the queue exceeds
  `2 × max_buffering_frames` it pops the oldest ("Video frame queue overflow")
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L203-L229>].
- **Buffering control = running average.** On each render-side dequeue, ALVR updates
  `avg = avg·w + len·(1−w)` and pops the front image when `avg > max_buffering_frames`
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L101-L136>].
  Defaults: `max_buffering_frames = 2.0`, `buffering_history_weight = 0.90`
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L1725-L1726>],
  help text: "Increasing this value will help reduce stutter but it will increase latency"
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L717-L726>].
- **GPU import.** The `AHardwareBuffer` becomes an `EGLImage` (`eglGetNativeClientBufferANDROID`,
  `EGL_NATIVE_BUFFER_ANDROID`) bound as `GL_TEXTURE_EXTERNAL_OES`
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/graphics/src/lib.rs#L379-L410>],
  copied into a staging texture, then run through the stream pass (foveation decode, colour) into the eye swapchains
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/graphics/src/stream.rs#L292-L302>].
- **MediaCodec options by default:** `operating-rate = i32::MAX`, `priority = 0`,
  `vendor.qti-ext-dec-low-latency.enable = 1`; `low-latency` (API 30) stays commented out with the note "Quest 1 and 2
  might not be capable, since they are on level 29"
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L1867-L1874>].
  The format also carries a fake `width=512/height=1024`, with a comment against changing it
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/video_decoder/android.rs#L252-L255>].
- **"Decoder latency limiter"** (the current name for what older builds called a decoder latency fixer): when decode
  latency stays above `max_decoder_latency_ms` (default 30 ms) for `latency_overstep_frames` (default 90), the
  bitrate is multiplied by 0.99. Its help text says: "Currently there is a bug where the decoder latency keeps rising
  when above a certain bitrate". It is a bitrate controller, not a presentation lever
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L332-L357>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L392-L396>,
  defaults <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/session/src/settings.rs#L1753-L1759>].

### 1.2 Frame loop, pacing, stream fps vs display refresh — OFFICIAL / SOURCE

- **Refresh rate.** ALVR calls `request_display_refresh_rate(refresh_rate_hint)` when `XR_FB_display_refresh_rate`
  is present [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L114-L117>].
  The server renders at the negotiated rate; the client does not convert frame rates. The wiki's troubleshooting
  page says Meta's "framerate scaling for throttling" is not handled, so a throttled headset and the streamer drift
  apart and stutter [PROVEN: <https://github.com/alvr-org/ALVR/wiki/Troubleshooting> (section "Possible temporary fix
  for Meta framerate scaling for throttling feature"); maintainer confirmation in
  <https://github.com/alvr-org/ALVR/issues/2537>].
- **Standard OpenXR loop:** `xrWaitFrame` → `vsync_time = predicted_display_time` → `stream.render()` →
  `xrEndFrame(display_time)`
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/lib.rs#L582-L623>].
- **"Late latch" of the video frame inside the app frame.** After `xrWaitFrame`, `render()` polls the decoder queue
  every 0.5 ms for up to `0.8 × frame_interval` (`DECODER_MAX_TIMEOUT_MULTIPLIER = 0.8`) before it gives up and
  re-shows the previous frame
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L33>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L343-L354>].
- **Timewarp is used.** The frame goes out as a `CompositionLayerProjection` whose views carry the **pose the server
  rendered with**, and `xrEndFrame` gets the **frame's own timestamp** as display time (capped at 1 s old), so the
  Meta compositor reprojects from that pose to the current head pose. ALVR only re-renders the rotation itself on YVR
  (`use_custom_reprojection = is_yvr()`)
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L406-L430>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L483-L494>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L227>].
- [INFERRED] Decode → photon in ALVR is therefore: decode done → wait in the image queue (≥ 0, target ~2 frames of
  running-average occupancy) → wait for the next app frame (`xrWaitFrame` wake-up) → GL staging and stream pass →
  `xrEndFrame` → compositor → scan-out. That is at least one app frame plus a compositor pass. Our Android-surface
  quad skips the app frame and the GPU copies (cites: the lines above).

### 1.3 ALVR statistics: what "decode / decoder queue / vsync queue" mean — OFFICIAL / SOURCE

- `video_decode` = decoder callback time − packet received; `video_decoder_queue` = `report_compositor_start` time −
  (received + decode); `rendering` = submit time − previous stages
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/statistics.rs#L66-L103>].
- `vsync_queue` is **not measured**. The code comment reads "it cannot be measured by ALVR and should be reported by
  the VR runtime", and the value passed in is `predicted_display_time − xr_now` at submit
  [PROVEN: <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_core/src/statistics.rs#L89-L106>,
  <https://github.com/alvr-org/ALVR/blob/dc84d6835d4125226f9698f1f052629852d86e31/alvr/client_openxr/src/stream.rs#L459-L462>].
  So ALVR's "total latency" ends at the runtime's *prediction*, not at photons.
- Wiki: "Client VSync" = "VR runtime compositor latency" [PROVEN: <https://github.com/alvr-org/ALVR/wiki/How-ALVR-works> (tracking/prediction section)];
  "AVC/H.264 (with CAVLC) may save a few milliseconds of decode latency"; "increasing maxBufferingFrames will
  linearly increase latency" [PROVEN: <https://github.com/alvr-org/ALVR/wiki/Settings-tutorial>, Steps 2 and 4].
- Roadmap: phase sync for "frame submission timing (to reduce frame queueing on the client, controlled by shifting the
  phase of the driver rendering cycle)" is listed under **Upcoming** [PROVEN: <https://github.com/alvr-org/ALVR/wiki/How-ALVR-works> § Upcoming → Phase sync].

### 1.4 ANECDOTAL (ALVR issues / PRs)

- Quest 2: decode latency blows up above ~60 Mbps in one user's case, and at 2144p "no matter the bitrate it just
  gets to 100 ms". A collaborator puts the HEVC limit at "about 200Mbit for quest2/3 — after that it struggles — the
  symptom of which is huge decode latency" [ANECDOTAL: <https://github.com/alvr-org/ALVR/issues/2305>].
- MediaCodec `priority = 1` gave "a big regression … on Quest 2", which is why `priority = 0` is the default. A
  maintainer suggests `low-latency=1` should work on Quest 2 by now [ANECDOTAL: <https://github.com/alvr-org/ALVR/pull/1960>].

---

## 2. WiVRn (WiVRn/WiVRn): Quest client + server pacer

### 2.1 Decoder → GPU path — OFFICIAL / SOURCE

- `AImageReader_newWithUsage(w, h, AIMAGE_FORMAT_PRIVATE, CPU_*_NEVER | GPU_SAMPLED_IMAGE, image_buffer_size + 4)`,
  where `image_buffer_size = 3`
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/decoder/android/android_decoder.cpp#L119-L127>,
  <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.h#L53>].
- Async MediaCodec; each output buffer is released with `render = true` as soon as it arrives
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/decoder/android/android_decoder.cpp#L533-L545>].
  The image callback uses `AImageReader_acquireLatestImage`, so older images are skipped
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/decoder/android/android_decoder.cpp#L282-L291>].
  The buffer is imported into Vulkan with a `VkSamplerYcbcrConversion`
  [PROVEN: same file, L354-L400].
- Format keys: `OPERATING_RATE = ceil(stream fps)`, `PRIORITY = 0`; `vendor.qti-ext-dec-low-latency.enable` is
  **commented out** [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/decoder/android/android_decoder.cpp#L138-L144>].

### 2.2 Presentation — OFFICIAL / SOURCE

- **Frame selection by display time.** In each `xrWaitFrame` cycle the client picks, among the last 3 decoded frames,
  the one whose server-predicted `display_time` is closest to the runtime's `predictedDisplayTime`
  (`common_frame(frame_state.predictedDisplayTime)`)
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L673-L719>,
  <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L923>].
- The frame is drawn (defoveated) into the app's swapchain and submitted as a **projection layer** with the rendered
  pose, so timewarp applies
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L1185-L1207>].
- `feedback.displayed = frame_state.predictedDisplayTime`: WiVRn's "displayed" is the runtime prediction, not a
  measurement [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L940-L944>].
- The refresh rate follows the server's stream description (`session.set_refresh_rate`), and the client forwards
  `refresh_rate_changed` events to the server
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L1299>,
  <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/client/scenes/stream.cpp#L1449-L1451>].

### 2.3 Server-side phase lock (the transferable technique) — OFFICIAL / SOURCE

`server/compositor/pacer.cpp`:
- A worker collects `decoded − present` for each frame, takes the **99.5th percentile**, and adds
  `WIVRN_CLIENT_MARGIN_MS` (default **1 ms**) → `safe_present_to_decoded_ns`
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/server/compositor/pacer.cpp#L31>,
  <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/server/compositor/pacer.cpp#L52-L69>].
- `predict()` places the desired present time at `predicted_client_render − safe_present_to_decoded_ns`, so the frame
  finishes decoding just before the headset's render slot
  [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/server/compositor/pacer.cpp#L96-L126>].
- `on_feedback()` computes the phase error between the headset's `blitted` time and the predicted slot, wraps it into
  ±½ period, and applies **1/10 of it** (`last_ns += d / 10`); it also tracks `mean_render_to_display_ns` with a 0.1
  lerp [PROVEN: <https://github.com/WiVRn/WiVRn/blob/754ba4f6e128fb68b47f052422323b41f033f4a0/server/compositor/pacer.cpp#L128-L166>].
- [INFERRED] This is a phase-locked loop on "decode complete vs. headset consumption", with a tail-latency margin
  instead of a mean. For us, the target event is the Meta compositor's latch of our surface, not an app blit, and the
  actuator is the air unit's frame period. The PPXR1 design already has that shape; WiVRn adds two refinements: set
  the setpoint from a high percentile of arrival jitter (not the mean), and move only a fraction of the error per step.

### 2.4 ANECDOTAL (WiVRn PRs)

- A WiVRn collaborator on a Quest 3 extended-refresh PR: "The decoder already struggles with 120FPS, I doubt we can
  sustain decode under 7ms (for 144Hz)". He also calls Meta's acceptance of rates outside the enumerated list a spec
  violation. A contributor reports streaming "works ok up to 200hz" with slight flicker ≥ 185 Hz (Quest 3)
  [ANECDOTAL: <https://github.com/WiVRn/WiVRn/pull/1076>].

---

## 3. Virtual Desktop, Steam Link, Air Link / Quest Link

### OFFICIAL (Meta)
- **Oculus Link architecture:** "The remote streaming client is responsible for decoding, rectifying and submitting
  the frame to the compositor"; ATW with Adaptive Compositor Kickoff "makes sure to kick off a frame just in time so
  that it can be decoded, rectified and presented for the upcoming display period". The post gives no ms breakdown
  [PROVEN: <https://developers.meta.com/horizon/blog/how-does-oculus-link-work-the-architecture-pipeline-and-aadt-explained/>].
- **Phase Sync:** "The aim is to have the frame finish rendering right before our compositor needs the completed
  frame". Measured: "10 milliseconds latency reduction in Oculus Home with Quest 2, and an 8 milliseconds reduction
  with Quest"; "Phase Sync will be the default Vr Timing management method in our OpenXR implementation"
  [PROVEN: <https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/>].
  [INFERRED] Phase Sync paces *app-rendered* frames through `xrWaitFrame`. An Android-surface layer is produced by
  MediaCodec outside that loop, so Phase Sync does not pace our video. It does show that Meta measures ~8-10 ms of
  "wait before compositor" in a naively paced pipeline, which is the same class of wait an air-side phase lock attacks.
- **Compositor cadence:** "On both Quest1 and Quest2, its per-frame work is split in 2 for latency optimisations,
  preempting your application usually twice per frame as it runs every 7ms" (at 72 Hz)
  [PROVEN: <https://developers.meta.com/horizon/blog/a-vr-frames-life/>, 2021-05-20].
- **Air Link 120 Hz** arrived with Quest 2 v29 [PROVEN (press): <https://www.androidcentral.com/oculus-air-link-now-supports-120hz-wireless-pc-vr-gaming-quest-2>].
- **Synchronous Spacewarp (VD):** frame extrapolation on the headset using Qualcomm's Adreno Motion Engine. It fills in
  missed frames and does **not** reduce decode → photon [PROVEN: <https://www.khronos.org/news/permalink/a-virtual-boost-in-vr-rendering-performance-with-synchronous-space-warp-using-openxr>,
  <https://www.uploadvr.com/virtual-desktop-synchronous-spacewarp/>].

### ANECDOTAL
- VD's own overlay reported "motion to photon latency as 26 milliseconds" at 90 Hz on a pre-launch Quest 2 (press
  quoting the in-app number) [ANECDOTAL: <https://www.uploadvr.com/virtual-desktop-quest-2-pc/>, 2020-09-28].
- VD v1.18 "should improve latency by about 10ms" (Godin on Reddit, via press); no mechanism given
  [ANECDOTAL: <https://www.uploadvr.com/huge-virtual-desktop-update-latency-environments/>].
- Quest OS v42/v43 raised VD latency; fixed in VD 1.21.1, cause not published
  [ANECDOTAL: <https://mixed-news.com/en/virtual-desktop-update-fixes-latency-issues-with-quest-2/>].
- VD overlay: "Decoding: Headset load. 12 ms to 15 ms is usual for AV1 or HEVC" (context suggests Quest 3)
  [ANECDOTAL: <https://abolethvr.substack.com/p/more-on-ez-vd-setup>].
- VD release notes (GitHub) mention "Significant latency improvements" (v1.34.0) with no detail
  [ANECDOTAL: <https://github.com/guygodin/VirtualDesktop/releases>].
- Oculus Link: wired uses H.264 with 5 slices, Air Link HEVC with 1 slice; slicing "can add 5-10ms" (search-result
  summary of a Blur Busters thread; the page returned 403 to direct fetch, so this is unverified)
  [ANECDOTAL/SPECULATION: <https://forums.blurbusters.com/viewtopic.php?t=10364>].
- **Steam Link on Quest:** no developer post on decode → photon found. Community MTP numbers exist (§6).
- Closed source (VD, Steam Link, Air Link): whether they use an Android-surface layer or a projection layer is not
  published [SPECULATION; would need an APK/trace inspection].

---

## 4. Moonlight ports, Quest media players, Bigscreen

### OFFICIAL / SOURCE
- **moonlight-android** (the Android client usually sideloaded on Quest as a 2D app) has three pacing modes. In the
  non-"balanced" modes it drains the decoder and renders only the newest buffer (`releaseOutputBuffer(lastIndex,
  System.nanoTime())`: "Use a PTS that will cause this frame to be dropped if another comes in within the same V-sync
  period"). "Balanced" hands frames to a `Choreographer` vsync callback instead
  [PROVEN: <https://github.com/moonlight-stream/moonlight-android/blob/b48494cb96bff23d8886c4775cc4f39a1075495d/app/src/main/java/com/limelight/binding/video/MediaCodecDecoderRenderer.java#L1023-L1070>,
  L948-L991].
- Moonlight's decoder options, tried from most to least risky: `low-latency=1` (Android 11+), `vdec-lowlatency`,
  `operating-rate=Short.MAX_VALUE` on Qualcomm (not Adreno 620), else `priority=0`; then vendor keys
  `vendor.qti-ext-dec-picture-order.enable` + `vendor.qti-ext-dec-low-latency.enable`. It also notes that some Qualcomm
  devices have separate `c2.qti.*.decoder.low_latency` components that advertise FEATURE_LowLatency
  [PROVEN: <https://github.com/moonlight-stream/moonlight-android/blob/b48494cb96bff23d8886c4775cc4f39a1075495d/app/src/main/java/com/limelight/binding/video/MediaCodecHelper.java#L481-L590>,
  L903-L911].
- **Android MediaCodec contract** (it applies to whatever consumes the Surface): "if multiple buffers are sent to the
  Surface to be rendered at the same VSYNC, the last one will be shown, and the other ones will be dropped"; a
  timestamp not within ~1 s of `System.nanoTime` is ignored and the buffer shown "at the earliest feasible time";
  "Since Build.VERSION_CODES.Q the default behavior is to drop excessive frames"
  [PROVEN: <https://developer.android.com/reference/android/media/MediaCodec> (releaseOutputBuffer(int,long); "Using an Output Surface")].
- **Meta, VR video (Carmack):** "Display the video surface(s) on a compositor layer, don't draw them into your 3D
  world" and "Copy the decoded frames to a deep swapchain instead of directly using the Surface to mitigate small
  glitches" [PROVEN: <https://developers.meta.com/horizon/blog/techniques-for-improved-vr-video-w-john-carmack/>].
  [INFERRED] For playback he trades latency for smoothness (a deep swapchain). For live FPV the direct Surface is the
  low-latency end of the same trade.
- **Meta Unity docs:** "Is External Surface … allows the creation of Android Surface and lets Timewarp layer manage
  it"; "use the Is External Surface feature to … feed external video directly into the compositor"
  [PROVEN: <https://developers.meta.com/horizon/documentation/unity/unity-ovroverlay/>].
- Open-source users of `XR_FB_android_surface_swapchain_create`: Godot's vendor plugin exposes both flags
  (`synchronous`, `use_timestamps`) as layer properties
  [PROVEN: <https://github.com/GodotVR/godot_openxr_vendors/blob/master/plugin/src/main/cpp/extensions/openxr_fb_android_surface_swapchain_create_extension.cpp#L37-L38>];
  Wolvic (browser) uses `xrCreateSwapchainAndroidSurfaceKHR` for video
  [PROVEN: <https://github.com/Igalia/wolvic/blob/main/app/src/openxr/cpp/OpenXRSwapChain.cpp#L41-L48>].
  None of them publishes a latency measurement.

### ANECDOTAL
- A zero-copy Android-surface pipeline "prevents applications from running GPU processing on the decoded frames" and
  a user asks Meta for a GPU hook (feature request, Quest 3 8K player)
  [ANECDOTAL: <https://communityforums.atmeta.com/discussions/Questions_Discussions/feature-request---expose-android-surface-swapchain-frames-to-gpu-vulkan-for-comp/1359668>].
- AVPro Video (commercial Unity player) documents its "XRCompositionLayer" output as decoder surface → XR swapchain
  with no BGRA conversion or texture handling (issue text, Quest 2/3)
  [ANECDOTAL: <https://github.com/RenderHeads/UnityPlugin-AVProVideo/issues/2505>, <https://github.com/RenderHeads/UnityPlugin-AVProVideo/issues/2496>].
- Skybox / Bigscreen / Oculus TV: nothing published on decode → photon or surface-layer latency was found.
- Moonlight Quest ports on GitHub (`berry64/moonlight-quest`, `MoonlightQuestUnity`) are stock moonlight-android
  copies or empty; no OpenXR surface-layer Moonlight port was found (gh repo search, 2026-09-28).

---

## 5. FPV on Quest

### OFFICIAL / SOURCE
- **OpenIPC PixelPilot** and **FPVue_android** list Meta Quest 2/3 as supported "in non-VR mode" (a 2D Android panel
  window, composited by the Horizon shell) [PROVEN: <https://github.com/OpenIPC/PixelPilot/blob/master/README.md>,
  <https://github.com/gehee/FPVue_android>]. No latency numbers on Quest.
- **Consti10 FPV_VR / LiveVideo10ms** (phone VR for wifibroadcast): published MediaCodec total decode times of
  8.0-11.5 ms on phones (Galaxy S9+, Pixel 3, HTC U11) and "SuperSync" front-buffer rendering for Daydream phones
  [PROVEN: <https://github.com/Consti10/LiveVideo10ms>, <https://github.com/Consti10/RenderingX>]. [INFERRED] Front-buffer
  or beam-racing tricks do not carry over to Quest, because the Horizon compositor owns the display and apps only
  submit layers.
- GitHub repo search for "fpv openxr", "fpv quest", "wfb quest vr", "openipc vr", "pixelpilot xr" found **no other
  OpenXR FPV viewer** (2026-09-28). Our fork looks like the only native-XR PixelPilot in public.

### ANECDOTAL
- Quest 3 + cheap analog UVC receivers: "It has about the latency that the passthrough has + a little more. Usable for
  slow flights" (Hackaday comment); no number [ANECDOTAL: <https://hackaday.com/2025/01/03/fpv-flying-in-mixed-reality-is-easier-than-youd-think/>].
- IntoFPV "Using the Quest3 as FPV Goggles" (Walksnail V1 at 1080p60 into Quest 3, "very little latency" per search
  summary; the page returned 403) [ANECDOTAL: <https://intofpv.com/t-using-the-quest3-as-fpv-goggles>].
- DJI / HDZero / Walksnail "on Quest": no measured G2G found. The goggle-native figures (HDZero 3-5 ms, Walksnail
  22-30 ms, DJI O4 ~28 ms) come from blogs without method and describe the goggles, not Quest
  [ANECDOTAL: <https://blog.uavmodel.com/fpv-goggle-ecosystem-analog-vs-hdzero-vs-walksnail-vs-dji-image-quality-latency-and-cost-compared-2026/>].

---

## 6. Third-party measurements on Quest 2 (and neighbours)

### Published with method
- **Greendayle, VR motion-to-photon** (120 fps phone slow-mo camera filming the controller and the HMD lens; a VRChat
  or minimal OpenXR test scene turns red when the hand moves; 10-20 flicks per row; frame counting, so resolution is
  about 8.3 ms per camera frame):
  - Quest 2 @ 120 Hz, Oculus OpenXR runtime over USB (Link), custom minimal OpenXR app, 500 Mb, noiseless:
    **32.1 ± 1.4 ms**; noisy: **31.3 ± 2.3 ms**.
  - Quest 2 @ 120 Hz, Virtual Desktop over Wi-Fi, SteamVR, H.264 150 Mbps: **42.7 ± 2.4 ms** ("VD latency 30ms", i.e.
    the overlay under-reported by ~13 ms).
  - Quest 3 VD 120 fps H.264 200 Mbit: 64-70 ms; Quest Pro WiVRn 90 Hz: 64-101 ms; wired Vive Pro 2: 41.7 ms.
  [PROVEN (community, method stated): <https://github.com/Greendayle/VR-Motion-to-photon-latency->]
  [INFERRED] These are controller-motion-to-photon figures and include tracking, PC render and encode. They bound
  the Quest 2 display path from above but cannot isolate decode → photon.
- **PLOS One 2023, audio-visual onset on MR headsets** (dummy head with light sensors on the eyes): Quest 2 (120 Hz,
  standalone, Unity) audio lags video by **36.44 ms** (headphones, jitter 1.70 ms) and 49.97 ms (internal speaker). This
  is AV offset, not display latency; listed only so nobody misreads it
  [PROVEN: <https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0295817>].
- **OptoFidelity passthrough photon-to-photon:** Quest 3 / Quest Pro 35-40 ms, Vision Pro ~11 ms (minimum values);
  **Quest 2 not tested** [PROVEN (press summary of OptoFidelity): <https://mixed-news.com/en/quest-3-vision-pro-passthrough-latency-measurement/>].
- Academic MTP study (Springer 2022): 21-42 ms for Vive, Rift, Rift S and Index, no Quest
  [PROVEN: <https://link.springer.com/article/10.3758/s13428-022-01983-5>].

### Display facts (Quest 2)
- Fast-switch LCD; the backlight flashes "after waiting for the liquid crystal to 'settle down'"; 100 nits at low
  persistence; 1920×3664; 120 Hz max. No persistence duration or flash timing was disclosed (Display Week 2022, via
  press) [PROVEN: <https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/>].
- Carmack: the LCDs in Quest (S) and Go have "lower persistence than the OLEDs in original Rift and Quest"
  [PROVEN: <https://x.com/id_aa_carmack/status/1108703559263178752>].
- 72 vs 90 vs 120 Hz: no third-party photodiode comparison on Quest 2 was found. Carmack recommends 120 Hz for 60 fps
  video because "it avoids the flickering of 60 Hz" [PROVEN: quote in <https://www.uploadvr.com/quest-2-120hz-no-longer-experimental/>].

### Self-reported / method unclear (ANECDOTAL)
- Air Link "Frame Latency" (probably Oculus Debug Tool): ~54.8 ms at 90 Hz, 59.1 ms at 80 Hz, 79.9 ms at 72.5 Hz
  (hotspot) [ANECDOTAL: <https://mixed-news.com/en/meta-quest-2-pc-vr-streaming-with-air-link-latency-review/>].

---

## 7. Is 120 Hz on Quest 2 available without a user toggle?

- **OFFICIAL (Meta doc, current):** the refresh-rate table lists Quest 2 with 72/80/90/96/100/120 Hz (60 Hz "Media
  apps only"); rates other than 72 Hz need `XR_FB_display_refresh_rate`; "If an app with a display refresh rate higher
  than 72 Hz experiences thermal events, dynamic throttling may change the refresh rate to 72 Hz as a first step". The
  page does not mention a user setting [PROVEN: <https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/>].
- **History:** 120 Hz shipped as an opt-in "experimental" setting in April 2021; in September 2022 Carmack said it
  would become default-on [PROVEN (press quoting Carmack): <https://www.uploadvr.com/quest-2-120hz-no-longer-experimental/>].
  A Meta forum thread summarised by search (April 2024) says the toggle is hidden on Quest 3 but "for Quest 2, the
  settings are still there" [ANECDOTAL: <https://communityforums.atmeta.com/discussions/OtherTroubleshooting/quest-3-version-64---no-120-hz-mode/1181365>, 403 on direct fetch].
- **Silent fallbacks reported:** (a) an OpenXR app that `xrEnumerateDisplayRefreshRatesFB` shows only 60/72 Hz and
  gets `XR_ERROR_DISPLAY_REFRESH_RATE_UNSUPPORTED_FB` for 90 Hz, because it runs in Quest-1 compatibility mode; fixed
  by target SDK 32 + `com.oculus.supportedDevices` metadata [ANECDOTAL: <https://communityforums.atmeta.com/discussions/dev-quest/openxrs-xr-fb-display-refresh-rate-extension-only-returns-60hz-and-72hz-for-ques/1237082>];
  (b) thermal throttling to 72 Hz (official, above); (c) ALVR users see stutter when throttling changes the rate
  underneath the stream [PROVEN: ALVR wiki, §1.2].
- [INFERRED] So "requested 120 → result 0" is not proof that the display runs at 120 Hz. The only safe checks are
  `predictedDisplayPeriod` from `xrWaitFrame` and `XrEventDataDisplayRefreshRateChangedFB` (WiVRn forwards the latter,
  §2.2).
- Spec note: Meta also accepts rates that are not in the enumerated list on Quest 3 (up to 240 Hz); a WiVRn
  collaborator calls that a violation of the OpenXR rule that other values must return `…UNSUPPORTED_FB`
  [ANECDOTAL: <https://github.com/WiVRn/WiVRn/pull/1076>].

---

## 8. Khronos / Meta on Android-surface swapchain timing

### OFFICIAL (OpenXR spec source)
- `XR_KHR_android_surface_swapchain`: the swapchain's producer is an `android.view.Surface`; the only allowed call on
  the swapchain is `xrDestroySwapchain` (no acquire/wait/release); writing frames outside VISIBLE/FOCUSED is
  undefined. **The spec says nothing about when the runtime samples the surface**
  [PROVEN: <https://github.com/KhronosGroup/OpenXR-Docs/blob/5a82d45bc9e0adbaa24b6c4a3e5b6d50e08c887d/specification/sources/chapters/extensions/khr/khr_android_surface_swapchain.adoc#L15-L78>].
- `XR_FB_android_surface_swapchain_create` flags:
  - `SYNCHRONOUS_BIT_FB`: "the underlying BufferQueue should be created in synchronous mode, allowing multiple buffers
    to be queued instead of always replacing the last buffer. Buffers are retired in order, and the producer may block
    until a new buffer is available."
  - `USE_TIMESTAMPS_BIT_FB`: "the compositor should acquire the most recent buffer whose presentation timestamp is not
    greater than the expected display time of the final composited frame."
  [PROVEN: <https://github.com/KhronosGroup/OpenXR-Docs/blob/5a82d45bc9e0adbaa24b6c4a3e5b6d50e08c887d/specification/sources/chapters/extensions/fb/fb_android_surface_swapchain_create.adoc#L36-L46>]
  - [INFERRED] So the **default is an async BufferQueue: the newest buffer replaces the older one**, and the compositor
    shows whatever is newest when it composes. That is the lowest-latency mode. `SYNCHRONOUS` adds in-order queueing,
    so up to N-1 frames of extra delay once the producer outruns the display (our case: 167 fps into 119.7 Hz).
    `USE_TIMESTAMPS` can only *hold back* a buffer whose PTS is in the future. For a live stream stamped at decode
    time it does nothing, or delays frames if the PTS is wrong.
- `XR_FB_swapchain_update_state_android_surface`: only width/height state [PROVEN: same folder, `fb_swapchain_update_state_android_surface.adoc`].
- No Khronos issue or Meta forum thread about "surface swapchain latches late" was found (GitHub code/issue search +
  web search, 2026-09-28). Public knowledge of *when* the Quest compositor latches the surface is nil. Only an
  on-device trace answers it (our `docs/xr/compositor-phase.md` measured it).

---

## (a) Techniques vendors use, and whether they apply to our Android-surface head-locked layer

| Technique | Project | Source | Applies to an Android-surface head-locked layer? | Expected gain for us |
|---|---|---|---|---|
| Decode into `AImageReader` (PRIVATE, GPU-sampled), app GPU pass into eye swapchain | ALVR, WiVRn | ALVR `android.rs` L369-376; WiVRn `android_decoder.cpp` L119-127 | No: it is the opposite design (adds an app frame and a copy) | Negative [INFERRED: §1.2] |
| Projection layer with the frame's render pose + runtime timewarp | ALVR, WiVRn, Link | ALVR `stream.rs` L406-430, L483-494; WiVRn `stream.cpp` L1185-1207 | No: a head-locked FPV picture has no head pose to correct | 0 (perceived rotation latency only; not relevant) |
| Server/source **phase lock** to headset consumption, margin = p99.5 jitter + 1 ms, correct 1/10 of the error per step | WiVRn | `pacer.cpp` L52-69, L96-126, L128-166 | **Yes**, as an air-side frame-period controller aimed at the compositor latch (our PPXR1) | Up to ~½ refresh period on average (~4.2 ms at 119.7 Hz) minus the jitter margin [INFERRED]; our PoC: −2.4 ms mean over Wi-Fi |
| Meta Phase Sync (late app-frame start) | Meta runtime | Meta blog | No for the video (MediaCodec is outside `xrWaitFrame`); yes for any app-rendered overlay | 0 on video; Meta quotes −10 ms for app frames on Quest 2 |
| Adaptive compositor kickoff / just-in-time decode | Oculus Link | Link architecture blog | Only through the source side (same as phase lock) | Same budget as the phase lock |
| Cap client buffering, drop the oldest when over target (`max_buffering_frames`) | ALVR | `android.rs` L101-136, settings L1725 | Already implicit: an async BufferQueue keeps only the newest buffer | 0 extra (keep the default: no `SYNCHRONOUS`) |
| Render newest decoder output, drop the rest in the same vsync | Moonlight (low-latency modes) | `MediaCodecDecoderRenderer.java` L1023-1052 | Yes, and MediaCodec + async queue already do it | 0 extra; don't add a Choreographer-style queue |
| Pick the frame whose target time is closest to `predictedDisplayTime` | WiVRn | `stream.cpp` L673-719 | Only via `USE_TIMESTAMPS`, which needs future PTS | ≤ 0 for live FPV |
| `SYNCHRONOUS_BIT_FB` (in-order queue) | spec / Godot option | `fb_android_surface_swapchain_create.adoc` L38-42 | Yes, but it **adds** latency when fps > refresh | Negative: up to (queue depth − 1) × 8.35 ms |
| Poll the decoder late inside the app frame (up to 0.8 × period) | ALVR | `stream.rs` L33, L343-354 | No app frame in our path | n/a |
| Decoder low-latency keys (`low-latency`, `vendor.qti-ext-dec-low-latency`, `operating-rate`, `priority=0`, picture-order) | ALVR, Moonlight, WiVRn (partly) | settings L1867-1874; `MediaCodecHelper.java` L481-590 | Yes (decode side, before the latch) | Already measured in `docs/xr/decoder-levers.md` |
| Highest refresh rate the panel allows | all | Meta refresh-rate doc | Yes: Quest 2 max 120 Hz | 90 → 120 Hz: ~1.4 ms less mean wait (½ × (11.1 − 8.35) ms) plus a shorter panel path [INFERRED] |
| Sliced encode/decode | Oculus Link (wired, 5 slices) | ALVR wiki "Sliced encoding"; Blur Busters summary | Partly: slices overlap air encode/transport with decode, but MediaCodec still outputs whole frames | Small, on transport/decode, not on decode → photon [SPECULATION] |
| Synchronous/Asynchronous Spacewarp | VD (SSW), Meta | Khronos/Qualcomm post | No: synthesises frames, adds work, needs pose/motion vectors | 0 / negative |
| Handle throttling-induced refresh changes (`DisplayRefreshRateChangedFB`) | WiVRn (forwards to server); ALVR (not handled) | WiVRn `stream.cpp` L1449-1451; ALVR wiki | Yes: the phase lock must re-lock to the new period | Robustness, not ms |
| Front-buffer / beam racing | Consti10 SuperSync (phones) | RenderingX README | No: the Horizon compositor owns the display | n/a |

## (b) Published measurements

| Device | Refresh | Method | Number | URL | Official / anecdotal |
|---|---|---|---|---|---|
| Quest 2, Link USB, minimal custom OpenXR app | 120 Hz | 120 fps camera, controller flick → scene colour change, 10-20 reps | MTP **32.1 ± 1.4 ms** (noiseless), **31.3 ± 2.3 ms** (noisy) | <https://github.com/Greendayle/VR-Motion-to-photon-latency-> | Third-party, method published |
| Quest 2, Virtual Desktop Wi-Fi, H.264 150 Mbps | 120 Hz | same | MTP **42.7 ± 2.4 ms** (VD overlay said 30 ms) | same | Third-party, method published |
| Quest 3, VD H.264 200 Mbit | 120 fps | same | MTP 64.4-70.2 ms | same | Third-party, method published |
| Quest Pro, WiVRn, Wi-Fi 6 / USB | 90 Hz | same | MTP 64-101 ms (bitrate/codec dependent) | same | Third-party, method published |
| Quest 2, Oculus Home | (72/90) | Meta internal | Phase Sync: **−10 ms** latency | <https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/> | Official |
| Quest (1), Oculus Home | 72 Hz | Meta internal | Phase Sync: −8 ms | same | Official |
| Quest 1/2 compositor | 72 Hz | Meta description | runs every 7 ms, work split in 2 per frame | <https://developers.meta.com/horizon/blog/a-vr-frames-life/> | Official |
| Quest 2 display | up to 120 Hz | Meta, Display Week 2022 | 100 nits at low persistence; flash after LC settles; no timing disclosed | <https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/> | Official (via press) |
| Quest 2 standalone, Unity | 120 Hz | light + audio sensors on dummy head | audio lags video 36.44 ms (headphones), 49.97 ms (speaker): **AV offset, not display latency** | <https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0295817> | Peer-reviewed |
| Quest 3 / Quest Pro passthrough | n/s | LED → 100 kHz sensor (OptoFidelity) | photon-to-photon 35-40 ms (min) | <https://mixed-news.com/en/quest-3-vision-pro-passthrough-latency-measurement/> | Third-party lab (press summary) |
| Quest 2, VD (pre-launch) | 90 Hz | VD's in-app overlay | "MTP" 26 ms | <https://www.uploadvr.com/virtual-desktop-quest-2-pc/> | Anecdotal (self-reported) |
| Quest 2, Air Link | 90 / 80 / 72.5 Hz | Oculus tool "Frame Latency" (method unclear) | 54.8 / 59.1 / 79.9 ms | <https://mixed-news.com/en/meta-quest-2-pc-vr-streaming-with-air-link-latency-review/> | Anecdotal |
| Quest (3?), VD | n/s | VD overlay | decode 12-15 ms "usual" for AV1/HEVC | <https://abolethvr.substack.com/p/more-on-ez-vd-setup> | Anecdotal |
| Quest 2/3, ALVR HEVC | n/s | ALVR statistics tab | decode latency "huge" above ~200 Mbit; one user ~100 ms at 2144p | <https://github.com/alvr-org/ALVR/issues/2305> | Anecdotal |
| Quest 3, WiVRn | 120 Hz | collaborator statement | "decoder already struggles with 120FPS", doubts < 7 ms decode | <https://github.com/WiVRn/WiVRn/pull/1076> | Anecdotal |
| Phones (S9+, Pixel 3, U11), LiveVideo10ms | 60 Hz | in-app decode timer | total decode 8.0-11.5 ms | <https://github.com/Consti10/LiveVideo10ms> | Project README (self-measured) |
| Quest 2, decode → photon, any app | any | — | **no published measurement found** | — | — |

---

## Open questions / hypotheses

- [SPECULATION] VD, Steam Link and Air Link may use an Android-surface or other direct compositor layer on Quest.
  Confirm with `dumpsys SurfaceFlinger`/Perfetto on the headset while each app streams, or by decompiling the APKs.
- [SPECULATION] A head-locked quad may be composited in a different half-frame slot from world-locked layers (the
  compositor splits its work in 2 per frame, §3). Only an on-device latch trace per screen half can confirm this.
- [SPECULATION] `c2.qti.*.decoder.low_latency` components (mentioned by Moonlight for Pixel 4) may exist on Quest 2.
  Check with `adb shell dumpsys media.player` / `MediaCodecList` on the headset.
- The Quest 2 120 Hz toggle: whether current Horizon OS still gates 120 Hz behind Settings → Display for third-party
  apps has only anecdotal evidence either way. Check on the device: with the toggle off, request 120 and read
  `predictedDisplayPeriod`.

## Method notes

- Sources cloned into `C:/Users/vlad_/AppData/Local/Temp/claude/research-clones/` (ALVR, WiVRn, OpenXR-Docs sparse,
  ALVR.wiki); moonlight-android and Meta-OpenXR-SDK files fetched with `gh api` at the pinned SHAs.
- Pages that returned 403 to direct fetch (Meta community forums, IntoFPV, Blur Busters, WePC) are cited only as
  search-result summaries and tagged ANECDOTAL/SPECULATION.
- Dropped as off-topic after reading: "Gotta Go Fast" (arXiv 2306.02637) measures an Oculus DK2, not Quest; CLET
  (PMC10546026) measures a Vive Pro Eye.
