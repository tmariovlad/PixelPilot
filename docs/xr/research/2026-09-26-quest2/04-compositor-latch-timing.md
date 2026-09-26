# 04: When the Horizon compositor latches a surface-swapchain layer on Quest 2

> Fresh research from primary sources (2026-09-26). The older reports 01–03 were read only for the audit in §6.
> Tags: `[PROVEN: source]` / `[INFERRED: from what]` / `[SPECULATION]`. **Nothing here was measured on the owner's
> Quest 2.** Every ms figure is derived from code, documentation or third-party logs.
> Setup assumed throughout: OpenXR app, `XR_KHR_android_surface_swapchain`, MediaCodec renders into the Surface,
> head-locked `XrCompositionLayerQuad` submitted every frame, `createFlags = 0` (no timestamps, not synchronous).

> **Correction, 2026-09-26: measured on the owner's Quest 2 (supersedes §1.1's lead time).** Perfetto trace, H.264 720p60 stream, XR app at 120 Hz.
> - The compositor (`com.oculus.vrruntimeservice`, thread `OVR::TimeWarp`) latches the video `SurfaceTexture` **once per frame, 2.14 ms before the DRM vsync callback** (p5–p95 1.93–2.39 ms). The half-frame lead assumed below (4.2–4.7 ms) is wrong.
> - At **90 Hz** the lead is **2.22 ms** and in **timestamp mode** it is **2.15 ms**, so it is a fixed time, not a fraction of the frame.
> - The two compositor passes (one per half) are 4.18 ms apart. The first starts 0.40 ms after the latch; the second starts ~2.2 ms after vsync and **does not** latch a new frame.
> - Adding the kernel flash offsets from §1.2 (8.0 / 11.35 ms, re-checked from `dsi_panel.c:780-860` + `hollywood-dsi-panel-boe-dsc-4k-120Hz-video.dtsi`): **latch → mid-flash is 10.2 ms (first half) / 13.5 ms (second half), ~11.9 ms averaged**, not ~14.
> - Source: [compositor-phase.md](../../compositor-phase.md) §"Compositor phase, measured" and `scripts/quest-latch/`. [PROVEN: trace]

---

## 1. Summary

### 1.1 Answer to Q1: when the latch happens

1. **The compositor latches one half-frame ahead and then races the scan, one eye per half-frame.** It does not
   latch a whole frame ahead, and it does not latch at vsync.
   - Meta's 2021 description of Quest 1 and Quest 2 says the compositor's "per-frame work is split in 2 for latency
     optimisations, preempting your application usually twice per frame as it runs every 7ms" (at 72 Hz).
     `[PROVEN: https://developers.meta.com/horizon/blog/a-vr-frames-life/ (2021-05-20)]`
   - Meta's own VrApi documentation gives the schedule. The asynchronous TimeWarp "consumes new eye images … halfway
     through a display refresh cycle. This is the first time the time warp can start updating the first eye, covering
     the first half of the display". It "has half a display refresh cycle (up to V-sync) to update the first eye",
     then "waits for V-sync and then has another half a display refresh cycle … to update the second eye".
     `[PROVEN: VrApi.h:265-300 (VrApi 1.1.42, mirror github.com/lovr-org/ovr_sdk_mobile); same text on the current
     page https://developers.meta.com/horizon/documentation/native/android/mobile-vrapi/]`
   - The original Carmack TimeWarp code does the same. It sleeps to `vsyncBase + 0.5` (eye 0) and `vsyncBase + 1.0`
     (eye 1) ("try to warp each eye exactly half a frame ahead"). It picks the newest finished eye buffers **only when
     it starts the first eye**, and reuses them for the second eye so that both eyes match.
     `[PROVEN: github.com/SoylentGraham/VRLib jni/VrApi/TimeWarp.cpp:196-203, 1241-1262 (Gear VR era, 2014)]`
   - Meta's `Tear=` metric ("Screen tears occur if the compositor takes too long to submit a frame") only makes sense
     for a compositor that races scan-out.
     `[PROVEN: https://developers.meta.com/horizon/documentation/native/android/ts-logcat-stats/]`
