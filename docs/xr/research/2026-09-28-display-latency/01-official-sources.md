# Decode → photon on Quest 2: what the official sources say (fresh research, 2026-09-28)

**Question.** What sets the time from "MediaCodec finished a frame into the OpenXR Android-surface swapchain"
to "photons on the Quest 2 panel"? Which levers can an app pull to shorten it?

**Method.** This is primary-source research started from zero. On purpose, it does not read the repo's earlier
latency docs (compositor-phase, phase-lock-protocol, g2g-budget, decoder-levers, or the openipc-low-latency
project); those get audited against this file later. Sources used:
- the Khronos OpenXR 1.1 spec (downloaded 2026-09-28, header revision 1.1.51), plus the vendored headers;
- Meta Horizon developer docs and blogs, fetched 2026-09-28;
- AOSP `libs/gui` source (branch `main`) and the Android developer reference.
- In the app, only `app/xr/src/main/cpp/XrRuntime.cpp` was read.

**Tags.**
- **[PROVEN: src]**: stated explicitly in an official source.
- **[INFERRED: from …]**: deduced from proven facts; the chain is given.
- **[SPECULATION]**: a guess, with what would confirm it.

§1–§7 use only official sources: Khronos, Meta/Oculus docs and blogs, AOSP and Android docs, plus Meta's own
patent. Anything else is kept apart in §8.

Short keys used below:
- **SPEC** = https://registry.khronos.org/OpenXR/specs/1.1/html/xrspec.html. Anchors used: `#XR_KHR_android_surface_swapchain`,
  `#XR_FB_android_surface_swapchain_create`, `#XR_FB_display_refresh_rate`, `#XR_FB_swapchain_update_state_android_surface`,
  `#XR_EXT_performance_settings`, `#XR_META_performance_metrics`, `#rendering-frame-synchronization`, `#rendering-frame-submission`,
  `#rendering-compositing`, `#XR_KHR_android_thread_settings`, `#XR_ANDROID_performance_metrics`, `#XR_KHR_convert_timespec_time`.
- **HDR** = `repos/PixelPilot_quest/external/OpenXR-Headers/include/openxr/` (`openxr.h:29` = API 1.1.51).
- **APP** = `app/xr/src/main/cpp/XrRuntime.cpp`.

---

## TL;DR

