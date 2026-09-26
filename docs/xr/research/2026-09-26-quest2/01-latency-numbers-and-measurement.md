# Meta Quest 2 as the display for an OpenIPC/PixelPilot FPV stream: where the display latency comes from, how big it is, and how to measure it

> Date: 2026-09-26. Independent research from primary sources (Meta developer docs and blogs, the SID papers,
> the Khronos OpenXR registry, Meta/Oculus patents, and the PixelPilot/ALVR/FPVue_xr source code, shallow-cloned locally).
> The older project notes were read **only after** this research was finished. They are audited in §7.
> Tags: `[PROVEN: source]` = read directly in a primary source or in code. `[INFERRED: from …]` = derived from
> proven facts. `[SPECULATION]` = hypothesis that still needs a measurement.
> **Nothing below has been measured on the owner's Quest 2 yet.** Every total is a model until the §5 protocol is run.

---

## 0. TL;DR

1. **The Quest 2 cannot fit inside a 20 ms glass-to-glass budget.** Its own display side alone
   (decoder frame ready → photons) is modelled at about **11 ms in the best case and about 16–33 ms typically**
   (depending on refresh rate and presentation path), before any camera, encode, link or decode time is added.
   Most of that is physics and pacing that no setting removes: the LCD has to finish scanning, the liquid crystal
   has to settle, and only then does the backlight flash. On top of that come compositor pacing waits.
   `[INFERRED: §2 + §3 model, cross-checked against Meta's CFL≈20 ms @72 Hz example]`
2. **The panel.** The Quest 2 uses **one fast-switch LCD with two backlights, one per eye**. Each eye's half of the
   panel is scanned, the LC settles, and then **that eye's backlight flashes for a short pulse**. The two eyes flash
   at different times. `[PROVEN: SID 2025 Quest 3S paper, which says Quest 3S "uses the same display system design as Quest 2"]`
   Meta's timing figure puts the first-eye flash at about 0.9–1.0 frame after scan start and the second-eye flash at
   about 1.2–1.3 frames. `[PROVEN figure / INFERRED scale: figure is schematic]`
3. **The path of a 2D panel app (PixelPilot).** Evidence says a 2D activity on Horizon OS runs on a **separate,
   non-default Android display that belongs to the panel container** `[PROVEN: amwatson/2DVrHybrid README]`, and that
   Horizon's **"custom compositor within XrRuntime"** produces the pixels of the headset view `[PROVEN: Meta MediaProjection doc]`.
   So PixelPilot's SurfaceView most likely goes: MediaCodec → **SurfaceFlinger composites the panel's virtual display
   (on the GPU; no overlay plane)** → the XR compositor takes it as a layer → per-eye compose → scan-out → per-eye flash.
   That is **two sampled buffering stages** plus the panel's fixed delay, against one stage for a native OpenXR layer.
   `[INFERRED — the exact topology is not published; §5 gives the dumpsys/Perfetto test that settles it]`
4. **The lowest-latency path Horizon OS offers for a video stream** is not PixelPilot's 2D panel. It is a native
   OpenXR app that makes its decoder output Surface **with `XR_KHR_android_surface_swapchain`**, so decoded frames go
   straight into a compositor quad layer with no SurfaceFlinger, no app GPU pass and no app frame loop.
   Meta Spatial SDK's `VideoSurfacePanelRegistration` ("direct-to-surface … only available with layers") is the same idea.
   `[PROVEN: Khronos + Meta Spatial SDK docs]` None of the three OpenIPC Quest clients checked here uses it
   `[PROVEN: grep of PixelPilot, FPVue_xr, PixelPilot_quest]`. Estimated saving versus the 2D panel: **~4–5 ms typical,
   up to ~11–17 ms worst case** `[INFERRED]`.
5. **Refresh rate is the biggest setting you can change.** Every waiting stage scales with the frame period, so going
   from 72 Hz to 120 Hz saves about **7–12 ms typical** in the proportional model `[INFERRED]`. The Quest 2 supports
   72/80/90/120 via `debug.oculus.refreshRate` (the documented list also has 60) `[PROVEN: Meta system-properties doc]`.
   It is unverified whether this property also retimes the Home/panel environment.
6. **PixelPilot version matters.** Only **v0.25.0 (2026-09-02)** both applies the MediaCodec low-latency keys and
   renders into a SurfaceView. **v0.24.0** (and any build with object detection on) renders into a **TextureView**
   (≈ +1 frame) and **v0.24.0 and older** never applied `low-latency` / `priority=0`.
   `[PROVEN: PRs #108/#113/#114 merge dates vs release dates]`
7. **No public glass-to-glass figure exists for PixelPilot on Quest 2.** The public Quest 2 streaming numbers found are
   either a Meta documentation example or an anecdotal forum overlay reading (§3). The protocol in §5 separates decode,
   compositor and panel with the owner's scope, photodiode and 480 fps phone.

---

## 1. The display path, stage by stage

### 1.1 What PixelPilot does with a decoded frame (read from source)

Upstream PixelPilot was shallow-cloned at `C:/xampp/htdocs/pixelpilot-xr/repos/PixelPilot` (commit `3d6ca17`, 2026-09-02).

- **Input side.** Every NALU is fed separately. Its presentation timestamp is set to "now" (steady_clock, µs) at the
  moment it is queued.
  `[PROVEN: app/videonative/src/main/cpp/VideoDecoder.cpp:228-232]`