2. **Therefore the surface buffer is most likely acquired once per display frame, at the start of the first-eye
   slice.** That is about **T/2 before vsync**, plus a small CPU/GPU lead. At 120 Hz this is about 4.2–4.7 ms before
   vsync. At 72 Hz it is about 6.9–7.5 ms.
   `[INFERRED: half-frame schedule (PROVEN above) + buffer choice only at eye 0 (TimeWarp.cpp:1262). The exact
   BufferQueue acquireBuffer moment inside com.oculus.vrruntimeservice is NOT observed → §4 measures it]`
3. **What the panel does after vsync is known exactly** from the Quest 2 GPL kernel ("hollywood" device tree + DSI
   driver):
   - Video-mode dual-DSI panel, 3664 active lines. The first half of the lines is one eye; the kernel calls it the
     "right" BLU. `[PROVEN: hollywood-dsi-panel-boe-dsc-4k-120Hz-video.dtsi:21,44; dsi_panel.c:812-833]`
   - Refresh rate is changed by stretching the VFP at a constant line rate of 442,320 lines/s (2.261 µs per line).
     So **scan-out always takes 8.28 ms**, at 72 Hz as well as at 120 Hz.
     `[PROVEN: DT timings; 3686×120 = 6144×72 = 4916×90 = 5529×80 ≈ 442,3xx lines/s]`
   - The two backlight units (BLUs) are each flashed once. The flash ends exactly when the next frame starts writing
     that half, but the start is capped at `end of active + 1200 lines`.
     `[PROVEN: dsi_panel.c:780-860, hollywood-panel.dtsi:26-29]`

| Refresh | T (ms) | Eye-1 mid-flash after vsync | Eye-2 mid-flash after vsync | Mean |
|---|---|---|---|---|
| 120 Hz | 8.33 | **8.0** | **11.35** | 9.7 |
| 90 Hz | 11.1 | 10.7 | 11.5 | 11.1 |
| 80 Hz | 12.5 | 11.5 | 11.5 (same flash) | 11.5 |
| 72 Hz | 13.9 | 11.6 | 11.6 (same flash) | 11.6 |

`[INFERRED: arithmetic on the PROVEN formulas at brightness level 1000. Level 800–1200 shifts eye 1 by less than
0.15 ms]`

### 1.2 Expected range (Q3), Quest 2 at 120 Hz

These numbers use the half-frame model with the decoder's output phase uncorrelated with vsync.

| Segment | Eye 1 | Eye 2 | Tag |
|---|---|---|---|
| Frame queued → compositor latch (mailbox wait) | 0 – 8.3 (mean 4.2) | same | INFERRED (BufferQueue replace-latest §2) |
| Latch → vsync | ≈ 4.2 (+0–0.5 lead) | same | INFERRED (§1.1-2) |
| Vsync → mid-flash | 8.0 | 11.35 | INFERRED from PROVEN kernel code |
| **Latch → photon** | **≈ 12.2–12.7** | **≈ 15.5–16.0** | INFERRED |
| **Frame-ready → photon** | **12.2 – 21 (mean ≈ 16.5)** | **15.5 – 24 (mean ≈ 19.8)** | INFERRED |

- **Eye average: about 14 ms from latch to photon, and about 18 ms (range 14–22) from frame-ready to photon.**
  - Add one more T (8.3 ms) whenever a latch is missed. This happens, for example, if the decoder's acquire fence is
    not yet signalled, or if `SYNCHRONOUS` queueing is on.
- **Bracket for model risk:**
  - If Horizon actually latches a full frame ahead (no split), latch→photon becomes about 18 ms eye-average.
    `[SPECULATION]`
  - If it latches only about 2–3 ms before vsync, it becomes about 12 ms. `[SPECULATION]`
  - **Plausible latch→photon span at 120 Hz: 12–18 ms, with a central estimate of 14 ms.**