1. **The compositor latches the surface buffer, not `xrEndFrame`.** The KHR spec says nothing about *when* the
   compositor takes a buffer from the surface. The only normative timing text is in the FB extension:
   - without `SYNCHRONOUS` the BufferQueue "always repl[aces] the last buffer" (mailbox);
   - with `USE_TIMESTAMPS` "the compositor should acquire the most recent buffer whose presentation timestamp is
     not greater than the expected display time of the **final composited frame**".

   Both texts describe a pick made per compositor frame, with no link to the app's `xrEndFrame`/`displayTime`
   [INFERRED: SPEC `#XR_FB_android_surface_swapchain_create`]. Meta also says compositor layers are drawn "at the
   framerate of the compositor … never lower than the frame rate of your application"
   [PROVEN: https://developers.meta.com/horizon/documentation/unity/os-compositor-layers/].

2. **The decode→photon floor at 120 Hz.** It is the sum of two parts:
   - (a) the wait until the next compositor latch: uniform over 0…8.33 ms, **mean ≈ 4.2 ms** while decode and
     compositor are not phase-locked;
   - (b) latch → mid-illumination, which **no official source quantifies**. Meta says only that the compositor
     applies its correction "just a few milliseconds before it will be displayed"
     [PROVEN: https://developers.meta.com/horizon/documentation/native/android/os-compositor/].

   Best estimate for the total: **≈ 9–16 ms mean at 120 Hz**, against ≈ 13–24 ms at 72 Hz [INFERRED/SPECULATION, §9].

3. **The refresh rate is the biggest app-side lever.**
   - Quest 2 supports 72/80/90/96/100/120 Hz, 60 Hz for media apps only, and also 76 Hz. Nothing above 120: rates
     above 120 are "exclusive to Meta Quest 3 … not available on any other headset"
     [PROVEN: https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/].
   - 120 Hz was once behind a user toggle ("Settings > Experimental Features > 120 Hz")
     [PROVEN: https://developers.meta.com/horizon/blog/oculus-developer-release-notes-v28/]. The current doc no
     longer mentions the toggle.
   - Thermal throttling can drop the rate to 72 Hz silently
     [PROVEN: https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/].

4. **Most "latency features" do not touch this path.**
   - Phase Sync, late latching, App SpaceWarp and TimeWarp all act on the *app's* rendered frames or on the pose.
   - A head-locked layer "bypass[es] TimeWarp"
     [PROVEN: https://developers.meta.com/horizon/documentation/unity/unity-ovroverlay/].
   - `SUSTAINED_HIGH` is already the spec default [PROVEN: SPEC `#XR_EXT_performance_settings`].
   - **No compositor-bypass path** (front buffer, direct scanout) exists in the OpenXR registry or in current
     Meta docs [INFERRED: registry extension list, §6].

5. **Two app findings.** APP chains `XrAndroidSurfaceSwapchainCreateInfoFB` with `createFlags = 0`
   (APP:309). The spec says "**createFlags must not be 0**" [PROVEN: SPEC `#XR_FB_android_surface_swapchain_create`,
   Valid Usage]. APP also never handles `XrEventDataDisplayRefreshRateChangedFB` (APP:358-375).

---

## 1. Quest 2 refresh rates

| Claim | Tag |
|---|---|
| Supported rates on Quest 2, per the current table: 60 Hz "Media apps only", then 72, 80, 90, 96, 100, 120 Hz. | [PROVEN: https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/ (Updated Aug 27, 2026); same table at https://developers.meta.com/horizon/documentation/unreal/unreal-change-display-refresh-rate/] |
| "Quest 2, Quest Pro, Quest 3, and Quest 3S all support 76 Hz" (not listed in the enumeration). | [PROVEN: same native doc] |
| The default rate is 72 Hz. | [PROVEN: same doc] |
| **Nothing above 120 Hz on Quest 2.** "Meta Quest 3 supports display refresh rates above 120 Hz, up to 240 Hz. This is exclusive to Meta Quest 3. It is not available on Meta Quest 3S, and it is not available on any other headset." | [PROVEN: same doc, section "Meta Quest 3 extended refresh rates"] |
| 120 Hz on Quest 2 was introduced in v28 as experimental. The release notes say it applies "on devices where users have enabled Settings > Experimental Features > 120 Hz". | [PROVEN: https://developers.meta.com/horizon/blog/oculus-developer-release-notes-v28/] |
| The current refresh-rate doc lists 120 Hz for Quest 2 and **does not mention** any toggle. I found no official Meta release note that removes the toggle. | [PROVEN (absence in the current doc); removal date not found] |
| `xrRequestDisplayRefreshRateFB` with a value that is not 0.0 and not enumerated: "The runtime must return XR_ERROR_DISPLAY_REFRESH_RATE_UNSUPPORTED_FB". 0.0 means "no preference". | [PROVEN: SPEC `#XR_FB_display_refresh_rate`; HDR `openxr.h:217`] |
| An enumerated value is "only a request and does not guarantee the system will switch to the requested display refresh rate". | [PROVEN: SPEC `#XR_FB_display_refresh_rate`] |
| The enumeration is sorted low→high and is identical for the whole session. | [PROVEN: SPEC] |
| Meta says requesting non-enumerated values "is allowed on supported devices". This contradicts the spec's "must return …UNSUPPORTED". | [PROVEN (both texts); how the runtime actually behaves = device test] |
| **Silent lowering happens.** "If an app with a display refresh rate higher than 72 Hz experiences thermal events, dynamic throttling may change the refresh rate to 72 Hz as a first step. If thermal conditions worsen, dynamic throttling may take an additional step to change frame rate while maintaining the refresh rate (the equivalent of minVsyncs=2)." | [PROVEN: native refresh-rate doc] |
| Throttling can be simulated with `adb shell am broadcast -a com.oculus.vrruntimeservice.COMPOSITOR_SIMULATE_THERMAL --es subsystem refresh --ei seconds_throttled 10`. | [PROVEN: same doc] |
| Read the actual rate with `xrGetDisplayRefreshRateFB`. Changes arrive as `XrEventDataDisplayRefreshRateChangedFB{fromDisplayRefreshRate,toDisplayRefreshRate}`. | [PROVEN: SPEC `#XR_FB_display_refresh_rate`; HDR `openxr.h:481`] |
| The spec itself warns: "Increasing the display refresh rate … can lead to thermal degradation." | [PROVEN: SPEC, Issues] |
| Battery saver is reported as `LP=` and the power level as `PLS=` (NORMAL/SAVE/DANGER) in the VrApi logcat line. | [PROVEN: https://developers.meta.com/horizon/documentation/unity/ts-logcat-stats/] |
| No official source says whether battery saver lowers the refresh rate. | [SPECULATION; device test] |
| **APP:** picks the highest enumerated rate ≤ the requested one (APP:507-510). It polls `xrGetDisplayRefreshRateFB` every 30 frames (APP:489-491, 551). It does **not** handle the refresh-rate-changed event (APP:358-375 handle only session-state and instance-loss events). | [PROVEN: APP lines] |

## 2. Android-surface swapchain: when the compositor takes the buffer

| Claim | Tag |
|---|---|
| The KHR extension provides "a special swapchain that uses an android.view.Surface as its producer end". Size is "controlled by the producer and possibly changes at any time". Only `xrDestroySwapchain` may be called on it. | [PROVEN: SPEC `#XR_KHR_android_surface_swapchain`; HDR `openxr_platform.h:53-58`] |
| **The KHR text contains no statement about when the compositor latches the buffer**, and none about `displayTime`. | [PROVEN (absence): SPEC `#XR_KHR_android_surface_swapchain`] |
| Writing to the surface outside VISIBLE/FOCUSED is undefined. Before `xrEndSession` the app must ensure that no thread is writing. | [PROVEN: SPEC] |
| `SYNCHRONOUS_BIT`: "the underlying BufferQueue should be created in synchronous mode, allowing multiple buffers to be queued instead of always replacing the last buffer. Buffers are retired in order, and the producer may block until a new buffer is available." | [PROVEN: SPEC `#XR_FB_android_surface_swapchain_create`; HDR `openxr_platform.h:609`] |
| So without SYNCHRONOUS the default is "always replacing the last buffer", i.e. mailbox. | [INFERRED: from the SYNCHRONOUS definition above] |
| `USE_TIMESTAMPS_BIT`: "the compositor should acquire the most recent buffer whose presentation timestamp is not greater than the expected display time of the final composited frame." | [PROVEN: SPEC; HDR `openxr_platform.h:610`] |
| USE_TIMESTAMPS makes the compositor **hold** a buffer stamped later than the expected display time of the compositor frame it is building. It can never make a buffer appear *earlier*. So it can only add latency, of up to one refresh or more, and never removes any. Its purpose is pacing. | [INFERRED: from the USE_TIMESTAMPS definition + AOSP `BufferQueueConsumer::acquireBuffer`, §7] |
| "Expected display time of the final composited frame" names the **compositor's** frame, not the app's `XrFrameEndInfo::displayTime`. So the acquire happens per compositor frame. | [INFERRED: spec wording; consistent with Meta's "compositor layers … at the framerate of the compositor"] |
| Valid Usage: "createFlags must not be 0". **APP:309** sets `createFlags = useTimestamps ? USE_TIMESTAMPS_BIT : 0` and always chains the struct (APP:305-311). That is a VU violation whenever timestamps are off. | [PROVEN: SPEC VU + APP lines] |
| On Quest, the VU violation is probably ignored at runtime (the app works). The fix is to chain the struct only when a flag is set. | [SPECULATION; the validation layer would flag it] |
| Timestamp clock: `XR_KHR_convert_timespec_time` defines conversion between XrTime and a timespec "obtained from clock_gettime with CLOCK_MONOTONIC". | [PROVEN: SPEC `#XR_KHR_convert_timespec_time`] |
| Whether Meta compares the buffer timestamp against XrTime or CLOCK_MONOTONIC is unknown; System.nanoTime() = CLOCK_MONOTONIC. | [SPECULATION; test by converting XrTime↔timespec on device] |
| `XR_FB_swapchain_update_state_android_surface` only sets or reads the buffer default **size** (and the source of truth for `imageRect`). It has no timing semantics. | [PROVEN: SPEC `#XR_FB_swapchain_update_state_android_surface`] |
| Meta docs on Android surfaces (Unity "Is External Surface"): it "allows the creation of Android Surface and lets Timewarp layer manage it … render the Surface texture directly to the TimeWarp layer". This confirms that the compositor (the "TimeWarp" thread), not the app, samples the surface. | [PROVEN: https://developers.meta.com/horizon/documentation/unity/unity-ovroverlay/] |
| **No Meta doc found that gives latency numbers for Android-surface swapchains.** | [PROVEN (absence), searches of 2026-09-28] |

## 3. OpenXR frame timing and Meta's latency features

| Claim | Tag |
|---|---|
| `xrWaitFrame` "throttles the application frame loop in order to synchronize application frame submissions with the display" and "returns a predicted display time for the next time that the runtime predicts a composited frame will be displayed". | [PROVEN: SPEC `#rendering-frame-synchronization`] |
| "predictedDisplayTime must refer to the **midpoint of the interval during which the frame is displayed**." `predictedDisplayPeriod` is "for use in predicting display times beyond the next one" and "may [differ] from the hardware's refresh cycle". | [PROVEN: SPEC, XrFrameState] |
| On a low-persistence panel, the "interval during which the frame is displayed" is the backlight flash. So predictedDisplayTime ≈ mid-flash. | [INFERRED: SPEC midpoint rule + §4 low-persistence facts] |
| "The runtime may dynamically adjust the start time of the frame interval relative to the display hardware's refresh cycle to minimize graphics processor contention between the application and the compositor." | [PROVEN: SPEC] |
| On Meta, "With OpenXR, PhaseSync is always enabled and xrWaitFrame will take on the responsibility of frame synchronization and latency optimization". | [PROVEN: https://developers.meta.com/horizon/blog/a-vr-frames-life/] |
| Phase Sync aims "to have the frame finish rendering right before our compositor needs the completed frame". Measured gain: "a 10 milliseconds latency reduction in Oculus Home with Quest 2". It "has an insurance padding". | [PROVEN: https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/] |
| How far ahead predictedDisplayTime is on Meta: VrApi `Prd` = "the absolute time between when an app queries the pose before rendering and the time the frame is displayed on the HMD screen". The example line shows `Prd=38ms` at 72 Hz. An older blog says it "should almost always be a fixed number between 40 and 50 ms". | [PROVEN: https://developers.meta.com/horizon/documentation/unity/ts-logcat-stats/ ; https://developers.meta.com/horizon/blog/ovr-metrics-tool-vrapi-what-do-these-metrics-mean/] |
| No official number for OpenXR at 120 Hz. | [SPECULATION; measure `predictedDisplayTime − now` right after `xrWaitFrame`] |
| `CFL=` = "Minimum/maximum compositor frame latency … the amount of time in the Prd= measurement that is spent in the OS compositor, which prepares your submitted frame for display". The example is `CFL=19.74/21.66`, `ICFLp95=20.94`, device not stated, FPS=72. | [PROVEN: ts-logcat-stats] |
| CFL measures from the app's frame submission, not from the compositor's latch of a surface buffer. So it is an upper bound on the compositor-side part of the app path, not the surface latch→photon time. | [INFERRED: from the CFL definition "your submitted frame"] |
| **Does the app's Phase Sync / Prd pipeline add to Android-surface latency? Not directly.** The surface buffer is latched per compositor frame (§2), and compositor layers update at the compositor rate even when the app misses frames. So the video's latency is decoupled from the app's `predictedDisplayTime` depth. | [INFERRED: §2 USE_TIMESTAMPS wording + https://developers.meta.com/horizon/documentation/unity/os-compositor-layers/ ("Compositor layer elements in load screens always appear to update at full frame rate because the compositor runs at framerate even if the application fails to submit frames on time")] |
| The app must still resubmit the layer every frame: "All composition layers to be drawn must be submitted with every xrEndFrame call." | [PROVEN: SPEC `#rendering-compositing`] |
| Late latching = "updates head and controller tracking poses at the last possible moment before rendering begins". It is a pose-into-GPU-buffer technique for app rendering, so it is irrelevant to an app with no render pass. | [PROVEN definition: https://developers.meta.com/horizon/documentation/unity/unity-openxr-settings-quest/ ; irrelevance INFERRED] |
| TimeWarp "rotates the most recently completed frame to account for head rotation … the compositor corrects for this just a few milliseconds before it will be displayed". | [PROVEN: https://developers.meta.com/horizon/documentation/native/android/os-compositor/] |
| "Head-locked overlays bypass TimeWarp and exactly follow head motion." | [PROVEN: https://developers.meta.com/horizon/documentation/unity/unity-ovroverlay/] |
| So TimeWarp neither adds to nor removes from decode→photon for a VIEW-space quad. The same compositor pass still draws the quad, with distortion correction, so its GPU time still counts. | [INFERRED: from the two rows above + frames-life "Layer Composition / TimeWarp / Distortion Correction" steps] |
| App SpaceWarp "allows an app to render at half-rate … designed to only run on one Compositor layer". It has nothing to act on without a projection layer. | [PROVEN: https://developers.meta.com/horizon/documentation/unity/os-app-spacewarp/ ; irrelevance INFERRED] |
| Unity's Meta settings describe `xrWaitFrame` as "Intelligently delays frame starts to give your app just enough time to complete rendering, minimizing motion-to-photon latency". | [PROVEN: https://developers.meta.com/horizon/documentation/unity/unity-openxr-settings/] |

## 4. Compositor pipeline depth, the panel, and motion-to-photon

| Claim | Tag |
|---|---|
| Out-of-process compositor: "an independent process, VR Compositor … gathering frame submission information from all clients and then compositing and displaying". | [PROVEN: https://developers.meta.com/horizon/blog/a-vr-frames-life/] |
| Stage 3 = Layer Composition → TimeWarp → Distortion Correction → other post-processing (CAC); then "the screen is lit up at PredictedDisplayTime". | [PROVEN: same] |
| "it runs on a higher priority context on the GPU and will interrupt any other workloads … On both Quest1 and Quest2, its per-frame work is split in 2 for latency optimisations, preempting your application usually twice per frame as it runs every 7ms." | [PROVEN: same] |
| "Split in 2 … every 7 ms" (≈ half of 13.9 ms at 72 Hz) points to per-half-screen (per-eye) composition timed against the scanout, i.e. a beam-racing-like scheme. If so, the latch may happen **twice per refresh**, once per half. | [SPECULATION: from the quote; Perfetto can show whether there are 2 acquire points per vsync] |
| Quest 2 panel: "5.46″ 773 PPI … 1920 RGB × 3664 … fast-switch LCD with low-persistence backlight". | [PROVEN: abstract of Meta's SID 2022 invited paper, https://sid.onlinelibrary.wiley.com/doi/abs/10.1002/sdtp.15410 (abstract quoted from search index; full text paywalled)] |
| Meta's patent on low-persistence LCD: "the backlight unit is activated after a set lag since the start of the frame". The lag depends on "the data transfer period, the data scanning period, and the transitional period". The patent covers both global ("all the pixels simultaneously illuminate") and segmented backlights. | [PROVEN (patent text, Meta Platforms Technologies, filed 2021-05-11): https://patents.google.com/patent/US11436987B1/en — this is a patent, **not** a statement that Quest 2 uses this exact scheme] |
| So on Quest 2 the photons come **after** the frame's data is scanned in and the LC has settled, near the end of the refresh period. Latch→photon is therefore at least the time to scan the rest of the frame plus LC settle plus half the flash. | [INFERRED: panel abstract + patent + SPEC midpoint rule] |
| Persistence duration (flash length) for Quest 2 is **not published** in any official source found. | [PROVEN (absence)] |
| Whether the backlight is global or segmented on Quest 2 is not officially stated. | [SPECULATION] |
| Meta's pose-latency statement for its own apps: Phase Sync gave −10 ms on Quest 2. Typical `Prd` (pose query → display) is 38–50 ms. That is app pose latency, not head-rotation M2P, which TimeWarp shortens to "a few milliseconds". | [PROVEN: phase-sync blog; logcat doc; os-compositor doc] |
| `XR_META_performance_metrics` lists `/perfmetrics_meta/app/motion_to_photon_latency`, `/compositor/gpu_frametime`, `/compositor/dropped_frame_count`, `/compositor/spacewarp_mode`, among others. The spec gives **no definition** of what each counter measures. "The application should not change its behavior based on the counter reads"; intervals are runtime-defined. | [PROVEN: SPEC `#XR_META_performance_metrics`] |
| For comparison only (a different runtime): Android XR's `XR_ANDROID_performance_metrics` defines `motion_to_photon_latency` as "time spent from user-initiated motion event to corresponding physical image update on the display". | [PROVEN: SPEC `#XR_ANDROID_performance_metrics`] |
| Rift PC analogue: "App Motion-to-Photon Latency — Latency from when the last predicted tracking information was queried … to when the middle scanline of the target frame is illuminated". | [PROVEN: https://developers.meta.com/horizon/documentation/native/pc/dg-hud/] |
| For an app that never queries a pose and renders nothing (APP:532-534 reads it), Meta's `app/motion_to_photon_latency` presumably follows the pose-query → mid-photon definition above. **It does not measure decode→photon.** | [INFERRED: definitions above + APP has no pose query] |

## 5. `XR_EXT_performance_settings` and related knobs

| Claim | Tag |
|---|---|
| Levels are POWER_SAVINGS(0) / SUSTAINED_LOW(25) / SUSTAINED_HIGH(50) / BOOST(75). "The XR Runtime shall select XR_PERF_SETTINGS_LEVEL_SUSTAINED_HIGH_EXT as the default hint if the application does not provide any." | [PROVEN: SPEC `#XR_EXT_performance_settings`; HDR `openxr.h:2258`] |
| **So APP:522-523 (SUSTAINED_HIGH on CPU and GPU) restates the default and is a no-op by spec.** | [INFERRED: from the default rule] |
| SUSTAINED_LOW "is allowed to take measures to reduce power, such as increasing latencies or reducing headroom". POWER_SAVINGS: "low latency [is] not needed". Both must be avoided. | [PROVEN: SPEC] |
| BOOST is allowed "beyond the thermally sustainable range … short-term durations (< 30 seconds)". It raises the risk of the thermal throttle to 72 Hz (§1). | [PROVEN: SPEC; thermal link INFERRED from §1 throttling text] |
| Meta clock levels are logged as `CPU4/GPU=…` and by `XrPerformanceManager SetClockLevels`; `debug.oculus.clockStateLogLevel 1` shows the min/max reasons. | [PROVEN: ts-logcat-stats] |
| The compositor runs in its own process on a high-priority GPU context that preempts apps (§4). App CPU/GPU levels should therefore barely move its timing. | [INFERRED: frames-life blog; not measured] |
| Compositor layer costs on Quest 2 at CPU/GPU level 4: "every additional compositor layer costs about 0.1ms" and "a fullscreen compositor layer costs about 0.6ms". "The compositor additionally merges headlocked FIXED_TO_VIEW layers using the QUAD shape into 1 layer. Merged layers have no additional per-layer cost." | [PROVEN: https://developers.meta.com/horizon/documentation/unity/os-compositor-layers/] |
| ATW GPU time (`TW=`) "directly correlates to the number of layers … with equirect and cylinder layers being more expensive on the GPU than quad and projection layers". | [PROVEN: ts-logcat-stats] |
| `LCnt=N(DRxx,LMn)` reports "the Direct Render FPS (used for rendering overlay layers)" and the merged-layer count. | [PROVEN: ts-logcat-stats] |
| Whether a merged head-locked overlay group is pre-rendered into an intermediate texture at "DR" fps is undocumented. If it were, and DR were below the refresh rate, it would add a stage. | [SPECULATION; check `LCnt` DR while the video plays] |
| `XR_FB_composition_layer_settings` (super-sampling/sharpening) adds per-layer compositor filtering. That means compositor GPU cost and no latency benefit. | [PROVEN definition: SPEC `#XR_FB_composition_layer_settings`; cost INFERRED] |
| Fixed foveated rendering and dynamic resolution act on app eye buffers. With no projection layer they do nothing. | [INFERRED: ts-logcat-stats FFR definition] |
| `XR_KHR_android_thread_settings`: "these threads must be identified to the system, which will adjust their scheduling priority". Types: APPLICATION_MAIN = time-critical CPU; RENDERER_MAIN = time-critical graphics. | [PROVEN: SPEC `#XR_KHR_android_thread_settings`] |
| APP:520 marks the frame-loop thread RENDERER_MAIN. The decode-output thread (the one calling `releaseOutputBuffer`) is a candidate for APPLICATION_MAIN. The expected effect is sub-ms jitter only. | [INFERRED; unmeasured] |

## 6. Is there any compositor-bypass path?

| Claim | Tag |
|---|---|
| The OpenXR 1.1 registry lists **no** extension for front-buffer rendering, direct scanout or compositor bypass. The FB/META/OCULUS extensions present are listed in the extension index (e.g. passthrough, composition_layer_*, display_refresh_rate, space_warp, local_dimming, performance_metrics…). | [INFERRED: extension list of SPEC as of 2026-09-28] |
| On Meta, all client output goes through the out-of-process compositor: "gathering frame submission information from all clients and then compositing and displaying". | [PROVEN: frames-life blog] |
| The VrApi/Mobile SDK (where Gear-VR-era front-buffer modes lived) is deprecated: "As of August 31, 2022, Mobile SDK and the VrApi library are no longer supported … New apps will not have access". | [PROVEN: https://developers.meta.com/horizon/documentation/native/android/mobile-phase-sync/ banner] |
| `XR_FB_passthrough` and similar are compositor layers themselves, not bypasses. | [INFERRED: SPEC; passthrough is composited] |
| "Direct Render" in `LCnt` is a compositor-internal overlay path, not an app-accessible bypass. | [INFERRED: definition text §5] |
| **Conclusion: no documented path lets an app bypass the Quest compositor.** The Android-surface swapchain is already the shortest documented path, because it has no app render pass and no copy (the buffer is passed by handle). | [INFERRED: above + AOSP "Buffer contents are never copied by BufferQueue … buffers are always passed by a handle", https://source.android.com/docs/core/graphics/arch-bq-gralloc] |

## 7. AOSP: BufferQueue behavior and MediaCodec timestamps

| Claim | Tag |
|---|---|
| In `BufferQueueProducer::queueBuffer`, a queued item is *droppable* iff `mAsyncMode \|\| (mConsumerIsSurfaceFlinger && mQueueBufferCanDrop) \|\| (mLegacyBufferDrop && mQueueBufferCanDrop) \|\| shared-slot`. When the last queued item is droppable, the new buffer **overwrites** it ("Overwrite the droppable buffer with the incoming one"). Otherwise it is appended. | [PROVEN: https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/libs/gui/BufferQueueProducer.cpp (lines ~1066-1130)] |
| At `connect`: `mQueueBufferCanDrop=false`, `mLegacyBufferDrop=true`. They become `mQueueBufferCanDrop = mDequeueTimeout <= 0` only if both the consumer and the producer are "controlled by app". So for a **non-SurfaceFlinger consumer**, replace-last requires the consumer to set async mode, or that both-app-controlled condition. | [PROVEN: same file (~1440-1447); `BufferQueueCore.cpp:108-125` defaults] |
| That the non-SYNCHRONOUS Quest surface replaces the last buffer is therefore Meta's configuration of its consumer, which the FB spec text guarantees (§2). | [INFERRED: spec + AOSP mechanism] |
| `BufferQueueConsumer::acquireBuffer(expectedPresent)`: if `expectedPresent` is given, earlier buffers are dropped while the next one is "timely" (timestamp ≤ expectedPresent and ≥ expectedPresent − 1 s). This is skipped for auto-timestamps. A front buffer stamped later than expectedPresent (by less than 1 s) gets `PRESENT_LATER` (held). Timestamps more than 1 s off are treated as "garbage" and shown at once, without drops. | [PROVEN: https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/libs/gui/BufferQueueConsumer.cpp (lines ~124-235)] |
| The FB `USE_TIMESTAMPS` wording matches this `expectedPresent` logic. | [INFERRED: matching semantics; Meta source not public] |
| MediaCodec: since API 23, `releaseOutputBuffer(id, true)` renders with "the presentation timestamp of the buffer (converted to nanoseconds)". `releaseOutputBuffer(id, ns)` sets the surface timestamp explicitly. The NDK `AMediaCodec_releaseOutputBufferAtTime` does the same ("see the Java documentation"). | [PROVEN: https://developer.android.com/reference/android/media/MediaCodec ; https://developer.android.com/ndk/reference/group/media] |
| **Who honors the timestamp.** The Java doc describes only SurfaceView: shown "at the VSYNC at or after the buffer timestamp … within one (1) second … if multiple buffers are sent to the Surface to be rendered at the same VSYNC, the last one will be shown … if the timestamp is not 'reasonably close' … display the buffer at the earliest feasible time. In this mode it will not drop frames." For other consumers: "The timestamp may have special meaning depending on the destination surface." | [PROVEN: MediaCodec reference] |
| On Quest, only an Android-surface swapchain created with USE_TIMESTAMPS is specified to honor it (§2). Without that flag, no source says the compositor looks at the timestamp. | [INFERRED] |
| If USE_TIMESTAMPS is used with `releaseOutputBuffer(true)`, the stream PTS (not System.nanoTime) becomes the timestamp. By the AOSP rule it is more than 1 s from expectedPresent, so it counts as "garbage" and is shown at once. USE_TIMESTAMPS then changes nothing, provided Meta uses the stock rule. | [INFERRED/SPECULATION: AOSP rule; Meta's consumer unknown] |
| Surface drop policy: "Since Build.VERSION_CODES.Q the default behavior is to drop excessive frames. Applications can opt out … for non-View surfaces … setting the key MediaFormat.KEY_ALLOW_FRAME_DROP to 0". Keep the default. | [PROVEN: MediaCodec reference, "Using an Output Surface"] |
| **167 fps into a 120 Hz mailbox consumer.** Frames arrive every 5.99 ms and latches come every 8.33 ms. So ~28 % of decoded frames are replaced before any latch (1 − 120/167). Each latch takes the newest one, which is on average ~3 ms old at the latch. No queue builds up. | [INFERRED: arithmetic on the replace-last rule] |
| **The same stream in SYNCHRONOUS mode.** The queue grows by 47 frames/s until the producer blocks on `dequeueBuffer` ("the producer may block until a new buffer is available"). Latency then grows to (queue depth) × 8.33 ms, and the decoder is back-pressured. | [INFERRED: SPEC SYNCHRONOUS text + MediaCodec "it will eventually block the decoder"] |
| The acquire fence ("The sync framework controls how buffers move") means a buffer can be latched before the decoder hardware has finished writing it. The compositor's GPU then waits on the fence. | [PROVEN: arch-bq-gralloc doc wording; effect on the latch INFERRED] |

---

## 8. Non-official sources (kept apart; only corroboration)

| Claim | Source |
|---|---|
| 120 Hz on Quest 2 was user opt-in from April 2021. John Carmack (then Meta consulting CTO) wrote in Sept 2022: "we are finally going to make it default-on". The mode "only kicks in when apps explicitly ask for it". | https://www.uploadvr.com/quest-2-120hz-no-longer-experimental/ ; https://mixed-news.com/en/meta-quest-2-120-hertz-mode-becomes-a-standard-feature/ |
| At Display Week 2022, Meta's engineer Cheon Hong Kim gave the talk "High-PPI Fast-Switch Display Development for Oculus Quest 2 VR Headsets". Panel: 100 nits in low-persistence mode. Fast-switch panels "illuminate the backlight for a fraction of the frame, after waiting for the liquid crystal to 'settle down'". | https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/ |
| Quest 3 extended rates (207 Hz standard, 240 Hz in dev mode with display scaling) arrived in Horizon OS 2.7. This matches the official "Quest 3 only" statement. | https://www.uploadvr.com/qhorizon-os-2-7-adds-gamepad-emulation-and-207-hz-display-mode-240-hz-in-dev-mode/ |
| Forum report: in some cases `xrEnumerateDisplayRefreshRatesFB` returned only 60/72 on Quest 2, traced to a compatibility-mode setting. | https://communityforums.atmeta.com/discussions/dev-quest/openxrs-xr-fb-display-refresh-rate-extension-only-returns-60hz-and-72hz-for-ques/1237082 (search snippet only; page did not render) |
| Independent MTP benchmarks (OptoFidelity) cover Quest 3/AVP. No Quest 2 decode→photon or persistence number found. | https://www.optofidelity.com/insights/blogs/apple-vision-pro-bencmark-test-2.-angular-motion-to-photon-latency-in-vr |

---

## 9. Levers: expected effect on decode→photon at 120 Hz

**Working model** [INFERRED: §2, §3, §4, §7]:
`decode→photon = W + L`, where
- `W` = wait from queueBuffer to the compositor's acquire. It is uniform over [0, P) when not phase-locked, so mean P/2. At P = 8.33 ms that is ≈ 4.2 ms.
- `L` = acquire → mid-flash, which is unknown. It is at least (remaining scanout + LC settle + ½ flash). The plausible range is
  0.6–1.4 × P, i.e. **5–12 ms at 120 Hz** [SPECULATION].

Total mean ≈ **9–16 ms at 120 Hz** and ≈ **13–24 ms at 72 Hz** (P = 13.9 ms) [SPECULATION on L; INFERRED on W].

| Lever | Mechanism | Expected Δ decode→photon at 120 Hz (reasoning) | Confidence | Source |
|---|---|---|---|---|
| Run at 120 Hz rather than 72 (and confirm it is granted) | A shorter P shrinks both W (P/2) and L (∝ P if L is scanout-bound). | vs 72 Hz: W −2.8 ms, L −2 to −7 ms, **total −5 to −10 ms**. vs 90 Hz: about −2 to −4 ms. | INFERRED (W), SPECULATION (L) | native refresh-rate doc; SPEC midpoint rule |
| Detect silent fallback to 72 Hz (thermal) or a denied 120 | Handle `XrEventDataDisplayRefreshRateChangedFB`, log `xrGetDisplayRefreshRateFB`, avoid BOOST | Saves the whole +5 to +10 ms regression when it happens. Otherwise it is invisible. | PROVEN mechanism | native refresh-rate doc; SPEC |
| Keep non-SYNCHRONOUS (mailbox) | The newest buffer replaces the pending one, so there is no queue | vs SYNCHRONOUS at 167→120 fps: avoids **+8.3 ms per queued buffer**, growing to the BufferQueue depth (e.g. 2–3 buffers = **+17–25 ms**) plus decoder back-pressure | PROVEN semantics / INFERRED size | SPEC FB flags; AOSP BufferQueueProducer |
| Do **not** use USE_TIMESTAMPS for latency | It can only defer a buffer stamped after the compositor frame's expected display time | Best case 0. Timestamps a little in the future: **+8.3 ms** or more per deferral. PTS (not nanoTime) stamps probably count as "garbage", so 0 | INFERRED | SPEC FB; AOSP BufferQueueConsumer |
| Fix `createFlags = 0` (chain the FB struct only when a flag is set) | Spec correctness | 0 ms expected; removes undefined behaviour | PROVEN (VU) | SPEC VU; APP:305-311 |
| Phase-align decode completion to the compositor latch (release frames just before the latch) | Lowers W from P/2 to about the safety padding | Up to **−3 to −4 ms** mean at 120 Hz (W from 4.2 ms to ~0.5–1 ms), plus lower jitter. Needs the latch phase and a stable source clock | INFERRED (arithmetic); latch phase needs measuring | Model above; SPEC `predictedDisplayTime`/period |
| Fewer layers; quad (not cylinder/equirect); no sharpening/supersampling | Less compositor GPU time (`TW`) | **−0.1 to −1 ms**, and only if the compositor starts later when it has less work (unknown) | PROVEN costs / INFERRED effect | os-compositor-layers; ts-logcat-stats |
| `XR_EXT_performance_settings` SUSTAINED_HIGH | It is already the spec default | **0 ms** | PROVEN default | SPEC |
| BOOST level | Higher clocks for < 30 s | ~0 ms for the compositor (separate high-priority context). Risks throttling to 72 Hz | INFERRED | SPEC; native refresh doc |
| Phase Sync / `xrWaitFrame` tuning | Moves the app's frame start, not the compositor's surface latch | **~0 ms** on the video path (always on in OpenXR anyway) | INFERRED | frames-life blog; phase-sync blog |
| Late latching, App SpaceWarp, TimeWarp, FFR, dynamic resolution | Act on poses and app eye buffers; head-locked layers bypass TimeWarp | **0 ms** | PROVEN (bypass) / INFERRED (rest) | ovroverlay; os-compositor; os-app-spacewarp |
| Thread hint APPLICATION_MAIN on the decode-output thread | Raises the scheduling priority of `releaseOutputBuffer` | **< 0.5 ms** (jitter tail only) | SPECULATION | SPEC thread_settings |
| Keep `KEY_ALLOW_FRAME_DROP` default (drop) | Prevents decoder back-pressure | Avoids unbounded growth; 0 in steady state | PROVEN | MediaCodec ref |
| Compositor bypass / front buffer / direct scanout | Not available | n/a | INFERRED (absence) | SPEC extension list; VrApi deprecation |
| Refresh above 120 Hz on Quest 2 | Not available | n/a | PROVEN | native refresh-rate doc |

## 10. Open questions that need a device measurement

1. **Which rates does the headset actually grant?** Record the `xrEnumerateDisplayRefreshRatesFB` list on this Quest 2 and OS version. Does it include 120 with no user toggle? Is 76 accepted outside the list? Do they agree with `xrGetDisplayRefreshRateFB` and the VrApi `FPS=x/y` line during a run?
2. **Where is the latch?** Find the acquire point(s) of the Android-surface BufferQueue relative to vsync in a Perfetto trace: one per refresh or two (the "split in 2, every 7 ms" quote)? What is its phase jitter?
3. **Latch → mid-photon (L) at 72/90/120 Hz.** This is the dominant unknown. It needs a photodiode on the lens plus a trace marker at the acquire. Bracket all three rates.
4. Is the Quest 2 backlight **global or segmented**, and how long is the flash? Photodiode at the top, middle and bottom of the panel.
5. Does the compositor re-acquire the surface on compositor frames where the **app missed `xrEndFrame`** (stale app frame)? Force app frame drops while the video plays.
6. What does **USE_TIMESTAMPS** do on Meta in practice? Which clock (XrTime vs CLOCK_MONOTONIC; check with `xrConvertTimeToTimespecTimeKHR`)? Does a PTS-based stamp count as "garbage"? Does it change the queue from mailbox to FIFO?
7. Does the runtime **reject or ignore** `createFlags = 0`? Run with the validation layer, then again with the struct omitted.
8. What do `/perfmetrics_meta/app/motion_to_photon_latency` and `CFL`/`ICFLp95` read for this no-render app at 120 Hz? Do they move with the refresh rate?
9. What is `LCnt=…(DRxx,LMn)` while the video plays? Is DR equal to the refresh rate? Are the video and stats quads merged (LM2)?
10. How far ahead is `predictedDisplayTime` (minus now) at 120 Hz? This is context for the app loop only.
11. What does the thermal throttle look like under a sustained 120 Hz video load? Measure time-to-throttle and whether the refresh-rate-changed event fires. Can it be reproduced with `COMPOSITOR_SIMULATE_THERMAL`?
12. With 167 fps input, confirm the measured drop fraction (~28 %) and the age of the latched frame from buffer frame numbers in the trace.
