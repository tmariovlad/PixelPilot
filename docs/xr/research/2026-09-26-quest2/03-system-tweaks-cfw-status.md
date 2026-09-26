# Quest 2 as an FPV display: system-level levers, custom-OS/root status, hardware alternative

> **Date:** 2026-09-26. **Scope:** a retail Meta Quest 2 that the owner owns, showing an external FPV
> H.264/H.265 stream decoded on-device by an Android APK (PixelPilot, flat 2D panel, "non-VR mode").
> **Project target:** 20 ms glass-to-glass (G2G) total.
> **Method:** independent research from primary sources: Meta developer docs, Carmack's Connect 2020
> keynote transcript, Meta's GPL kernel source for Quest 2, Khronos, and the PixelPilot PRs. The older
> project note (#47) was read only after this research was done; its audit is in §9.
> **Constraints followed:** no device was connected or modified. No exploit or jailbreak mechanics are
> described; root and bootloader topics are covered as public status only.
> **Tags:** `[PROVEN: source]` = seen in a primary source or code. `[INFERRED]` = deduced from proven
> facts, with the chain given. `[SPECULATION]` = hypothesis, with the probe that would settle it.

---

## 0. TL;DR

1. **Nothing at the system level lets a retail Quest 2 bypass the VR compositor.** No ADB property,
   developer setting or official API turns it off or scans an app buffer straight to the panel.
   [PROVEN: Meta ATW doc: "ATW is automatically applied by the Compositor; you do not need to enable or
   tune it."; Meta system-properties doc lists no compositor switch, see §2]
2. **The physics sets a floor of about one refresh period per frame, before any software cost.**
   The Quest 2 LCD must settle, then each eye's backlight is flashed once, and the flash is placed at
   the end of the refresh. Photons for frame N therefore arrive about 1 to 1.4 refresh periods after
   frame N's scanout starts. [PROVEN: Carmack Connect 2020 transcript, and the Quest 2 kernel
   `dsi_panel_jdi_update_backlight()`, see §1.3; timing numbers INFERRED from that code]
   - At 120 Hz this is about 8 to 11.5 ms.
   - At 72 Hz it is about 14 to 19 ms.
3. **The 2D-panel path adds at least one more composition hop, on top of that floor.** The APK's
   SurfaceView goes into a system-shell panel, and the shell's layer then goes to the VR compositor.
   [INFERRED/SPECULATION, §1.4]
   - A realistic display-side cost (decoded frame to photon) is about 2 to 4 refresh periods.
   - That is roughly **17 to 35 ms at 120 Hz**, and more at the shell's default 90 Hz.
   - **This alone uses up or exceeds the whole 20 ms G2G budget.** [INFERRED]
4. **Real levers, ranked by expected gain:**
   - (a) **Leave the 2D panel.** Build an immersive OpenXR path in which MediaCodec decodes into an
     Android-Surface swapchain attached to a quad layer. This removes the shell and SurfaceFlinger hop.
     It is an app change, needs no root, and is already being built upstream for Quest 3.
   - (b) **Run at 120 Hz.**
   - (c) **Enable the MediaCodec low-latency keys** (PixelPilot PR #113, merged 2026-09-02), and use
     **SurfaceView, not TextureView** (PR #114).
   - Everything else (CPU/GPU levels, foveation, guardian, proximity, casting) has **≈0 ms** effect on
     this path. It is useful only to cut jitter or to keep a bench session running.
5. **Root and custom OS do not help in practice.** There is no official unlock, and the public unlock
   works only on old firmware (May 2021, and community reports of ≤v59). Current firmware is far past
   that. There is no public custom OS with a working display. Even with root, the LCD settle and
   strobe floor stays. [PROVEN/INFERRED, §4–5]
6. **Verdict: the 20 ms G2G target cannot be reached on a Quest 2.** The best case is an immersive
   OpenXR path at 120 Hz. Even that puts about 14 to 21 ms on the display side alone. [INFERRED]
   A low-latency HDMI goggle is the only realistic route to 20 ms. The HDZero Goggle 2 accepts
   720p100 HDMI "without adding any frame buffer latency". [PROVEN: docs.hd-zero.com]

---

## 1. How the Quest 2 display stack works (what can be changed)

### 1.1 The panel hardware (from Meta's own GPL kernel source)

Meta publishes the Quest 2 ("hollywood") kernel. It is Linux 4.19, and the `oculus-quest2-kernel-master`
branch was last pushed 2026-09-25 (commit `e8c2245c4c`, build 5224299.3580.150).
[PROVEN: https://github.com/facebookincubator/oculus-linux-kernel/tree/oculus-quest2-kernel-master ,
README.meta.md: "Quest 2/hollywood"]

- **The panel is a single 3664×1920 LCD, driven over two DSI controllers with four lanes each.** It runs
  in video mode with DSC compression (8 bpp, slices of 480×16). Panel timing blocks list 960×3664 per
  controller. [PROVEN: `arch/arm64/boot/dts/oculus/hollywood/hollywood-dsi-panel-sharp-dsc-4k-120Hz-video.dtsi`
  — "Sharp panel 3664x1920(24bpp) @ 120Hz", `qcom,dsi-ctrl-num = <0 1>`, `qcom,compression-mode = "dsc"`,
  `qcom,mdss-dsc-bit-per-pixel = <8>`]
- **Four panel vendor variants exist in the tree: BOE, JDI, JDI-NVT and Sharp.** Each has its own mode
  table for 72, 80, 90 and 120 Hz. [PROVEN: `hollywood-panel.dtsi` `display_panels` list]
  - Which vendor a given retail unit has is unknown. [SPECULATION; probe: `/sys/class/drm` or `dmesg`
    panel name]
- **The refresh rate is changed through the DSI vertical front porch**
  (`dfps_immediate_porch_mode_vfp`), with a minimum of 60 and a maximum of 120.
  [PROVEN: same dtsi, `qcom,mdss-dsi-pan-fps-update`, `min/max-refresh-rate`]
  - In the BOE 120 Hz mode, vtotal is 3686 lines at 120 Hz. One line is therefore about 2.26 µs, and
    the 3664 active lines take about **8.28 ms**. [INFERRED from the timing values: v-active 3664 +
    VBP 7 + VFP 14 + VSW 1]
- **The backlight is a "global" strobe split into two BLUs (one per half of the panel, which means one
  per eye).** It is programmed by a DCS command (`0xB9`) that sets the start scanline and the period of
  each BLU. [PROVEN: `techpack/display/msm/dsi/dsi_panel.c` `dsi_panel_jdi_update_backlight()`, ~L780–860,
  comment "Payload … parameter 0: Start scanline of right BLU / parameter 1: Period of right BLU in
  scanlines … parameter 4: Start scanline of left BLU"]
  - **The flash is placed at the end of the refresh.** The code computes "the last scanline to start on
    for each BLU without overlapping the backlight illumination with the next refresh's scanout".
    [PROVEN: same function, comment + `right_scanline = vtotal + v_sync_width + v_back_porch - bl_lvl`]
  - **Flash length = brightness level × duty × vtotal.** Brightness levels run from 800 to 1200, and
    duty is 8 to 10 % depending on the panel variant, so the flash lasts **about 6 to 12 % of a frame**.
    At 120 Hz that is about 0.5 to 1.0 ms, and at 90 Hz about 0.7 to 1.3 ms.
    [PROVEN: `hollywood-panel.dtsi` `qcom,mdss-dsi-jdi-default-duty-cycle = <80>/<100>`,
    `bl-min-level 800`, `bl-max-level 1200`; arithmetic INFERRED]
- **The display pipeline exposes a line-pointer interrupt with a 256-line advance, and the writeback
  thread runs at RT priority.** [PROVEN: `hollywood-panel.dtsi` `&mdss_mdp { qcom,sde-lineptr-scanline-advance = <256>;
  qcom,sde-wb-rtprio = <99>; }`] This hints that the compositor beam-races, rendering just ahead of
  scanout, as Gear VR/Quest-1 TimeWarp did. [SPECULATION; it is not confirmed in any Meta doc found]

### 1.2 What Carmack said about this panel (primary source)

This is from the Facebook Connect 2020 keynote, https://www.youtube.com/watch?v=sXmY26pOE-Y at about
18:40–23:30. The transcript was pulled with youtube-transcript-api.

- "you command the LCDs to switch but it takes them a few milliseconds to actually get done changing and
  then we blast the backlight behind it … previous displays had a single backlight … a 1 millisecond
  burst over the entire thing. Now we have that split … the left eye and the right eye kind of get their
  own separate bursts … We can scan out half the screen, wait a while while the second half of the screen
  is scanning out, blast the first eye, blast the second eye." [PROVEN: transcript]
- "at the same frame rate, there is a little bit more latency on Quest two than there is on Quest one
  because we have to wait a little while for the LCD to settle … we can usually claw that back by running
  at a higher rate." [PROVEN: transcript]
- "our compositor takes input images from multiple different clients … pop-up dialogues, the actual game
  screen, UI … all these can come from different places." [PROVEN: transcript]
- He described variable refresh ("dynamically firing off the retraces") as an experiment that showed
  "visible flickering" with a single backlight burst. It was not shipped as far as the public docs show.
  [PROVEN: transcript; "not shipped" is INFERRED from its absence in the refresh-rate docs]

### 1.3 The latency floor that follows from the panel [INFERRED from §1.1 code + §1.2]

Start the clock at the first active line of frame N's scanout. With the BOE/JDI-type BLU logic at 120 Hz
(vtotal 3686, line ≈ 2.26 µs):

- **The first-flashed half (the "right" BLU) is at its midpoint about 7.9 to 8.1 ms after scanout
  start.**
  - The flash ends when the next frame's active scanout begins.
- **The second half (the "left" BLU) is later.** Its start is capped at `vtotal − VFP + max_scanline_offset(1200)`,
  which is about 2.7 ms into the next refresh. Its midpoint is therefore **about 11.3 to 11.5 ms** after
  frame N's scanout start.
- **Averaged over both eyes, the display takes about 1.15 to 1.2 refresh periods from "scanout starts"
  to "photons".** That is about 9.7 ms at 120 Hz.
  - Scaled with the refresh period, it is about 12.9 ms at 90 Hz and about 16 ms at 72 Hz.
  - This assumes the lower-rate modes keep the same proportion. Because refresh is changed through the
    VFP, active scanout may stay at about 8.3 ms, with extra blanking added before the flash.
- **Brightness is not a real lever.** Going from minimum to maximum brightness makes the flash start
  earlier (its end is fixed), which moves the photon centroid by only about **0.17 ms** at 120 Hz.
  [INFERRED from the `bl_lvl` formula; which Settings slider maps to 800–1200 is unverified]
- **This floor applies to any content, including a hypothetical root or custom-OS direct path.** It
  comes from LC settling plus the strobe placement, not from Horizon OS. [INFERRED]

### 1.4 How a 2D Android app reaches the panel on Horizon OS

- **2D apps appear as windows inside the VR environment.** "Meta VR devices display 2D apps in resizable
  windows within a VR environment". [PROVEN: https://developers.meta.com/horizon/documentation/android-apps/horizon-os-apps/]
- **The VR compositor combines frames from several apps and services, each in its own window.** It also
  applies lens distortion correction. [PROVEN: https://developers.meta.com/horizon/documentation/native/android/os-compositor/
  and https://developers.meta.com/horizon/documentation/unity/os-compositor/]
- **The VR compositor also corrects for the panel itself.** It adapts content for "panel and backlight
  variations (rolling shutter, uniformity)". 2D panel apps are upscaled by the compositor.
  [PROVEN: https://developers.meta.com/horizon/blog/vr-image-quality-meta-quest-super-resolution/]
- **VrShell manages the "System 2D panels"** (community research). [PROVEN as a community claim:
  https://github.com/Nuvido/Quest2_Research/blob/main/System.md]
- **What happens in between is not public.** No Meta document found describes the path from an Android
  window's SurfaceFlinger output to the compositor layer. The likely path is:
  **app SurfaceView → SurfaceFlinger composing a per-window virtual display (GPU, no HW overlay plane) →
  shell (VrShell/SystemUX) samples that buffer on its own frame → quad/cylinder compositor layer →
  compositor/TimeWarp → panel.** Each "→" that is paced by vsync can add up to one refresh period.
  [SPECULATION; probe (read-only, when allowed): `adb shell dumpsys SurfaceFlinger --display-id`,
  `dumpsys display | grep -i virtual`, and `dumpsys SurfaceFlinger --latency <layer>` while PixelPilot runs]
- **The shell runs at 90 Hz by default.** "Quest 2 system software including Home, Guardian, and
  Passthrough will run at 90Hz." [PROVEN: https://developers.meta.com/horizon/blog/-oculus-quest-v23-how-to-update-your-app-for-90hz/ (2020-11-13)]
  - With the 120 Hz toggle enabled, "Home Environment, Explore, Store, Browser and Oculus TV" support
    120 Hz out of the box, according to the v28 release coverage. [PROVEN (secondary): https://www.androidcentral.com/oculus-quest-2-v28-update-adds-120hz-wireless-pc-vr-streaming-and-more]
  - The Quest Browser renders 2D pages at 90 Hz on Quest 2. [PROVEN: https://web.dev/articles/pwas-on-oculus-2 (2022-01-10)]
- **Consequence: the rate the 2D PixelPilot panel actually runs at is decided by the shell, not by the
  APK.** Whether Android `Surface.setFrameRate()` from a panel app is honoured on Horizon OS is
  undocumented. [SPECULATION; probe: request 120 from the app and read the OVR Metrics Tool display
  refresh while the panel is focused]

### 1.5 Can the compositor be disabled or bypassed?

- **ATW cannot be turned off.** "ATW is automatically applied by the Compositor; you do not need to
  enable or tune it." and "At the refresh interval, the Compositor applies ATW to the last rendered
  frame." [PROVEN: https://developers.meta.com/horizon/documentation/native/android/mobile-timewarp-overview/]
- **The panel refreshes every period whatever the app does.** "The display continues to refresh at its
  configured rate regardless of application frame rate … the compositor always outputs a frame to the
  display on time — it just may be a reprojected version." [PROVEN: https://developers.meta.com/horizon/documentation/unity/os-missed-frames/]
- **Positional TimeWarp runs only when App SpaceWarp is active.** App SpaceWarp is an app opt-in; a 2D
  panel does not have it. [PROVEN: os-compositor doc; the 2D-panel part is INFERRED]
- **There is no ADB property or documented API that bypasses the compositor.** [PROVEN by omission:
  https://developers.meta.com/horizon/documentation/native/android/ts-systemproperties/ lists only refresh,
  texture size, CPU/GPU level, foveation and capture properties]
- **The closest official thing to "direct to panel" is a compositor layer fed straight by the decoder.**
  - OpenXR `XR_KHR_android_surface_swapchain` creates a swapchain that exposes an Android `Surface`.
    The producer (MediaCodec) writes into it, and `xrAcquire/Wait/ReleaseSwapchainImage` "cannot be
    called" on it. [PROVEN: https://expipiplus1.github.io/vulkan/openxr-0.1-docs/OpenXR-Extensions-XR_KHR_android_surface_swapchain.html ;
    Khronos man page https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_KHR_android_surface_swapchain.html]
  - It is in use on Quest 2. AVPro Video's `XRCompositionLayer` mode hands "the decoder surface …
    straight to the XR swapchain — no BGRA conversion, no Unity texture" on Quest 2.
    [PROVEN: https://github.com/RenderHeads/UnityPlugin-AVProVideo/issues/2505]
  - **Meta's main OpenXR support page does not list this extension.** Treat Quest 2 runtime support as
    very likely but not officially guaranteed. [PROVEN: absent from https://developers.meta.com/horizon/documentation/native/android/mobile-openxr/ ;
    SPECULATION on current-firmware support until `xrEnumerateInstanceExtensionProperties` is checked on the device]

---

## 2. ADB-only settings (no root)

Meta states that "Changes to system properties do not persist over reboots."
[PROVEN: https://developers.meta.com/horizon/documentation/native/android/ts-systemproperties/]
The owner has to re-apply them after each boot, for example through SideQuest, QGO or a small script.

| Lever | Exact command | Documented effect | Persistence | Expected latency effect on the **2D PixelPilot panel** |
|---|---|---|---|---|
| Refresh rate | `adb shell setprop debug.oculus.refreshRate 120` (Quest 2 values: 60, 72, 80, 90, 120 per Meta's system-properties page; the Unreal refresh page's table is extracted as 72/80/90/96/100/120, which is **inconsistent, so check on the device**) | "Used to set the display refresh rate" [PROVEN: ts-systemproperties]. UploadVR (2020): it applies to "90Hz-ready" apps; at launch "Quest 2 can only run at 90Hz for the home environment and Oculus Browser" [PROVEN: https://www.uploadvr.com/90hz-games-oculus-quest-2-how-to-virtual-desktop/] | Lost on reboot [PROVEN] | **Largest lever if it reaches the panel.** Going from 90 Hz to 120 Hz takes 11.1 → 8.3 ms per hop. With about 2 to 4 vsync-paced hops that is **−5 to −11 ms** [INFERRED from §1.3–1.4]. Whether the shell hosting a 2D panel obeys this property is **unproven** [SPECULATION; probe with OVR Metrics "display refresh" while the panel is focused]. The official route is to turn on the **120 Hz toggle (Settings → System → Display)**, which makes the shell use 120 Hz [PROVEN (secondary): androidcentral v28 article above] |
| 120 Hz default-on | (Settings) | Carmack, 2022-09: "we are finally going to make it default-on" [PROVEN: https://www.uploadvr.com/quest-2-120hz-no-longer-experimental/] | Persists (user setting) | Same as the row above |
| CPU / GPU level | `adb shell setprop debug.oculus.cpuLevel <n>` / `debug.oculus.gpuLevel <n>` | "Used to override an app's set CPU/GPU level"; the maximum depends on the device [PROVEN: ts-systemproperties] | Lost on reboot | **≈0 ms on average.** It may reduce jitter or stale frames if the shell or compositor is clock-starved [SPECULATION]. H.264/H.265 decode runs on the fixed-function video block, not the CPU/GPU [INFERRED]. Whether it applies to a 2D app at all (it overrides levels set by *VR apps*) is unproven [SPECULATION] |
| Foveation | `adb shell setprop debug.oculus.foveation.level 0..4`, `debug.oculus.foveation.dynamic 0` | System-wide FFR override [PROVEN: https://developers.meta.com/horizon/documentation/native/android/os-fixed-foveated-rendering/ via search, and the ts-systemproperties page] | Lost on reboot | **0 ms.** FFR applies to an app's eye buffers; a 2D panel layer is not foveated eye-buffer content [INFERRED] |
| Eye-buffer size | `debug.oculus.textureWidth/Height` (Quest 2 default 1440×1584) | Overrides the default eye texture [PROVEN: ts-systemproperties] | Lost on reboot | 0 ms for a 2D panel [INFERRED] |
| Guardian / boundary | `adb shell setprop debug.oculus.guardian_pause 1`; MQDH Device Actions → Boundary (Ctrl+Shift+G) | Pauses the guardian [PROVEN: https://gist.github.com/t-34400/3bc5f81d9e40b69072c99d5d640b5c89 ; https://developers.meta.com/horizon/documentation/unity/ts-mqdh-basic-usage/] | Property lost on reboot; the MQDH toggle stays until changed [PROVEN: MQDH doc] | ≈0 ms [SPECULATION]. Guardian is a separate compositor client (Carmack 2020), so pausing it can only remove a small GPU load |
| Proximity sensor (bench) | `adb shell am broadcast -a com.oculus.vrpowermanager.prox_close [--ei duration <ms>]`; re-enable with `… automation_disable`; MQDH Ctrl+Shift+P | Keeps the display on when the headset is not worn [PROVEN: gist above; MQDH doc: re-activates after 10 min when disconnected from MQDH] | Temporary | **0 ms.** Needed only so a LED/LDR rig can sit in front of a lens |
| Video capture / casting | `debug.oculus.enableVideoCapture`, `debug.oculus.fullRateCapture`, `debug.oculus.capture.*` | Capture controls [PROVEN: ts-systemproperties] | Lost on reboot | **Keep OFF during G2G tests.** Capture or casting encodes the compositor output, adding GPU and encoder load that may cause stale frames or decoder contention [INFERRED; not measured] |
| Thermal simulation (test only) | `adb shell am broadcast -a com.oculus.vrruntimeservice.COMPOSITOR_SIMULATE_THERMAL --es subsystem refresh --ei seconds_throttled 10` | Simulates refresh throttling [PROVEN: https://developers.meta.com/horizon/documentation/unreal/unreal-change-display-refresh-rate/] | Temporary | Negative lever. It shows that **thermal throttling can drop the rate to 72 Hz** ("Dynamic throttling may change the refresh rate to 72 Hz"), so G2G runs must log the actual refresh |
| Phase Sync / FrameSync | Manifest `com.oculus.enable_frame_sync` (app side); there is no documented setprop | Frame timing for **VR apps**: Phase Sync gave −10 ms in Oculus Home on Quest 2; FrameSync becomes the default for Store apps from v203 [PROVEN: https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/ ; https://developers.meta.com/horizon/blog/framesync-meta-horizon-os/ (2026-03-03)] | App build | **N/A for a 2D panel app**, because it acts on eye-buffer submission timing. It would matter only for an immersive OpenXR PixelPilot [INFERRED] |
| App SpaceWarp / ASW | App opt-in only (no global switch on standalone) | Positional TW only with ASW [PROVEN: os-compositor doc] | — | N/A (off for 2D panels) [INFERRED] |
| Backlight persistence / brightness | No user or ADB control of the BLU duty; brightness moves only the start of the flash | BLU duty is fixed in the device tree at 8–10 % [PROVEN: kernel dtsi] | — | ≤0.2 ms (§1.3) [INFERRED] |
| "Developer Runtime Features" (Settings → Developer) | UI toggle | No primary doc found tying it to display timing | — | Assume 0 ms [SPECULATION] |

**Third-party front-ends** apply the same `setprop` levers through wireless ADB, and must re-enable it
after each reboot. These are SideQuest, Quest Games Optimizer (QGO) and Web-ADB-Menu. They are
conveniences, not new levers. [PROVEN: https://mixed-news.com/en/quest-games-optimizer-faq-infos/ via search summary;
https://github.com/twhlynch/Web-ADB-Menu/blob/main/hz.html]

**APK-level levers:** these are not system settings, but they are the cheapest real wins.
- **MediaCodec low-latency keys.**
  - Before PixelPilot PR #113, `writeAndroidPerformanceParams()` "was never invoked … every decoder
    [ran] without low-latency optimization or realtime priority".
  - "Without `KEY_LOW_LATENCY` the codec may hold output frames back for reordering."
  - The fix adds a switch at Settings → Video → Low latency (default on). It was merged on 2026-09-02,
    and the keys were "accepted by Meta's H.265 decoder" on a Quest 3.
  - [PROVEN: https://github.com/OpenIPC/PixelPilot/pull/113] Expected gain: **0 to several frames**,
    depending on how the Quest 2 Venus decoder behaves by default. [SPECULATION; A/B on the rig]
- **SurfaceView, not TextureView.**
  - PR #114 restores SurfaceView unless object detection is on. A TextureView "costs GPU time, power,
    and roughly one frame of extra latency". [PROVEN: https://github.com/OpenIPC/PixelPilot/pull/114]
  - On Horizon OS the HW-overlay argument probably does not apply, because the window is itself
    composited into a panel. SurfaceView still avoids an app-side GPU copy and a UI-thread frame.
    [INFERRED]

---

## 3. Official Meta options (2025–2026) and Quest 2 support status

- **Immersive OpenXR app with a decoder-fed layer.** This is the only official path that removes the
  2D-shell hop.
  - MediaCodec decodes into an `XR_KHR_android_surface_swapchain`, which is submitted as a quad layer
    (see §1.5).
  - The upstream PixelPilot contributor "iflyhere" is "building an immersive (OpenXR) mode on a Quest 3",
    and PRs #113–#120 are spin-offs of that work. [PROVEN: https://github.com/OpenIPC/PixelPilot/pull/115]
  - Expected gain vs the 2D panel: **about 1 to 2 refresh periods (≈8–17 ms at 120 Hz)**, because the
    SurfaceFlinger virtual display and the shell frame drop out. [INFERRED from §1.4; SPECULATION
    until measured]
- **Meta Spatial SDK `VideoSurfacePanelRegistration`** is the official Kotlin equivalent.
  - "Direct-to-compositor rendering improves performance by avoiding image copying in memory."
  - "Direct-to-surface" connects ExoPlayer or a decoder surface straight to a compositor-layer panel.
  - "if you enable direct-to-surface without direct-to-compositor, your app will crash."
  - [PROVEN: https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-media-playback/]
  - Quest 2 is listed among "currently supported Meta devices that run Android". The minimum OS for the
    Spatial SDK on Quest 2 was not found. [SPECULATION; check the SDK release notes before choosing it]
- **Refresh:** apps pick 72/80/90/120 on Quest 2. Rates above 120 Hz ("extended refresh rates", up to
  240 Hz) are **"exclusive to Meta Quest 3 … not available on any other headset"**.
  [PROVEN: https://developers.meta.com/horizon/documentation/unreal/unreal-change-display-refresh-rate/ ;
  https://skarredghost.com/2026/09/01/meta-quest-207-hz-how-to/]
- **Software support:**
  - Security updates for Quest 2 run until **December 2027**. [PROVEN: https://www.meta.com/help/policies/1268845083754899/]
  - Feature updates run until **December 2026**. [PROVEN (secondary): Meta community post "Updates to Your
    Meta Quest Experience in 2026" (403 to the fetcher), reported via search results and
    https://www.techradar.com/computing/virtual-reality-augmented-reality/meta-sets-oculus-quest-headset-shelf-life-at-six-years-but-theres-still-hope-that-the-meta-quest-2-will-survive-past-2026]
  - The latest Horizon OS is **v2.7 (2026-08-26), based on Android 14**. The Quest 2 was discontinued on
    2024-09-25. [PROVEN: https://en.wikipedia.org/wiki/Meta_Horizon_OS , https://en.wikipedia.org/wiki/Quest_2]
  - Whether v2.7 itself shipped to Quest 2 was not checked. [SPECULATION]
  - **There is no "final" OS yet.** The last feature build is expected around end-2026. [INFERRED]

---

## 4. Custom OS status (public projects only)

- **AOSP / LineageOS / postmarketOS:** no public port for Quest 2 was found.
  - GitHub search for `oculus hollywood` returns only TWRP device trees
    (https://github.com/cualquiercosa327/android_device_oculus_hollywood , last push 2022-10) and
    firmware dumps. Searches for `quest2 linux`, `hollywood kernel oculus` and `quest 2 postmarketos`
    return nothing.
  - The `sm8250-mainline/linux` tree has no "hollywood" or "oculus" hits.
  - [PROVEN: `gh api search/*` run 2026-09-26; https://github.com/sm8250-mainline/linux]
- **Mainline Linux on SM8250 phones works, display included.** One example is Arch Linux ARM on the
  Samsung S20 FE with the panel enabled in the device tree. [PROVEN (secondary):
  https://github.com/sitsirK/r8q-arch] The XR2 is SM8250-derived. [PROVEN as a community claim:
  https://github.com/Nuvido/Quest2_Research/blob/main/System.md]
- **Windows PE was booted natively on a Quest 2 in June 2024.** It ran on a unit unlocked through an old
  2021 firmware vulnerability (details out of scope). The article does not state that the panel showed
  an image. [PROVEN: https://akersys.com/posts/running-windows-pe-natively-on-meta-vr-headset/]
- **What a custom OS would be missing** [INFERRED from the kernel tree in §1.1]:
  1. The dual-DSI + DSC panel bring-up and the per-panel-vendor init sequences. These are public in
     Meta's GPL dts.
  2. The BLU-MCU strobe programming (`0xB9` command) and its scanline placement. This is also public, in
     `dsi_panel.c`.
  3. Lens distortion, chromatic correction and per-eye split. These live in the proprietary compositor.
     Without them the image through the lenses is barrel-warped and colour-fringed.
  4. The tracking SoC ("syncboss") and sensor stack.
  5. The Adreno/Venus userspace blobs, for HW decode.
  - Items 1–2 mean a Linux display bring-up is *technically documented*. Items 3–5 mean you would
    rebuild a VR compositor just to show one flat video.
- **Latency relevance: none that an app-level OpenXR quad layer cannot also get.** The LC settle and
  strobe floor (§1.3) is in the panel. [INFERRED]

## 5. Root / bootloader — public status (high level only)

- **There is no official unlock path for Quest 2.** Meta shipped an official unlocked OS only for
  Oculus Go (2020–2021). Carmack called that "specific to Go" and hoped it "sets a precedent".
  [PROVEN: https://www.uploadvr.com/oculus-go-unlocked-os-available/ , https://roadtovr.com/oculus-go-unlock-root-john-carmack/]
- **The public unlocks are all for old firmware.** The public community unlock applies only to old
  firmware (latest vulnerable Quest 2 build 29.0.0.65.370…, May 2021), and is "PATCHED ON LATEST
  FIRMWARE". [PROVEN: https://github.com/darknight1050/quest-bootloader-unlocker]
  - An XDA thread reports unlocks up to v59. It says a rollback fuse set on v60 prevents downgrading, so
    **units on v60 or later cannot be unlocked by the known public methods**. [PROVEN (search-index
    snippet; page returned 403): https://xdaforums.com/t/quest-2-on-v59-has-been-bootloader-unlocked-aswell.4799802/]
  - A retail Quest 2 that has taken normal OTAs is on Horizon OS v2.x, far past v60, so the answer for
    current firmware is **no**. [INFERRED]
- **Verdict: root would not open any latency lever that matters.** [INFERRED]
  - With root you could in theory change the BLU duty or start scanline, or the DFPS range, through the
    kernel. At most that moves the photon centroid by a fraction of a millisecond, and it risks ghosting
    because the LC settle time would shrink.
  - You could kill or replace the compositor, but then you lose lens correction, and the panel floor of
    about 1.2 refresh periods remains.
  - Everything that removes a whole frame (leaving the 2D shell for a decoder-fed quad layer, 120 Hz,
    low-latency decode) can already be done with **ADB + APK**.

## 6. Hardware alternative

- **Driving Quest 2 panels from an external board: no public project found.** Searches covered
  Hackaday, GitHub and AliExpress. DIY VR headsets use off-the-shelf 2560×1440 5.5" or 2880×1440 2.9"
  panels with HDMI/DP→MIPI boards. Examples: LS055R1SX03 kits (~$21–89); a 2880×1440 120 Hz dual
  2.9" DP→MIPI kit ($149.99). [PROVEN: https://www.aliexpress.com/item/32832376262.html ,
  https://www.aliexpress.com/item/4000184350083.html]
- **Why the Quest 2 panel is hard** [INFERRED from §1.1]:
  - It needs **dual-link 4-lane DSI with DSC 8 bpp**, so the bridge must *encode* DSC at 3664×1920@120.
  - It needs the vendor-specific init sequence, and the right one for the (unknown) panel vendor.
  - It needs the 5.7–5.8 V LCDB rails.
  - It needs the BLU-MCU strobe commands and correct scanline placement, or the image will ghost.
  - It needs the stock lens and housing, plus your own lens-distortion pre-warp in the video source.
  - Cost is likely low in parts (a used Quest 2 screen assembly), but engineering effort is high:
    FPGA or DSC bridge plus firmware. [SPECULATION on cost]
  - **The LC settle and strobe floor (~1 refresh period at the chosen rate) remains** even when driven
    perfectly. [INFERRED]
- **HDZero Goggle 2:**
  - "HDMI input latency: <1ms". [PROVEN: https://www.hd-zero.com/product-page/hdzero-goggle-2]
  - "The current firmware supports resolution up to 1080p60 and 720p100 for HDMI input. The incoming
    HDMI video is routed to the OLED display without adding any frame buffer latency."
    [PROVEN: https://docs.hd-zero.com/goggles-setup]
  - Display: "Full HD 1920x1080p 90fps OLED micro display". Price **$699.99**. [PROVEN: hd-zero.com product page]
  - Its display term is essentially scanout alone: about 0 ms first-line, and ≤10 ms for the last line at
    100 Hz, about 5 ms mid-screen. This is **far below the Quest 2's roughly 17 to 35 ms 2D-panel path.**
    [INFERRED]
  - The remaining cost moves to the ground-station HDMI output: decoder → DRM plane → HDMI scanout. It
    can be measured with the existing ESP32 rig. [INFERRED]

## 7. Final table

G2G budget reminder: 20 ms total. Display-side figures assume the decoded frame is ready. Gains are
relative to the stock case: PixelPilot 2D panel with the shell at 90 Hz and no low-latency decoder keys.

| Option | Works on retail Quest 2 today? | Expected latency gain | Risk | Effort |
|---|---|---|---|---|
| Enable 120 Hz toggle / `debug.oculus.refreshRate 120` | Yes (toggle official; setprop lost at reboot) | −5 to −11 ms if the panel host really runs at 120 [INFERRED]; **verify on device** | Heat and battery; thermal fallback to 72 Hz | Minutes |
| PixelPilot with PR #113 low-latency keys ON | Yes (APK, merged 2026-09-02) | 0 to ~1–2 decoder frames (≈0–17 ms) [SPECULATION] | None | Minutes (update APK) |
| SurfaceView instead of TextureView (PR #114, detection off) | Yes | ≈ one frame (PR's own claim) [PROVEN claim, not measured on Quest] | None | Minutes |
| Immersive OpenXR PixelPilot (decoder → Android-Surface swapchain → quad layer), or Spatial SDK direct-to-surface panel | Yes (app work; extension used on Quest 2 by AVPro) | −1 to −2 refresh periods (≈8–17 ms @120 Hz) vs 2D panel [INFERRED/SPECULATION] | Low; extension support must be probed | Days to weeks (upstream work in progress for Quest 3) |
| CPU/GPU level max, foveation off, guardian paused | Yes (setprop, lost at reboot) | ≈0 ms average; maybe less jitter [SPECULATION] | Heat | Minutes |
| Casting / capture OFF during flights and tests | Yes | Avoids added stalls [INFERRED] | None | None |
| Proximity sensor disable | Yes | 0 ms (bench enabler only) | Battery | Minutes |
| Brightness / BLU persistence change | No (not user-exposed; root would be needed) | ≤0.2 ms [INFERRED] | Ghosting | n/a |
| Disable/bypass compositor (any route) | No | — | — | Impossible without root |
| Root / bootloader unlock | No on current firmware (only ≤ v59 / May-2021 builds via public methods; official: none) | ~0 ms beyond what ADB+APK can do [INFERRED] | Brick; no OTA | High |
| Custom OS (AOSP/Lineage/pmOS/mainline) | No (no public port with display) | Negative in practice (lose distortion correction, HW decode) [INFERRED] | Very high | Months |
| External driver board for Quest 2 panels | No public project | Keeps the ~1-refresh LCD floor; saves the compositor | High | Very high (dual-DSI + DSC + BLU MCU) |
| **HDZero Goggle 2 via HDMI 720p100** | n/a (buy) | Display adds <1 ms first pixel, ~5 ms mid-frame [PROVEN spec + INFERRED] | Low | $699.99 + wiring |

**Bottom line** [INFERRED]:
- **Best case on Quest 2:** immersive decoder-fed quad layer at 120 Hz. The display side alone is about
  14 to 21 ms: 0 to 1 period waiting for the compositor, plus about 1.2 periods from scanout to photons.
- **Adding the rest of the chain** (sensor, encode, link, decode) puts G2G at 25 ms or more.
- **Typical case today** (2D panel, shell at 90 Hz): display side about 25 to 45 ms.
- **Quest 2 is therefore a "comfortable cruising" display, not a 20 ms one.**

## 8. Suggested verification (when device access is permitted — not done here)

Per the project's extreme-value rule, bracket the levers. Do not run single points.

- **Refresh:** 72 vs 90 vs 120, N≥3 each, shuffled order, measured on the ESP32 rig through a lens with
  the proximity sensor held off.
- **Decoder mode:** PixelPilot `Low latency` ON vs OFF.
- **Output path:** 2D panel vs any immersive build.
- **Logging:** record the OVR Metrics refresh rate and stale frames, and
  `dumpsys SurfaceFlinger --latency`, so that a thermal drop to 72 Hz does not contaminate the results.

---

## 9. Audit of prior notes

The file audited is `C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/research/47-quest2-compositor-bypass-deep-research.md`
(June 2026). It was read after §1–8 were written. Each item was checked against the sources above.

**Right (verified):**
- Bootloader unlock is only possible on old (May 2021) firmware; current firmware cannot be unlocked by
  the public method. ✔ (darknight1050 README). The note missed the ≤v59 and v60 rollback-fuse detail.
- Windows PE was booted on an unlocked Quest 2. ✔ (akersys, 2024-06-10). The note did not mention that
  the article never states the panel showed an image.
- The ATW quotes "ATW is automatically applied by the Compositor; you do not need to enable or tune it."
  and "At the refresh interval, the Compositor applies ATW to the last rendered frame." ✔ Verbatim in
  Meta's mobile-timewarp-overview.
- "No property to disable TimeWarp/compositor/front-buffer/low-persistence." ✔ Consistent with Meta's
  system-properties page.
- `debug.oculus.refreshRate`, `foveation.level`, `cpuLevel/gpuLevel` and `textureWidth/Height` exist. ✔
- Operational conclusion "Quest 2 = NO for 20 ms" and "use a fast monitor/goggle". ✔ Same verdict here,
  and it is now backed by the panel-strobe mechanics.
- "Root = no latency gain." ✔ The reasoning is now stronger: the floor sits in the LCD and BLU
  placement, not in Android.

**Wrong:**
- **"PixelPilot already uses a compositor layer (Quad), late-latched, decode direct SurfaceView."** ✘
  - PixelPilot on Quest runs in **"non vr mode"** as a flat 2D Android window.
    [PROVEN: PixelPilot README]
  - It has no OpenXR or quad layer. An immersive OpenXR mode is only now being developed (on Quest 3)
    [PROVEN: PR #115].
  - The panel is hosted by the system shell. The note's main "optimization already done" claim is
    therefore false, and it hid the biggest real lever (§3).
  - It also treated "SurfaceView" as given. PR #108 had switched PixelPilot to TextureView until #114
    reverted that on 2026-09-02.
- **`debug.oculus.phaseSync 0/1` listed as a real property.** ✘ It does not appear in Meta's
  system-properties list or in the gist. Phase Sync is an app or manifest setting for VR apps, and it
  was superseded by FrameSync (default from v203, 2026). It does not apply to 2D panel apps.
- **"`cpuLevel/gpuLevel` 0-1+ forces max clock → less scheduling jitter."** ✘/unsupported. The values
  are device-specific levels, and Meta documents them only as overriding *an app's* level. There is no
  evidence of an effect on a 2D app or on decode.
- **"120Hz is experimental"** (as a current fact). ✘ Outdated: Carmack announced default-on in
  September 2022.
- **Allowed values "60/72/90/(120*)".** ✘ Incomplete. Meta lists 60/72/80/90/120 for Quest 2.
- **"120Hz cuts scan-out from ~14 ms to ~8 ms."** Partly wrong model. Quest 2 is not a rolling-scanout
  display: it scans, waits for the LC to settle, then strobes each BLU at the end of the refresh.
  Refresh does change the per-frame floor (13.9 → 8.3 ms per period), but the right mental model is
  "photons ≈ 1.2 periods after scanout start", multiplied by the number of vsync-paced hops (§1.3).

**Unsupported (claimed but not verified here):**
- "5 independent primary sources", including a Khronos quote ("the application does NOT render directly
  to the display…") and an app-spacewarp quote ("TimeWarp is mandatory … since the platform's
  inception"). These phrasings were not checked; the second one reads like a paraphrase. Only the ATW
  quotes were verified.
- **`COMPOSITOR_SKIP_RENDERING`** (from "previous session"). No Meta source was found; the documented
  broadcast is `COMPOSITOR_SIMULATE_THERMAL`. Treat it as unverified.
- **Hackaday 2025-01 flight anecdotes cited as Quest evidence.** That setup is a **Meta Quest 3** with a
  cheap analog UVC receiver and a video-player app. The commenter says: "about the latency that the
  passthrough has + a little more". [PROVEN: https://hackaday.com/2025/01/03/fpv-flying-in-mixed-reality-is-easier-than-youd-think/]
  The note did not say it was a Quest 3.
- "Quest 2 bought 2021 has almost certainly auto-updated." Plausible, but nobody checked the device.
- "Custom AOSP has no Adreno/display drivers." Half-true. Display bring-up (dual-DSI, DSC, BLU
  commands) **is public** in Meta's GPL kernel; the proprietary pieces are the compositor, distortion
  and codec userspace.

**Missed:**
1. **The actual panel mechanics:** a dual-BLU strobe placed at end-of-refresh, a flash of about 6–12 %
   of the frame, 8–10 % duty, VFP-based DFPS from 60 to 120, DSC 8 bpp, and panels from four vendors.
   This comes from Meta's own GPL kernel, and from Carmack's "wait … for the LCD to settle … before we
   flash the backlight".
2. **The 2D-panel extra hop** (SurfaceFlinger → shell → compositor), and the fact that the **shell** sets
   the panel's refresh (Home at 90 Hz by default).
3. **The one real no-root lever:** an immersive OpenXR decoder-fed quad layer
   (`XR_KHR_android_surface_swapchain`, proven in use on Quest 2 by AVPro), or the Spatial SDK
   `VideoSurfacePanelRegistration` "direct-to-surface".
4. **PixelPilot's own latency bugs:** the low-latency MediaCodec keys were never applied before #113,
   and TextureView was in use before #114.
5. **Quest 2 support timeline:** features until about December 2026, security until December 2027.
   Extended >120 Hz rates are Quest 3 only.
6. **Persistence:** all setprops are lost at reboot. **Thermal throttling** can silently drop to 72 Hz,
   which is a confound for any G2G test.
7. **A quantitative hardware alternative:** the HDZero Goggle 2's HDMI 720p100 and "no frame buffer"
   spec.

---

## Sources (primary first)

- Meta Quest 2 kernel (GPL):
  - https://github.com/facebookincubator/oculus-linux-kernel/tree/oculus-quest2-kernel-master (commit e8c2245c4c, 2026-09-25)
  - `arch/arm64/boot/dts/oculus/hollywood/hollywood-panel.dtsi`
  - `…/hollywood-dsi-panel-{sharp,boe}-dsc-4k-120Hz-video.dtsi`
  - `techpack/display/msm/dsi/dsi_panel.c` (`dsi_panel_jdi_update_backlight`, ~L780–860)
- Carmack, Facebook Connect 2020 keynote: https://www.youtube.com/watch?v=sXmY26pOE-Y (≈18:40–23:30)
- Meta docs:
  - [system properties](https://developers.meta.com/horizon/documentation/native/android/ts-systemproperties/)
  - [ATW overview](https://developers.meta.com/horizon/documentation/native/android/mobile-timewarp-overview/)
  - [compositor](https://developers.meta.com/horizon/documentation/unity/os-compositor/)
  - [missed frames](https://developers.meta.com/horizon/documentation/unity/os-missed-frames/)
  - [refresh rates](https://developers.meta.com/horizon/documentation/unreal/unreal-change-display-refresh-rate/)
  - [v23 90Hz blog](https://developers.meta.com/horizon/blog/-oculus-quest-v23-how-to-update-your-app-for-90hz/)
  - [Phase Sync blog](https://developers.meta.com/horizon/blog/bringing-phase-sync-to-mobile-vr/)
  - [FrameSync blog](https://developers.meta.com/horizon/blog/framesync-meta-horizon-os/)
  - [gameplay latency blog](https://developers.meta.com/horizon/blog/understanding-gameplay-latency-for-oculus-quest-oculus-go-and-gear-vr/)
  - [Super Resolution blog](https://developers.meta.com/horizon/blog/vr-image-quality-meta-quest-super-resolution/)
  - [Android apps](https://developers.meta.com/horizon/documentation/android-apps/horizon-os-apps/)
  - [Spatial SDK media playback](https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-media-playback/)
  - [MQDH](https://developers.meta.com/horizon/documentation/unity/ts-mqdh-basic-usage/)
  - [security update policy](https://www.meta.com/help/policies/1268845083754899/)
- Khronos: [XR_KHR_android_surface_swapchain](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_KHR_android_surface_swapchain.html)
- PixelPilot:
  - [README](https://github.com/OpenIPC/PixelPilot/blob/master/README.md)
  - [PR #113](https://github.com/OpenIPC/PixelPilot/pull/113)
  - [PR #114](https://github.com/OpenIPC/PixelPilot/pull/114)
  - [PR #115](https://github.com/OpenIPC/PixelPilot/pull/115)
- AVPro Quest 2 surface-swapchain use: https://github.com/RenderHeads/UnityPlugin-AVProVideo/issues/2505
- Status and news:
  - [Meta Horizon OS (Wikipedia)](https://en.wikipedia.org/wiki/Meta_Horizon_OS)
  - [Quest 2 (Wikipedia)](https://en.wikipedia.org/wiki/Quest_2)
  - [UploadVR LCD specs](https://www.uploadvr.com/quest-2-lcd-display-detailed-specs/)
  - [UploadVR 90Hz setprop](https://www.uploadvr.com/90hz-games-oculus-quest-2-how-to-virtual-desktop/)
  - [UploadVR 120Hz default-on](https://www.uploadvr.com/quest-2-120hz-no-longer-experimental/)
  - [Android Central v28](https://www.androidcentral.com/oculus-quest-2-v28-update-adds-120hz-wireless-pc-vr-streaming-and-more)
  - [web.dev PWAs on Quest 2](https://web.dev/articles/pwas-on-oculus-2)
  - [Skarredghost 207Hz](https://skarredghost.com/2026/09/01/meta-quest-207-hz-how-to/)
  - [UploadVR Oculus Go unlock](https://www.uploadvr.com/oculus-go-unlocked-os-available/)
- Unlock status (high level only):
  - https://github.com/darknight1050/quest-bootloader-unlocker
  - https://xdaforums.com/t/quest-2-on-v59-has-been-bootloader-unlocked-aswell.4799802/ (403; search snippet)
  - https://akersys.com/posts/running-windows-pe-natively-on-meta-vr-headset/
- ADB gist: https://gist.github.com/t-34400/3bc5f81d9e40b69072c99d5d640b5c89
- HDZero: https://www.hd-zero.com/product-page/hdzero-goggle-2 , https://docs.hd-zero.com/goggles-setup
- Hackaday (Quest 3 anecdote): https://hackaday.com/2025/01/03/fpv-flying-in-mixed-reality-is-easier-than-youd-think/