- **Cross-checks against Meta runtime numbers:**
  - `CFL` (compositor frame latency, "time in the Prd measurement spent in the OS compositor") is 19.7–21.7 ms in
    Meta's own 72 Hz example line. `[PROVEN: ts-logcat-stats doc]`
  - The model gives latch→photon at 72 Hz = 6.9 + 11.6 = **18.5 ms**. That is consistent with CFL_min ≈ 19.7 once
    Phase-Sync padding is added. `[INFERRED]`
  - Real OpenXR logs from a Quest 3 at 120 Hz show `CFL=10.6–10.9/14.8–14.9`.
    `[PROVEN: github.com/myers/openxr-vulkan-multiview-msaa benchmark_results/no_msaa_vrapi.txt]`
  - The Quest 3 panel is different. The number is only an order-of-magnitude sanity check: 1.3–1.8 frames.
- **At 72 Hz the same chain is 18.5–32.4 ms (mean about 25.5).** The panel costs as much time as the compositor.
  **120 Hz is the biggest lever** (§3).

---

## 2. What the flags and the spec actually say

- **`XR_KHR_android_surface_swapchain` defines no buffer-selection rule.**
  - The app may call only `xrDestroySwapchain` on the swapchain. Acquire, wait and release are invalid.
  - The producer submits "with ordinary Android APIs".
  - `[PROVEN: KhronosGroup/OpenXR-Docs specification/sources/chapters/extensions/khr/khr_android_surface_swapchain.adoc
    (local copy repos/openxr-spec-snippets/khr_android_surface_swapchain.adoc:54-71)]`
- **`XR_ANDROID_SURFACE_SWAPCHAIN_SYNCHRONOUS_BIT_FB` (bit 0)** means: "the underlying BufferQueue should be created
  in synchronous mode, allowing multiple buffers to be queued **instead of always replacing the last buffer**. Buffers
  are retired in order, and the producer may block until a new buffer is available."
  - This implies that **the default (flag clear) always replaces the last queued buffer**: a mailbox.
  - `[PROVEN: OpenXR-Docs …/fb/fb_android_surface_swapchain_create.adoc:38-42; xr.xml enum
    XrAndroidSurfaceSwapchainFlagBitsFB "Create the underlying BufferQueue in synchronous mode"; identical text in
    VrApi_Types.h:582-585 VRAPI_ANDROID_SURFACE_SWAP_CHAIN_FLAG_SYNCHRONOUS]`
- **How AOSP implements the two modes:**
  - In async mode, `item.mIsDroppable = mCore->mAsyncMode || …`.
  - On `queueBuffer`, if the last queued item is droppable it is freed and replaced (`bufferReplaced = true`).
  - With SYNCHRONOUS, items are not droppable, so they queue FIFO and the compositor retires one per composition.
  - `[PROVEN: android.googlesource.com platform/frameworks/native android14-release
    libs/gui/BufferQueueProducer.cpp:956-1000]`
  - **Latency effect of SYNCHRONOUS: once a backlog of k buffers forms, it persists as +k·T.** A burst of 2 frames
    within one period at 120 Hz gives +8.3 ms for good. There is no drop mechanism to recover.
    `[INFERRED from FIFO semantics + equal producer/consumer rates]`
- **`USE_TIMESTAMPS_BIT_FB` (bit 1):** "acquire the most recent buffer whose presentation timestamp is not greater than
  the expected display time of the final composited frame."
  `[PROVEN: fb_android_surface_swapchain_create.adoc:43-46]`
  - AOSP `acquireBuffer(expectedPresent)`:
    - drops stale earlier entries;
    - returns `PRESENT_LATER` for a buffer timestamped in the future;
    - treats a timestamp more than 1 s away from `expectedPresent` as "due now".
    - `[PROVEN: BufferQueueConsumer.cpp:119-177, 209-221]`
  - With `releaseOutputBuffer(idx, true)`, MediaCodec stamps the Surface with the stream PTS, not CLOCK_MONOTONIC.
    The flag is then either inert (PTS > 1 s off) or harmful (PTS near "now" → deferral).
    `[INFERRED; MediaCodec PTS behaviour not re-verified here → SPECULATION on the exact stamp]`
  - VrApi documents it as meant "Together with FLAG_SYNCHRONOUS … for video surfaces where several frames can be
    queued ahead of time", i.e. film playback, not live video. `[PROVEN: VrApi_Types.h:586-590]`