- **Output side.** A dedicated thread blocks in `AMediaCodec_dequeueOutputBuffer` (17 ms timeout) and immediately
  calls `AMediaCodec_releaseOutputBuffer(codec, index, true)`. That is "render now", with no explicit render time.
  `[PROVEN: VideoDecoder.cpp:271,283; VideoDecoder.h:138]`
  With `render=true` and no timestamp, MediaCodec passes the buffer PTS on as the Surface timestamp. That PTS is the
  queue time on CLOCK_MONOTONIC, so it is already in the past, and SurfaceFlinger will present the buffer at its next
  latch instead of holding it. `[INFERRED: libc++ steady_clock = CLOCK_MONOTONIC; AOSP MediaCodec render-time fallback]`
- **Where the frame is drawn.** The decoder's output window is the Surface of a **SurfaceView** (`mainVideoSurface`)
  unless object detection is enabled, in which case it is a **TextureView**. VR mode uses two SurfaceViews.
  `[PROVEN: app/src/main/java/com/openipc/pixelpilot/VideoActivity.java:398-433; VideoDecoder.cpp:65]`
- **Decoder tuning.** The low-latency MediaCodec keys (`low-latency`, `vendor.qti-ext-dec-low-latency.enable`, …,
  `priority=0`) are set behind a user toggle that defaults to ON.
  `[PROVEN: helper/AndroidMediaFormatHelper.h:9-23; VideoActivity.java:173]`
  This only happens since PR #113, merged 2026-09-02T19:17Z, which is **after** the v0.24.0 tag (19:09Z). v0.25.0 is
  the first release with it. The TextureView regression (#108, merged 2026-08-11) was fixed by #114 (2026-09-02T20:53Z).
  `[PROVEN: gh pr view 108/113/114; gh release list]`
- **Receive queue.** Packet reordering holds a frame back for at most 20 ms (`MAX_BUFFER_AGE`) and only when a
  sequence gap appears. That is a loss-case cost, not steady-state latency.
  `[PROVEN: BufferedPacketQueue.h, MAX_BUFFER_AGE]`
- **Manifest.** PixelPilot is a plain Android activity: no OpenXR, no VR category, no Spatial SDK. On Horizon OS it
  therefore runs as a **2D panel**.
  `[PROVEN: app/src/main/AndroidManifest.xml]`
- **What the OSD "ms" number means.** It is `avgParsingTime + avgWaitForInputBuffer + avgHWDecodingTime`. The HW decode
  part runs from `queueInputBuffer` to `dequeueOutputBuffer`.
  `[PROVEN: videonative/.../DecodingInfo.java:42; VideoDecoder.cpp:283-288]`
  - It covers **nothing after `releaseOutputBuffer`**: no SurfaceFlinger, no compositor, no panel.
  - When a frame arrives as several slices, the codec may report the PTS of the first slice. In that case the number
    also includes waiting for the rest of the frame to arrive. `[SPECULATION — codec-dependent]`

### 1.2 What happens after the SurfaceView on Horizon OS

**Proven facts**

- The Horizon OS VR runtime uses **Out-of-Process Composition**: a separate VR Compositor process gathers frames from
  every client, composites them and displays them. The same compositor does layer composition, TimeWarp, distortion
  correction and chromatic-aberration correction. `[PROVEN: Meta blog "A VR Frame's Life", 2021]`
- The compositor's work "is split in 2 for latency optimisations … as it runs every 7ms" on both Quest 1 and Quest 2.
  At 72 Hz that is half a frame. `[PROVEN: same blog]`
- Its screen content is produced by "our own compositor … custom compositor within XrRuntime". On Horizon OS the
  MediaProjection surface is "populated directly by our own compositor", unlike stock Android where a VirtualDisplay
  fills it. `[PROVEN: Meta MediaProjection doc]`
- A 2D activity launched normally "was launching on some random display, likely part of the container", not on
  Display 0. A VR activity must be launched explicitly on Display 0 to escape the 2D container.
  `[PROVEN: github.com/amwatson/2DVrHybrid README (observed logcat behaviour)]`

**Most likely topology** `[INFERRED from the four facts above]`

```
MediaCodec (Venus HW decoder)
  └─ releaseOutputBuffer(render) ──► SurfaceView BufferQueue            (stage A: sampled by SurfaceFlinger)
        └─ SurfaceFlinger composites the panel's *virtual* display on the GPU (RenderEngine) into the
           virtual-display output buffer                                (c_sf ≈ 1–3 ms GPU)
              └─ output BufferQueue ──► XR compositor panel layer       (stage B: sampled by the compositor)
                    └─ per-eye compose (TimeWarp/distortion/CAC), split in 2 halves per frame
                          └─ DSI scan-out: eye 1 half, then eye 2 half
                                └─ LC settle ──► eye-1 backlight flash … eye-2 backlight flash ──► photons
```

**Consequences**

- **The overlay-plane advantage of SurfaceView does not exist here.** A virtual display has no scan-out hardware plane
  in the usual AOSP setup, so SurfaceFlinger composites it on the GPU.
  `[INFERRED: AOSP virtual displays are GPU-composed unless HWC supports virtual-display composition — SPECULATION for Horizon]`
- **SurfaceView is still better than TextureView.** A TextureView adds the app's own HWUI RenderThread pass before
  SurfaceFlinger. That is a further sampled stage of about ½–1 frame. `[INFERRED: Android view architecture; PixelPilot PR #114 text]`

**Alternative topology** `[SPECULATION]`: Horizon hands the panel's individual layers straight to the compositor
(stage A would then disappear). No primary source says this happens for ordinary 2D apps. The §5.3 test can tell the
two apart.

### 1.3 The native OpenXR alternatives

| Path | Stages after decode | Status |
|---|---|---|
| **(N1) Android-surface swapchain**: `xrCreateSwapchainAndroidSurfaceKHR` gives a `Surface` that MediaCodec renders into, attached to an `XrCompositionLayerQuad` | decoder → compositor layer (one sampled stage, no app GPU) | Spec: the swapchain is fed "with ordinary Android APIs"; acquire/wait/release are not used `[PROVEN: Khronos XR_KHR_android_surface_swapchain]`. Meta Spatial SDK `VideoSurfacePanelRegistration` = "direct-to-surface rendering, only available with layers" `[PROVEN: Meta Spatial SDK docs]`. **No OpenIPC Quest client uses it** `[PROVEN: grep]` |
| **(N2) SurfaceTexture → GL → eye buffer / quad swapchain** | decoder → SurfaceTexture → app latches in its xrWaitFrame loop → render → submit → compositor | Used by the `PixelPilot_quest` fork (`samplerExternalOES`, `updateTexImage`) `[PROVEN: repos/PixelPilot_quest/app/xr/src/main/cpp/openxr_app.cpp:1248; vr/CurvedScreenGLView.java:159]` |
| **(N3) CPU copy**: `getOutputBuffer` → OpenCV RGB→RGBA → texture upload | slowest: memory copy + colour conversion + upload | FPVue_xr (StereoKit POC, 2024) `[PROVEN: repos/FPVue_xr/app/src/main/cpp/app.cpp:57,177; videonative/VideoDecoder.cpp:217,229]` |

- The compositor itself is mandatory in every path: an OpenXR app never writes to the display directly.
  `[PROVEN: OpenXR spec composition model; Meta blog above]`
- What varies between paths is **how many sampled stages sit in front of it**.

---

## 2. Quest 2 panel timing (from first principles plus Meta's own papers)

### 2.1 What is proven

- The Quest 2 panel is a 5.46″ fast-switch LCD, 1920×3664, 773 ppi, **100 nits with low persistence**, 120 Hz maximum.
  "Illuminate the backlight for a fraction of the frame, after waiting for the liquid crystal to settle."
  `[PROVEN: Meta, SID Display Week 2022 invited paper 6-2 (Kim), via UploadVR 2022-05-17]`
- **Architecture: one LCD, two separate backlights (one per eye), two Fresnel lenses.** Quest 3S "leverages the proven
  display and optical design of the Quest 2". "Although the Quest 3S uses the same display system design as Quest 2, …
  we have achieved the latency performance 14% better than Quest 2."
  `[PROVEN: SID 2025 Digest 39-4 (J. Xiang, Meta), pp. 523-524, https://sid.org/Portals/sid/Files/SID-Digest/docs/39-4.pdf]`
- The same paper names the levers for display latency in LCD HMDs: panel scan time, backlight on-time, LC response and
  backlight timing. "With longer LC settle time, display ghosting performance is better, and inherently increases the
  latency." The backlight delay is temperature-dependent. `[PROVEN: same]`
- **Fig. 2** ("typical display timing scheme in LCD HMDs"): `t_scan` → `t_BLU_delay` (LC settle) → `t_BLU_on`.
  The global flash for an area happens only after its last line has settled. `[PROVEN: same, Fig. 2]`
- **Fig. 3** (Quest 3S backlight timing): "right active" (scan) → "right settle" → **r blu**; "left active" starts when
  the right scan ends → "left settle" → **l blu**. A "blu offset" separates the two flashes. `[PROVEN: same, Fig. 3]`
- An Oculus patent (now Meta) gives example numbers: scan-out "3 ms for the entire rows"; LC "may take 6 ms to
  transition"; "illumination time period is 2 ms"; "frame time is 11 ms (∼90 Hz)"; the backlight is lit "during a
  portion of a frame time (e.g., 20%)", after the whole frame has been scanned and the LCs have finished transitioning.
  `[PROVEN: US20170287409A1 — example values of a 2016 design, not a Quest 2 spec]`
- Refresh rates the Quest 2 supports: 72, 80, 90, 96, 100 and 120 Hz; 60 Hz is for media apps only; 76 Hz also works.
  `[PROVEN: Meta "Set Display Refresh Rates" doc, updated 2026-08-27]`
- The system property `debug.oculus.refreshRate` accepts 60/72/80/90/120 on Quest 2.
  `[PROVEN: Meta ts-systemproperties doc]`

### 2.2 Numbers read off Fig. 3

The figure is schematic ("not to scale" is **not** stated, but it is a sketch). Positions were measured in pixels
relative to one frame period F. `[PROVEN figure; INFERRED fractions]`

| Event (relative to scan start of eye 1) | Fraction of F |
|---|---|
| Eye-1 (right) scan | 0 → 0.38 F |
| Eye-1 settle | 0.38 → 0.81 F |
| **Eye-1 flash** | **0.90 → 0.98 F** (centre 0.94 F) |
| Eye-2 (left) scan | 0.38 → 0.77 F |
| Eye-2 settle | 0.77 → 1.20 F |
| **Eye-2 flash** | **1.19 → 1.28 F** (centre 1.24 F) |
| Flash width (≈ persistence) | ≈ 0.08 F |
| Eye-to-eye offset | ≈ 0.30 F |

### 2.3 Scan start → mid-flash for each refresh rate

Two bracketing models, because it is unknown whether the Quest 2 panel scans and settles in a **fixed time in
milliseconds** (model T, anchored at 120 Hz) or in a time **proportional to the frame** (model P).
`[INFERRED: model P = Fig. 3 scaled; model T = LC physics is ms-fixed. Both SPECULATION until photodiode]`

| Refresh | F (ms) | Model P eye-1 / eye-2 / mean | Model T eye-1 / eye-2 / mean | Persistence (P: 0.08 F) | Eye skew |
|---|---|---|---|---|---|
| 72 Hz | 13.9 | 13.1 / 17.2 / **15.1** | 7.8 / 10.3 / **9.1** | ~1.1 ms | 4.2 ms (P) |
| 90 Hz | 11.1 | 10.4 / 13.8 / **12.1** | 7.8 / 10.3 / **9.1** | ~0.9 ms | 3.3 ms (P) |
| 120 Hz | 8.33 | 7.8 / 10.3 / **9.1** | 7.8 / 10.3 / **9.1** | ~0.7 ms | 2.5 ms |

- Persistence evidence is weak. A Blur Busters claim of "≈0.3 ms MPRT" for Quest 2 is secondary and unverified.
  The Oculus patent example is 2 ms at 90 Hz. `[SPECULATION: bracket 0.3–2 ms; measure]`

### 2.4 Cross-check against a Meta runtime number

- **CFL** is defined as "Minimum/maximum compositor frame latency … the amount of time in the `Prd=` measurement that
  is spent in the OS compositor, which prepares your submitted frame for display".
  Meta's example line shows **`CFL=19.74/21.66` at `FPS=72/72`**.
  `[PROVEN: Meta "Logcat Stats Definitions" doc, updated 2025-07-31. The device is not named in the example.]`
- **Model P** gives compositor lead + vsync→mean flash = (0.25–0.5 F = 3.5–6.9 ms) + 15.1 = **18.6–22.0 ms**.
  That matches.
- **Model T** can only reach 12.6–16.0 ms. It does not match.
- **So the CFL example favours model P**, assuming the example comes from a Quest-class LCD headset.
  `[INFERRED — medium confidence. The photodiode period-sweep in §5 is the decisive test.]`

---

## 3. Measured numbers that exist publicly (and what they are worth)

| Source | Device and path | Number | Method | Worth |
|---|---|---|---|---|
| Meta logcat doc example | Quest (model not stated), native VrApi/OpenXR app, 72 Hz | `Prd=38ms`, **`CFL=19.74/21.66 ms`**, `TW=1.25 ms` (compositor GPU time), `LCnt=2(DR72,LM2)` | Runtime self-report | **Primary.** CFL = submit→display inside the compositor `[PROVEN]` |
| Meta blog "OVR Metrics Tool + VrApi" | Quest apps | Prd "should almost always be a fixed number between **40 and 50 ms**, depending on your engine and display refresh rate" | Runtime | Primary. Pose→display for an engine with extra-latency mode, not video `[PROVEN]` |
| Steam forum, Virtual Desktop overlay | Quest 2, 80 Hz, ~90 Mbit/s, H.264/HEVC | Game 5, Encode 4, Network 6, **Decoding 5 ms**, overall 35–40 ms | VD in-app overlay | Anecdotal but from an instrumented app. The 15–20 ms left over (render + compositor + display) matches the §4 native model at 80 Hz `[PROVEN quote: steamcommunity.com/app/382110/discussions/0/2961642818646823995; INFERRED interpretation]` |
| Steam forum | Quest 2 VD, 90 Hz, 66 Mbit/s | "decoding latency … above 20 ms" (flagged as a regression) | VD overlay | Anecdote. Shows decode can blow up (overload or thermal) `[PROVEN quote]` |
| ALVR maintainers (GitHub #1838 and wiki) | Quest, OpenXR client | "Client vsync: VR runtime compositor time + idle … the latency every Quest app has". Code: `vsync_queue = predicted_display_time − xr_now` at submit | Runtime-predicted | Primary for the **definition**. No trustworthy Quest 2 number found `[PROVEN: alvr/client_openxr/src/stream.rs:459-462; alvr/client_core/src/statistics.rs:89-110]` |
| ALVR issue #2305 comments | Quest 2/3 HEVC | Decode latency explodes above ~150–200 Mbit/s | User reports | Irrelevant at OpenIPC bitrates (4–30 Mbit/s) `[PROVEN quote]` |
| PixelPilot + Quest 2 G2G | — | **none published** | — | Searched GitHub issues/PRs, OpenIPC, forums. The intofpv Quest-3 thread is Cloudflare-blocked, so not read `[PROVEN: absence in reachable sources]` |

**OVR Metrics / `adb logcat -s VrApi` field meanings** `[PROVEN: Meta logcat stats doc]`

- **FPS** = rendered fps / refresh.
- **Prd** = pose-query → display.
- **Tear** = the compositor was late → tear.
- **Early** = the frame arrived before it was needed (extra-latency mode).
- **Stale** = the frame was not ready and the previous one was reused. Stale2/5/10/max count consecutive streaks.
- **VSnc** = swap interval.
- **Lat** = frame-timing mode: >0 extra-latency frames, 0 = none, <0 = PhaseSync variants.
- **TW** = compositor (ATW) GPU time.
- **App** = app GPU time.
- **LCnt** = layers composited including system layers, then **DR** = Direct Render fps (for overlay layers) and
  **LM** = merged layers.
- **CFL** = compositor frame latency, min/max. **ICFLp95** = its 95th percentile.
- **DSF** = DPU scaling factor.
- **SF** = framebuffer scale.

**Important for a 2D panel session** `[SPECULATION — check on device]`: the VrApi line belongs to the **foreground
immersive client**, which is the Home/shell that composites the panels, not PixelPilot. So `FPS`/`Stale` describe the
shell. `CFL` describes shell-frame → display. `LCnt(DRxx)` shows the rate at which overlay/panel layers are direct-rendered.
**None of these fields covers PixelPilot → SurfaceFlinger → panel buffer.**

---

## 4. Latency budget: decoder output → photons (display side), plus decode

### 4.1 Definitions

- **t0** = `releaseOutputBuffer(render=true)` returns.
- **Photon** = mid-flash of the stated eye.
- **W** = wait until the next sampling point, uniform 0…1 F (the stream is not phase-locked to the headset).
- **L** = compositor lead, from content latch to the vsync / scan start of eye 1: 0.25–0.5 F.
  `[SPECULATION bounded by "split in 2, every 7 ms" and CFL]`
- **c_sf** = SurfaceFlinger GPU composite of the panel: 1–3 ms. `[SPECULATION]`
- **g** = phase gap between the SurfaceFlinger output and the compositor latch: ≈0.25 F if both are locked to the same
  vsync and tuned; average 0.5 F if not locked; up to 1 F.
- Best = W=0, L=0.25 F, eye 1. Typical = W=0.5 F, L=0.375 F, mean of eyes. Worst = W=1 F, L=0.5 F, eye 2
  (plus one more F if a latch is missed or a frame goes stale).

### 4.2 Display side only (ms). The first number uses model P, the number in brackets uses model T.

| Path | 72 Hz best / typ / worst | 90 Hz best / typ / worst | 120 Hz best / typ / worst | Confidence |
|---|---|---|---|---|
| **N1** Android-surface quad layer (native) | 16.5 (11.3) / **27.2 (21.2)** / 38.0 | 13.2 (10.6) / **21.9 (18.9)** / 30.5 | 9.9 / **16.4** / 22.8 | INFERRED, medium |
| **2D panel, SurfaceView** (PixelPilot ≥ v0.25, OD off) = N1 + c_sf + g | 17.5 (12.3) / **32.7 (26.7)** / 54.9 | 14.2 (11.6) / **26.7 (23.7)** / 44.6 | 10.9 / **20.5** / 34.1 | INFERRED topology, SPECULATION on c_sf/g |
| **2D panel, TextureView** (PixelPilot v0.24.0 or OD on) | + ½–1 F on top of SurfaceView (≈ +7–14 ms @72, +4–8 ms @120) | | | INFERRED |
| **N2** SurfaceTexture → GL → eye/quad layer | ≈ N1 + ½–1 F (app latch + render + submit) | | | INFERRED |

### 4.3 Decode (XR2 Venus block), OpenIPC-class streams (720p–1080p, 60–120 fps, 4–30 Mbit/s)

| Case | H.264 | H.265 | Confidence |
|---|---|---|---|
| Best | ~2 ms | ~2–3 ms | SPECULATION (SoC class) |
| Typical, low-latency keys on (v0.25) | 3–6 ms | 3–7 ms | INFERRED. VD shows 5 ms on Quest 2 at ~90 Mbit/s with much bigger frames; OpenIPC frames are smaller |
| Worst, keys off (≤ v0.24) | **+1…N video frames** (16.7 ms each at 60 fps) if the decoder holds frames for reordering | usually no hold | INFERRED: H.264 `max_num_reorder_frames` sits in *optional* VUI bitstream_restriction, so a conformant decoder may buffer up to the DPB size when it is absent. HEVC always signals `sps_max_num_reorder_pics` (0 without B-frames) |

### 4.4 Summary budget (display side + decode), typical

| Refresh | 2D panel (PixelPilot v0.25) | Native N1 | Main contributors |
|---|---|---|---|
| 72 Hz | **~31–39 ms** | ~25–31 ms | Panel flash ≈15, compositor wait + lead ≈12, SurfaceFlinger ≈5, decode ≈4 |
| 90 Hz | **~27–31 ms** | ~22–26 ms | |
| 120 Hz | **~24–26 ms** | ~20–22 ms | Panel ≈9, compositor ≈7, SurfaceFlinger ≈4, decode ≈4 |

- Even the **best** 2D figure (≈11 ms display + 2 ms decode at 120 Hz) leaves under 7 ms for sensor readout, ISP,
  encode and the radio link. That rules out the 20 ms target on Quest 2. `[INFERRED]`
- Moving 72 → 120 Hz saves about 12 ms typical on the 2D path in model P, or about 6 ms in model T. The photodiode
  period sweep decides which. `[INFERRED]`

---

## 5. Measurement protocol with the owner's equipment

**Goal:** split G2G into air+link (already measured by the project's HIL), **decode**, **SurfaceFlinger + compositor**
and **panel + backlight**, following the extreme-value (bracketing) rule: 72 vs 120 Hz, plus 90 Hz in the middle, and
N ≥ 3 runs in shuffled order.

### 5.1 Prerequisites

- Stop the headset blanking itself: tape over the proximity sensor, or
  `adb shell am broadcast -a com.oculus.vrpowermanager.prox_close` `[SPECULATION: community command — verify]`.
  Disable the Guardian (developer setting).
- Set the refresh rate with `adb shell setprop debug.oculus.refreshRate 72|90|120` `[PROVEN property]`, or in Quest
  Settings. **Check which rate is really active from the photodiode pulse period.** Do not trust the setting,
  especially for the Home/panel environment.
- Keep the Quest on a PD charger through a USB-C hub (the RTL8812AU occupies the port). Log `Temp`/`PLS` from VrApi:
  above 72 Hz, thermal throttling can drop the rate to 72 Hz `[PROVEN: Meta refresh-rate doc]`.
- **Use PixelPilot v0.25.0**, with Settings → Video → Low latency ON and object detection OFF. Record the version on
  every measurement.

### 5.2 Optical front end (why the ESP32+LDR fails, and what to use)

**Why the LDR rig fails through the optics** `[INFERRED: sensor physics + §2]`

- The light through the lens is a **train of ~0.7–1.1 ms pulses** at the refresh rate, averaging only ~100 nits × duty
  (~8%) ≈ 8 nits.
- A CdS LDR responds in 10–100 ms. It integrates the pulse train into a weak, slow level that the ESP32 slope/level
  detector cannot time.
- That is a **sensor** limit, not a Quest defect.

**Sensor**

- **OPT101**: photodiode with a built-in 1 MΩ transimpedance amplifier, ~14 kHz bandwidth, ~25 µs rise. Clean volts
  straight into the scope. Best choice.
- **BPW34**: reverse-biased 5–9 V, 10–47 kΩ load to the scope, or into an op-amp TIA. Faster, but a smaller signal.

**Mounting**

- Sensor against the centre of **one** lens, with a black foam shroud around it.
- Show a large full-white patch on the panel.
- For the eye-skew test, put a second sensor on the other lens and use CH1 + CH2.

**OWON VDS1022I**

- 2 isolated channels, 25 MHz, 100 MS/s. Its short record length is fine at 10–20 ms/div (tens of µs per point).
  `[SPECULATION: check the unit's record length]`
- Export CSV from the PC software. Trigger on CH1.
- Use the **centre of the first pulse whose amplitude changed** as the photon time.

**Xiaomi 15 Ultra, 480 fps (2.08 ms per frame)**

- Use it as a cross-check at ±2 ms per event.
- Put the stimulus LED and the lens **on the same sensor row**, so the phone's rolling-shutter skew cancels out.
- Average ≥ 30 events.

### 5.3 Experiments

**E1: characterise the panel (photodiode only, no stream)**

- Static white screen at 72 / 90 / 120 Hz. Measure on each lens:
  - pulse period (the real refresh rate),
  - pulse width (persistence),
  - left/right flash offset.
- A skew that scales with F supports model P; a constant skew in ms supports model T.
- Gives: persistence and eye skew. `[PROVEN by construction once measured]`

**E2: internal display latency (decoder-ready → photon), without optics guesswork**

- Build a small "flipper" APK with two variants:
  - **2D**: SurfaceView, same as PixelPilot.
  - **N1**: OpenXR `XR_KHR_android_surface_swapchain` quad layer.
- Each variant alternates black and white frames at a slow, non-harmonic cadence (e.g. 3.3 Hz).
- The frames are produced by a MediaCodec decoder (a pre-encoded black/white H.264/H.265 clip) or by
  `lockCanvas/unlockCanvasAndPost`. Both feed the same BufferQueue, so the path downstream is identical `[INFERRED]`.
- At each `releaseOutputBuffer`/post, the app toggles **DTR/RTS of a USB-serial adapter** (CP2102/FT232/CH340 on the
  USB-C hub, through the Android USB-host API). Wire DTR to scope CH1 and the photodiode to CH2.
- Calibrate USB control-transfer jitter by toggling DTR twice back-to-back and logging `System.nanoTime()` around the
  call. Expect about ±1 ms.
- **Result: t0 → photon directly, for the 2D and native paths, at 72/90/120 Hz.** This is the number no public source
  has. It replaces every INFERRED cell of §4.2.
- **Bracket:** also run with the flipper throttled to 1 fps and at 120 fps. If latency does not change with content
  rate, the stages are pure sampling.

**E3: attribute the stages with Perfetto, without optics**

- Record: `adb shell perfetto -o /data/misc/perfetto-traces/q2.pftrace -t 10s sched freq gfx view video`
  (atrace categories).
- Add `ATrace_beginSection("PP_release")` around PixelPilot's `releaseOutputBuffer` (a one-line patch).
- In the trace, read:
  - app release,
  - SurfaceFlinger latch/composite of the SurfaceView layer and of the virtual display,
  - the compositor / TimeWarp thread slices ("A VR Frame's Life" says TimeWarp is visible in systrace `[PROVEN]`),
  - HW vsync.
- Before and after, capture `adb shell dumpsys SurfaceFlinger > sf.txt` and `adb shell dumpsys display > disp.txt`.
  These show whether PixelPilot's layer lives on a **virtual display** (which proves the §1.2 topology), the
  composition type (CLIENT = GPU vs DEVICE), and the SurfaceFlinger vsync period and phase offsets. The period tells
  you whether SurfaceFlinger is locked to the panel rate; that is the `g` term.
- `dumpsys SurfaceFlinger --latency "<SurfaceView layer name>"` gives per-buffer ready/latch times for stage A.

**E4: decode**

- PixelPilot OSD "ms" (decode + parse + input wait) plus a logcat line per frame, for:
  - H.264 vs H.265, same resolution / fps / bitrate,
  - low-latency ON vs OFF (the toggle restarts the app: PR #121),
  - bracket at the lowest and highest bitrate the air unit supports.
- Also run the same air unit to the OPi5 ground station for the reference decode figure already in the project's HIL.

**E5: full optical G2G**

- LED in the air-unit camera's view, driven by an ESP32 GPIO that is also wired to CH1. Photodiode at the Quest lens on
  CH2. N ≥ 100 events per condition.
- Subtract the project's HIL air + link breakdown, E4 (decode) and E2 (display). The residual should be ≈ 0 ± 2 ms.
  If not, one stage is mis-modelled (see HM-019: combine all corrections before judging).

**Test matrix** (shuffle the order and repeat each cell 3 times)

| Axis | Levels |
|---|---|
| Refresh | 72 · 90 · 120 Hz |
| Codec | H.264 · H.265 |
| Presentation | PixelPilot v0.25 SurfaceView (2D) · PixelPilot TextureView (OD on or v0.24) · flipper-2D · flipper-N1 · optionally PixelPilot_quest OpenXR (N2) |
| Decoder keys | low-latency ON · OFF |
| Eye | left · right (E1/E2) |

---

## 6. Open questions (what would confirm or refute the model)

- Is the Horizon 2D panel really a virtual display composited by SurfaceFlinger on the GPU?
  → E3 `dumpsys` / Perfetto. `[SPECULATION]`
- Is SurfaceFlinger's vsync locked to the panel rate, and does it follow 72/90/120?
  → E3. `[SPECULATION]` If it is not locked, the 2D path gains ~½ F extra plus jitter.
- Model P vs model T for the backlight timing → E1 period sweep. `[SPECULATION]`
- Does `debug.oculus.refreshRate` retime the Home/panel environment, or only immersive apps? → E1. `[SPECULATION]`
- Does the XR2 decoder hold H.264 frames when low-latency is OFF and OpenIPC's SPS has no VUI bitstream_restriction?
  → E4, plus dump the SPS. `[INFERRED risk]`
- Which eye flashes first on Quest 2 (Fig. 3 is Quest 3S: right first) → E1. `[SPECULATION]`

---

## 7. Audit of prior notes (June 2026)

The two notes audited:

- `C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/hardware-research/07-meta-quest-2-display.md` (**07**)
- `C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/research/47-quest2-compositor-bypass-deep-research.md` (**47**)

### What they got right

- PixelPilot runs on the Quest 2 as a non-VR 2D app with a userspace RTL8812AU driver, no root. (07 §1)
- The VR compositor is mandatory and cannot be turned off for an app. Root or a custom OS gives no latency gain.
  (47 §1, §2, §4) This agrees with Meta's OOPC description.
- Higher refresh rate is the main setting to change, and `debug.oculus.refreshRate` exists. (47 §3; now confirmed:
  Quest 2 values 60/72/80/90/120 in the Meta system-properties doc.)
- Use a monitor with known input lag for the clean baseline, and measure the "Quest tax" as a delta afterwards.
  (07 §6) This is sound methodology and still recommended.
- No public G2G figure exists for PixelPilot + Quest. (47 §5) Confirmed here as well.
- Power, heat and hub caveats for the RTL8812AU on the Quest's single port. (07 §4) Plausible; not re-verified.

### What is wrong or unsupported

1. **"Horizon OS promotes the SurfaceView to a compositor layer with late-latching → tax plausibly well under 10 ms"**
   (07 header and §3; 47 §4 "compositor layer (Quad) — exactly what PixelPilot does").
   - **Unsupported, and contradicted by the evidence.**
   - PixelPilot is a plain 2D Android activity. It creates no OpenXR quad layer (`AndroidManifest.xml`).
   - Horizon runs 2D activities on a non-default container display (amwatson README). There is therefore at least a
     SurfaceFlinger stage before the compositor.
   - "Late latching" (Meta blog) is about app **pose** uniforms, not about when video content is picked up.
   - The cited "Android XR Extensions docs" describe Google's Android XR platform, not Horizon OS.
   - Carmack's "video surface on a compositor layer" is the 2015 Gear VR Netflix app, in which the **VR app itself**
     consumed the Surface as a SurfaceTexture (cgclass.csc.ncsu.edu copy of Carmack's post).
2. **"Plausibly well under 10 ms".**
   - The physics alone rules this out. After scan-out starts, the **first** eye's backlight flashes ~7.8 ms (120 Hz)
     to ~13 ms (72 Hz, model P) later. Add compositor lead and pacing waits.
   - Meta's own `CFL` example is ≈ 20 ms at 72 Hz for a native layer.
   - Realistic display side: ~11 ms best, ~16–33 ms typical (§4).
3. **"Compositor + TimeWarp ~1-2 ms"** (07 §3 table).
   - This confuses **compositor GPU execution time** (`TW=1.25 ms` in Meta's example) with **latency through the
     compositor** (`CFL≈20 ms` in the same example line).
4. **"Scanout + LCD pixel response ~2-25 ms; LCD response adds a latency tail"** (07 §2/§3, generic vrarwiki).
   - Misses the mechanism. With a strobed global per-eye backlight, LC response is **hidden before the flash**.
   - Latency is set by scan + settle + the flash position, a near-constant ~0.9–1.3 F, not by a response "tail".
   - The dual-backlight, per-eye flash and the 2.5–4 ms eye-to-eye skew are absent from both notes.
5. **"120 Hz lowers scan-out from ~14 ms to ~8 ms (−~6 ms)"** (47 §3; 07 "+8/+11/+14 ms").
   - Only one of several stages was scaled. In model P every sampled stage and the flash position scale together:
     about −12 ms typical on the 2D path.
   - In model T the panel part does not scale at all.
   - Both are unmeasured; the June notes presented one number as fact.
6. **"Refresh 72/90 official, 120 experimental"** (07 §2). Outdated. Meta's current table lists 72/80/90/96/100/120
   for Quest 2.
7. **"Decode HW … via Adreno video core"** (07 §2). Wrong. Video decode runs on Qualcomm's Venus video block, not the
   Adreno GPU. Minor.
8. **"ASW does not run on the 2D layer"** (47 §4). Stated as PROVEN, but no source shown for panels. It is
   `[SPECULATION]` at best (ASW concerns immersive app frames).

### What they missed

- **The decoder was not in low-latency mode in any PixelPilot release before v0.25.0 (2026-09-02).** The keys were
  commented out until PR #113, and v0.24.0 also rendered into a TextureView (#108). Any June-era Quest experience was
  on a non-low-latency decoder, and the H.264 reorder-hold risk applies to it.
- **The OSD "ms" measures only parse + decode**, never the display side.
- **The real bypass that exists**: native `XR_KHR_android_surface_swapchain` / Spatial SDK `VideoSurfacePanelRegistration`.
  It skips SurfaceFlinger and the app GPU pass (not the compositor) and is worth ~4–5 ms typical, up to ~11–17 ms
  worst case. 47 concluded "no clean path exists" without examining it.
- **The CFL/ICFLp95 fields** (runtime-reported compositor latency) and the fact that during a 2D session the VrApi
  logcat line describes the **shell**, not PixelPilot.
- **A concrete stage-separating protocol** (USB-DTR marker + photodiode, Perfetto/dumpsys), and why the LDR rig fails
  through the optics (pulsed ~1 ms, ~8 nit average light versus a 10–100 ms CdS sensor).
- **The eye-to-eye flash skew**, which matters for choosing which lens the photodiode sits on.

**Verdict on the notes.** Their operational conclusions were right: Quest 2 is not usable for the 20 ms target, and a
monitor should be used for the baseline. Their central quantitative claim ("PixelPilot's display tax plausibly well
under 10 ms, compositor layer + late-latching") was an unsupported upgrade based on the wrong platform's docs. It
should carry a correction note pointing to this file (see HM-019 rule 4).

---

## Sources

**Primary: Meta / Khronos / patents / papers**

- Meta blog, "A VR Frame's Life" (2021-05-20): https://developers.meta.com/horizon/blog/a-vr-frames-life/
- Meta, Logcat Stats Definitions (CFL/ICFLp95/LCnt/Prd…): https://developers.meta.com/horizon/documentation/native/android/ts-logcat-stats/
- Meta blog, OVR Metrics Tool + VrApi metrics: https://developers.meta.com/horizon/blog/ovr-metrics-tool-vrapi-what-do-these-metrics-mean/
- Meta, Set Display Refresh Rates: https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/
- Meta, Android system properties: https://developers.meta.com/horizon/documentation/native/android/ts-systemproperties/
- Meta, MediaProjection on Quest ("custom compositor within XrRuntime"): https://developers.meta.com/horizon/documentation/native/native-media-projection/
- Meta Spatial SDK, layer and mesh rendering modes (VideoSurfacePanelRegistration): https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-2dpanel-layers/
- Meta blog, FrameSync (2026-03-03): https://developers.meta.com/horizon/blog/framesync-meta-horizon-os/
- Khronos, xrCreateSwapchainAndroidSurfaceKHR: https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrCreateSwapchainAndroidSurfaceKHR.html
- SID 2025 Digest 39-4, "Quest 3S Immersive Display with High Visual Fidelity" (Meta), Figs. 2-3: https://sid.org/Portals/sid/Files/SID-Digest/docs/39-4.pdf
- SID 2022 6-2, "High-ppi Fast-Switch Display Development for Oculus Quest 2" (Kim, Meta): https://sid.onlinelibrary.wiley.com/doi/10.1002/sdtp.15410 (paywalled; summary via https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/)
- US20170287409A1, "Global illumination mode LCD for VR" (Oculus → Meta): https://patents.google.com/patent/US20170287409A1/en
- Carmack on the Netflix VR app (SurfaceTexture → TimeWarp layer), 2015: https://cgclass.csc.ncsu.edu/2015/10/john-carmack-on-developing-netflix-app.html

**Code (local shallow clones)**

- `C:/xampp/htdocs/pixelpilot-xr/repos/PixelPilot` (upstream OpenIPC, 3d6ca17): VideoDecoder.cpp, AndroidMediaFormatHelper.h, VideoActivity.java, DecodingInfo.java, BufferedPacketQueue.h, AndroidManifest.xml
- PixelPilot PRs #108/#113/#114/#120/#121 and releases v0.24.0/v0.25.0 (via `gh`)
- `C:/xampp/htdocs/pixelpilot-xr/repos/ALVR` (sparse, 99d8948): client_openxr/src/stream.rs, client_core/src/statistics.rs, wiki "How ALVR works"
- `C:/xampp/htdocs/pixelpilot-xr/repos/FPVue_xr`, `C:/xampp/htdocs/pixelpilot-xr/repos/PixelPilot_quest` (pre-existing clones)
- amwatson/2DVrHybrid README (2D container display behaviour): https://github.com/amwatson/2DVrHybrid

**Secondary / anecdotal**

- Virtual Desktop overlay numbers, Quest 2: https://steamcommunity.com/app/382110/discussions/0/2961642818646823995/ ; https://steamcommunity.com/app/250820/discussions/0/3820795131602118318/
- ALVR issues #1838, #2305 (GitHub)
- Carmack on LCD vs OLED persistence (Rift S/Go), X: https://x.com/id_aa_carmack/status/1108703559263178752