- **The current app already uses the right setting.**
  - `createFlags` is 0 unless the timestamp experiment is on.
    `[PROVEN: c:/xampp/htdocs/pixelpilot-xr/app/xr/src/main/cpp/XrRuntime.cpp:267-272]`
  - Decode output is released with `render=true` immediately.
    `[PROVEN: app/videonative/src/main/cpp/VideoDecoder.cpp:315]`
- **`predictedDisplayTime` is the midpoint of the display interval.**
  `[PROVEN: OpenXR rendering.adoc "must refer to the midpoint of the interval during which the frame is displayed"]`
  - On Quest 2 that corresponds to the BLU flashes, not to vsync. `[INFERRED]`

---

## 3. Levers table

The ms values are the change in frame-ready→photon, eye average, at 120 Hz unless stated.

| # | Lever | What it does | Evidence | Expected effect | Risk |
|---|---|---|---|---|---|
| L1 | **Refresh 120 Hz** (`xrRequestDisplayRefreshRateFB(120)`; ADB `setprop debug.oculus.refreshRate 120`) | Shrinks T. That cuts the latch lead (T/2) and the mailbox wait (T/2). Vsync→flash also drops from 11.6 to 9.7 ms mean. | Kernel DT timings + BLU code `[PROVEN]`; property values for Quest 2: 60/72/80/90/120 `[PROVEN: ts-systemproperties doc]` | **−7.5 ms mean vs 72 Hz** (25.5 → 18.0); −4 ms vs 90 Hz `[INFERRED]` | Battery/thermal only. Quest 2 needs 120 Hz enabled in Settings (experimental). |
| L2 | **`createFlags = 0`** (keep mailbox, no SYNCHRONOUS, no USE_TIMESTAMPS) | Newest buffer replaces the pending one, so the compositor always gets the newest. | §2 `[PROVEN spec + AOSP]` | Avoids +k·8.3 ms backlog (SYNCHRONOUS) and PRESENT_LATER deferrals (TIMESTAMPS) | None (already the default) |
| L3 | **Video fps > display rate** (air unit 150+ fps, mailbox drops extras) | The newest frame's age at the latch becomes uniform on [0, 1/R_video] instead of [0, T]. | Mailbox semantics `[INFERRED]` | Wait term 4.2 → 3.3 ms at 150 fps, → 2.1 ms at 240 fps (−1 to −2 ms mean) `[INFERRED]` | Air-unit load. Dropped frames are invisible anyway. |
| L4 | **Keep the compositor on time** (1 quad, opaque, no `BLEND_TEXTURE_SOURCE_ALPHA`, no `XR_FB_composition_layer_settings` super-sampling/sharpening, no `XR_META_automatic_layer_filter`, swapchain size = video size) | Lowers TW GPU time. Does not move the latch. | TW cost grows with layer count/complexity; "equirect and cylinder layers being more expensive"; super-sampling/sharpening add compositor cost `[PROVEN: ts-logcat-stats; os-compositor-layers doc]` | ~0 ms nominal. Prevents `Tear` and `Stale` (+T events). | None |
| L5 | **Phase Sync / `debug.oculus.phaseSync`** | Moves the app's `xrWaitFrame` wake-up. Irrelevant to surface content, which the compositor acquires itself. | Phase Sync is "the default Vr Timing management method in our OpenXR implementation" `[PROVEN: Phase Sync blog 2020-12-07]`; "Under the current OpenXR runtime … `setprop debug.oculus.phaseSync` have no effect" `[PROVEN: unreal-phase-sync doc]` | 0 ms `[INFERRED]` | None |
| L6 | **Regular swapchain + app late-latch (SurfaceTexture → GL → quad)** | Adds an app GPU stage in front of the same compositor latch. "Late latching" is about pose uniforms, not content. | UE4 late-latching blog `[PROVEN]`; stage count `[INFERRED]` | **+½ to +1 T worse** than N1 | Worse; do not use |
| L7 | `XR_FB_space_warp` / `XR_EXT_frame_synthesis` | Applies to projection layers (motion vectors). Not to a surface quad. | xr.xml ext 172/212 `[PROVEN]`; applicability `[INFERRED]` | 0 (keep off; ASW adds work) | Off by default |
| L8 | `XR_EXT_performance_settings` / CPU-GPU levels / `XR_KHR_android_thread_settings` | Faster app/decoder threads. The compositor already runs at higher GPU priority. | Compositor "runs on a higher priority context on the GPU" `[PROVEN: VR frame's life blog]` | Affects decode→queue only, not the latch `[INFERRED]` | Thermal |
| L9 | Brightness (BLU level 800–1200) | Moves only the start of the eye-1 flash (its end is fixed). | `dsi_panel.c:805-814` `[PROVEN]` | < 0.15 ms `[INFERRED]` | Ghosting none |
| L10 | **Root only:** `/sys/class/drm/sde-crtc-0/backlight_scanline_offset` (RW; default 1200 lines) | Lowers the cap on the eye-2 flash start. That gives an earlier eye-2 flash but less LC settle time. | `sde_crtc.c:508-576, 751` `[PROVEN]`; DT default `hollywood-panel.dtsi:27` `[PROVEN]` | Up to −2.7 ms on eye 2 at 120 Hz (the 1200-line settle) `[INFERRED]` | Needs root (retail Quest 2 not rootable). Ghosting. |
| L11 | Head-locked vs world-locked quad | Head-locked (`FIXED_TO_VIEW`) skips reprojection maths. The latch is the same. | LogLayers flags `[PROVEN: os-compositor-layers doc]` | 0 | — |
| — | Any setprop that moves the compositor latch later | **None found.** Meta documents only refreshRate, texture size, CPU/GPU level, foveation, capture, `logLayers`, `phaseSync` (VrApi only). | ts-systemproperties + os-compositor-layers `[PROVEN]` | — | Do not invent properties |
| — | Any OpenXR extension that controls surface-layer acquire timing | **None exists** among `XR_FB_*`, `XR_META_*`, `XR_EXT_*` in the registry. | xr.xml 2026-09 grep `[PROVEN]` | — | — |

**Kernel detail that looks like a lever but probably isn't, on Quest 2.** The hollywood DT enables a DPU writeback
CAC path:

- `qcom,sde-lineptr-scanline-advance = 256`, `sde-wb-passes = 2`, WB thread RT prio 99 on CPU7.
  `[PROVEN: hollywood-panel.dtsi &mdss_mdp]`
- It is kicked by a line-pointer IRQ 256 lines (0.58 ms) before vsync: "CAC is performed one eye at a time via
  writeback … Portrait display, use two pass writeback".
  `[PROVEN: sde_encoder_phys_wb.c:1533-1592; sde_encoder.c:4383-4440; msm_atomic.c:647]`
- Meta says the DPU does CAC when the DPU scaling factor `DSF` > 1.
  `[PROVEN: ts-logcat-stats "DPUs perform chromatic aberration correction and sharpening"]`
- Quest 2 example lines show `DSF=1.00`, so the stock Quest 2 path is most likely GPU CAC inside TimeWarp, with this
  WB path unused. `[INFERRED — if Quest 2 did use it, the whole composite would be due ≈0.6 ms before vsync, and the
  latch lead would be TW-GPU + margin ≈ 2–3 ms instead of T/2 = 4.2 ms]`

---

## 4. Measurement recipe (on-device, no root)

### 4.1 Cheap, runtime-reported numbers

1. **`adb logcat -s VrApi`.** Read these fields:
   - `CFL=min/max`: compositor frame latency.
   - `Preempt=`: compositor GPU slices per second. Divide by FPS. 2 per frame confirms the split model.
   - `TW=`, `Tear=`, `Stale=`, `LCnt=`, `DSF=`: DSF = 1.00 means the GPU-CAC path.
   - OpenXR apps still print this line: real 2025 OpenXR logs contain it.
     `[PROVEN: myers/openxr-vulkan-multiview-msaa log]`
   - Note the contradiction: the Unreal Phase Sync page says the logcat line has "no effect" under OpenXR.
2. **`adb shell setprop debug.oculus.logLayers 1` then `adb logcat -s CompositorClient`** shows the video quad, its
   flags and the SwapChain type every frame. `[PROVEN: os-compositor-layers doc]`
3. **In-app: `XR_META_performance_metrics`.** Counters to read:
   - `/perfmetrics_meta/app/motion_to_photon_latency`
   - `/perfmetrics_meta/compositor/{cpu,gpu}_frametime`
   - `/perfmetrics_meta/compositor/dropped_frame_count`
   - `[PROVEN: xr.xml ext 233; meta_performance_metrics.adoc:26-37]`
   - Log them next to the decoder's `queueBuffer` time.
4. **Kernel sysfs** (readability by the `shell` uid under SELinux is **untested**). Path from
   `device_create_with_groups(…, "sde-crtc-%d")` on the DRM class `[PROVEN: sde_crtc.c:7085]`:
   - `/sys/class/drm/sde-crtc-0/vsync_event`: last vsync, in ns.
   - `vsync_timing`: `"<vsw+vbp>,<vactive>,<vfp>@<Hz>"`.
   - `backlight_timing`: `"<BL pulse lines>,<right BLU start line>,<left BLU start line>"`.
   - `measured_fps`.
   - These give the exact vsync→flash offsets for the live mode and brightness. `[PROVEN: sde_crtc.c:375-436, 600-620]`

### 4.2 Perfetto: finding the latch

Record 10 s with MQDH, or `adb shell perfetto -c - --txt` with this config.

```
buffers { size_kb: 131072 fill_policy: DISCARD }
data_sources { config { name: "linux.ftrace" ftrace_config {
  ftrace_events: "sched/sched_switch"  ftrace_events: "sched/sched_wakeup"
  ftrace_events: "drm/drm_vblank_event"          # drm_vblank.c:1709, fired from sde_crtc_vblank_cb → drm_crtc_handle_vblank
  ftrace_events: "sde/tracing_mark_write"        # SDE_ATRACE_*: "vblank_0_callback", "encoder_vblank_callback",
                                                 #  "encoder_lineptr_callback", "complete_commit", counters wb_trigger_headroom
  ftrace_events: "ftrace/print"
  atrace_categories: "gfx"  atrace_categories: "video"  atrace_categories: "hal"  atrace_categories: "view"
  atrace_apps: "*"
}}}
data_sources { config { name: "track_event" } }          # VrApi / XR runtime metrics (Meta Perfetto blog)
data_sources { config { name: "linux.process_stats" } }
duration_ms: 10000
```

**What to look for:**

- **Producer side.** Look for the `queueBuffer` slice. `BufferQueueProducer.cpp` has `ATRACE_TAG_GRAPHICS` =
  `gfx` category. `[PROVEN: BufferQueueProducer.cpp:20]`
  - With Codec2, the output is queued from the **app process** (CCodec output surface).
    `[INFERRED — confirm in the trace]`
- **Consumer side, which is the latch.** Look for `acquireBuffer` slices (`BufferQueueConsumer.cpp:22,81`) inside
  **`com.oculus.vrruntimeservice`**. That process hosts "time warp and composition" (VrDriver.apk).
  `[PROVEN: engineering.fb.com 2023-09-12 "Meta Quest 2: Defense through offense"]`
  - A counter track named after the consumer (`ATRACE_INT(mConsumerName, queue size)`, `BufferQueueConsumer.cpp:301`)
    identifies which queue is the video surface.
  - Thread names inside the compositor are **unknown**. Discover them from the trace. `[SPECULATION]`
- **Vsync.** Use `drm_vblank_event` (crtc 0), or the `vblank_0_callback` slice.
- **Latch lead.** Compute `next_vsync − acquireBuffer_start` over at least 1000 frames. The half-frame model predicts
  about 4.2–4.7 ms at 120 Hz and about 6.9–7.5 ms at 72 Hz.
  - **Bracket it:** record at 72, 90 and 120 Hz, in shuffled order.
  - If the lead scales with T/2, the split model is confirmed.
  - If the lead is constant in ms, that points to the WB/DPU model.
- **Photon time.** Photon = vsync + BLU offsets from `backlight_timing` × (1 / (vtotal × Hz)).
- **Validation.** Close the loop with the photodiode / ESP32 G2G rig (skill `g2g-latency`), exactly as 01 §5 describes.
- **Caveat.** On user builds, perfetto may be refused `sde/*` or `drm/*` ftrace events by SELinux or the allowlist.
  `[SPECULATION]`
  - Fallback: use the `gfx` atrace plus a thread that polls `vsync_event`, or the XR-runtime track_event tracks.

**Diagnostic.** `adb shell am broadcast -a com.oculus.vrruntimeservice.COMPOSITOR_SKIP_RENDERING --ei milliseconds 60000`
disables TimeWarp for a minute. Use it only to confirm that a slice belongs to the compositor.
`[PROVEN: https://developers.meta.com/horizon/documentation/native/android/po-per-frame-gpu/]`

---

## 5. Sources

**Kernel** (Meta GPL, `facebookincubator/oculus-linux-kernel` branch `oculus-quest2-kernel-master`, commit
`e8c2245c4ca5`, blobless clone `repos/oculus-linux-kernel-quest2`, 3.9 MB, read with `git show`, no checkout):

- `arch/arm64/boot/dts/oculus/hollywood/hollywood-panel.dtsi`:
  - BLU duty 80 (8 %), max-scanline-offset 1200, bl 800–1200 (`:26-29`);
  - `&mdss_mdp` lineptr advance 256, wb-passes 2, wb-rtprio 99, CPU7.
- `hollywood-dsi-panel-{boe,jdi,jdi-nvt,sharp}-dsc-4k-{72,80,90,120}Hz-video.dtsi`: video mode, 960×3664 per DSI,
  VBP/VFP per rate, `dfps_immediate_porch_mode_vfp`.
- `techpack/display/msm/dsi/dsi_panel.c:780-975`: `dsi_panel_jdi(_nvt)_update_backlight`.
- `techpack/display/msm/sde/sde_crtc.c:375-620, 747-766, 2819-2877, 6110-6160, 6955-6967, 7085-7115`: sysfs, vblank,
  lineptr, timing props.
- `sde_encoder.c:4235-4440`, `sde_encoder_phys_vid.c:249-290, 470-530`, `sde_encoder_phys_wb.c:1533-1620, 2085-2107`,
  `msm_drv.c:560-575`, `msm_atomic.c:505-760`, `sde_trace.h:113, 390-396`, `drivers/gpu/drm/drm_vblank.c:1709`.

**Meta primary:**

- VrApi.h:265-300 and VrApi_Types.h:280-284, 578-591 (VrApi 1.1.42, mirror github.com/lovr-org/ovr_sdk_mobile).
- https://developers.meta.com/horizon/documentation/native/android/mobile-vrapi/
- https://developers.meta.com/horizon/blog/a-vr-frames-life/
- https://developers.meta.com/horizon/blog/understanding-gameplay-latency-for-oculus-quest-oculus-go-and-gear-vr/
- https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/
- https://developers.meta.com/horizon/documentation/unreal/unreal-phase-sync/
- https://developers.meta.com/horizon/documentation/native/android/ts-logcat-stats/
- https://developers.meta.com/horizon/blog/ovr-metrics-tool-vrapi-what-do-these-metrics-mean/
- https://developers.meta.com/horizon/documentation/native/android/os-compositor-layers/
- https://developers.meta.com/horizon/documentation/native/android/ts-systemproperties/
- https://developers.meta.com/horizon/documentation/native/android/po-per-frame-gpu/
- https://developers.meta.com/horizon/blog/how-to-run-a-perfetto-trace-on-oculus-quest-or-quest-2/
- https://developers.meta.com/horizon/documentation/native/android/mobile-timewarp-overview/
- https://engineering.fb.com/2023/09/12/security/meta-quest-2-defense-through-offense/
- Carmack TimeWarp source (Gear VR, 2014): github.com/SoylentGraham/VRLib `jni/VrApi/TimeWarp.cpp`.

**Khronos:**

- `KhronosGroup/OpenXR-SDK-Source specification/registry/xr.xml` (downloaded 2026-09-26: `XrAndroidSurfaceSwapchainFlagBitsFB`,
  ext 71/172/212/233/18512).
- `KhronosGroup/OpenXR-Docs specification/sources/chapters/extensions/{khr,fb}/…android_surface_swapchain*.adoc`,
  `rendering.adoc` (local copies in `repos/openxr-spec-snippets/`).

**AOSP:** android.googlesource.com `platform/frameworks/native` android14-release `libs/gui/BufferQueueProducer.cpp`,
`BufferQueueConsumer.cpp`.

**Third-party logs:** github.com/myers/openxr-vulkan-multiview-msaa (Quest 3, 120 Hz OpenXR VrApi lines),
github.com/RobertAldridge/purec (72 Hz lines).

---

## 6. Open questions, and audit of 01–03

### 6.1 Open questions

1. What is the real acquire moment inside `com.oculus.vrruntimeservice`? Is it at the first-eye slice (model),
   earlier, or once per slice? → §4.2 trace, bracketed over 72/90/120 Hz. `[SPECULATION until traced]`
2. Is the Quest 2 split still 2 slices per frame on Horizon OS v70+?
   - Blog 2021: yes, at 72 Hz.
   - Quest 3 at 120 Hz shows `Preempt=480` = 4 per frame.
   - → Read `Preempt/FPS` on the owner's Quest 2 at 120 Hz.
3. Is the DPU WB-CAC path (lineptr −256) active on Quest 2 at `DSF=1.00`? If yes, the latch lead is ~2–3 ms, not T/2.
   → Look for `encoder_lineptr_callback` / `wb_trigger_headroom` in the trace.
4. Does the compositor keep refreshing surface content when the app's `xrEndFrame` is late (stale app frame)?
   → Stall the app loop on purpose and watch the video. `[SPECULATION]`
5. Which eye is "right" = first-scanned? The code naming says the right BLU flashes first. Physical eye mapping is
   `[INFERRED]`.
6. Can the shell uid read `/sys/class/drm/sde-crtc-0/*` under SELinux, and can perfetto enable `sde/*` / `drm/*`
   events on the retail build?

### 6.2 Audit of the older reports (01–03)

- ✔ **01 §1.2** "split in 2 … runs every 7ms" is verified verbatim (A VR Frame's Life, 2021-05-20).
- ✘ **01 §2.3 / §2.4 (models P vs T, "CFL example favours model P")** is superseded by the kernel.
  - Scan-out is a fixed 8.28 ms at every rate (VFP-stretched refresh).
  - The flash start is capped at end-of-active + 1200 lines.
  - Actual mid-flash after vsync: **120 Hz 8.0/11.35; 90 Hz 10.7/11.5; 72 Hz 11.6/11.6 (both eyes flash together).**
    Neither model P (72 Hz 13.1/17.2) nor model T (7.8/10.3) is right below 120 Hz.
  - The CFL agreement is reproduced here with the T/2 latch lead: 6.9 + 11.6 = 18.5 ms vs CFL_min 19.7.
- ✔ **03 §1.3** eye-1 7.9–8.1 ms and eye-2 11.3–11.5 ms at 120 Hz match this report.
  - ✘ Its scaled "≈12.9 ms at 90 Hz, ≈16 ms at 72 Hz" is too high. Kernel arithmetic gives a 11.1 ms (90) and 11.6 ms
    (72) eye-mean. 03's own caveat (VFP stretching) was the correct branch.
- ~ **03 §1.1** "lineptr 256 … hints that the compositor beam-races". The lineptr actually drives the **DPU writeback
  CAC** kick, which is not the GPU TimeWarp. Beam-racing by the compositor is supported instead by Meta's split-in-2
  statement and the VrApi schedule (§1.1).
- ✔ **pixelpilot-xr-final-review "replace-latest without SYNCHRONOUS_BIT"** is now backed by spec text + AOSP
  `mIsDroppable`. It is still unobserved on the device (open question 1).
