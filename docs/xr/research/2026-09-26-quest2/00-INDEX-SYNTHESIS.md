# Quest 2 as an FPV display: latency, APK, firmware (research 2026-09-26)

> The summary of 3 **independent** research agents (from primary sources, not anchored on the June 2026 docs,
> which are only audited at the end). Key claims **re-verified by me** are marked ✔.
> Tags: `[PROVEN: source]` / `[INFERRED]` / `[SPECULATION]`. **Nothing is measured on the owner's Quest 2.**

## Reports

| # | Report | Topic |
|---|--------|-------|
| 01 | [01-latency-numbers-and-measurement.md](01-latency-numbers-and-measurement.md) | Display path, panel/backlight timing, latency budget, **measurement protocol** |
| 02 | [02-apk-low-latency-options.md](02-apk-low-latency-options.md) | Existing apps, optimal native OpenXR APK design, effort |
| 03 | [03-system-tweaks-cfw-status.md](03-system-tweaks-cfw-status.md) | ADB/system settings, custom OS, root (public status), HW alternative |
| 04 | [04-compositor-latch-timing.md](04-compositor-latch-timing.md) | When the compositor latches a surface-swapchain layer vs vsync, levers (flags/extensions/props), Perfetto latch recipe; corrects 01 §2.3 and 03 §1.3 scaling |

## Verdict

**The Quest 2 CANNOT reach 20 ms G2G, whatever the APK or firmware.** All 3 agents converge independently.
The main cause is the **panel**, not software: the LCD is scanned, the liquid crystal settles, then **each half-panel's backlight flashes once**,
placed at the end of the refresh so it doesn't overlap the next scan-out → the photons come ~0.9–1.3 frames after scan start
[PROVEN ✔: Meta GPL kernel `oculus-linux-kernel@oculus-quest2-kernel-master`, `techpack/display/msm/dsi/dsi_panel.c:780`
`dsi_panel_jdi_update_backlight()` — comment "without overlapping the backlight illumination with the next refresh's scanout"; the ms timings = INFERRED].

| Path (Quest side, from decoded frame → light, @120 Hz) | Estimate | Source |
|---|---|---|
| PixelPilot 2D panel (today) | 01: ~16–33 ms typical · 03: 17–35 ms · 02: 40–70 ms | all [INFERRED]; 2D panel composition undocumented by Meta |
| Native OpenXR + `XR_KHR_android_surface_swapchain` + head-locked quad | 01: best ~11 ms · 02: ~20 ms | [INFERRED] |
| + decode | ~3–6 ms | [INFERRED: 01] |
| **Realistic G2G total** | **~30 ms+** (with air + link) | [INFERRED: 02] |

⚠️ **The agents disagree on the gain from a native APK over 2D:** 01 says ~4–5 ms, 03 says 8–17 ms, 02 says 20–50 ms. Only **a measurement** settles this (protocol in 01).

## What actually helps (ranked)

1. **PixelPilot ≥ v0.25.0** (2026-09-02): before it, the MediaCodec low-latency keys **were never applied** (#113), and the video went through TextureView (+~1 frame) (#114) [PROVEN ✔: `gh api` releases + compare v0.24.0…v0.25.0]. Free, immediate.
2. **120 Hz** (vs 72 Hz): −6…12 ms estimated [INFERRED: 01]; 120 Hz is officially supported on Quest 2 today, not "experimental" [PROVEN: 02/03, Meta docs]. Not yet verified that a 2D panel follows 120 Hz [03].
3. **Native OpenXR APK** (decoder → compositor surface, head-locked quad, 120 Hz): gain 4–50 ms depending on agent (see above). **Nobody has implemented it**: FPVue_xr copies frames through the CPU, PixelPilot_quest redraws and doesn't request 120 Hz [PROVEN ✔: `gehee/FPVue_xr` (2024-05), `gpratas-pereira/PixelPilot_quest` (2025-11) exist]. Effort: prototype 1–2 days (patching PixelPilot_quest), clean app 3–6 days [INFERRED: 02].
4. **Missing decoder keys** (all paths): Qualcomm decode-order, operating-rate, the low-latency decoder variant [INFERRED: 02].
5. The other ADB tweaks ≈ 0 ms; **root/custom OS**: current firmware can't be unlocked, no custom OS with a working display, and they wouldn't remove the panel floor anyway [03].

## Measuring (01 §protocol)

- **The ESP32+LDR rig does NOT work** through the lenses: ~1 ms flashes, ~8 nits average, the LDR is far too slow [PROVEN: display-mode skill; INFERRED: 01]. (Correction note added in 02.)
- Photodiode (BPW34/OPT101) on each lens + OWON → flash timing, pulse width, L/R offset.
- A test app that toggles a USB-serial line at frame release → frame-ready→photon directly, on 2D vs native.
- Android tracing for decode/compositor breakdown; a full LED→photodiode run as a sum check.

## Audit of the June 2026 docs (OpenIPC `07-meta-quest-2-display.md`, `47-quest2-compositor-bypass-deep-research.md`)

- ❌ "PixelPilot's SurfaceView is promoted to a compositor layer with late-latching → tax plausibly <10 ms": **wrong / unsupported**. PixelPilot is a 2D app with no OpenXR [PROVEN ✔: 0 OpenXR hits in the repo; 02]; the source was the Google Android XR docs, not Horizon OS; late-latching doesn't apply to video [01, 02].
- ❌ The compositor's GPU time (~1.25 ms) was confused with the latency through the compositor (~20 ms @72 Hz per Meta's own example) [01].
- ❌ `debug.oculus.phaseSync` doesn't exist as a property; "120 Hz experimental" is outdated; the flight anecdotes were from a Quest 3 [03].
- ❌ The surface-swapchain path and the 2 existing native forks were missed [02].
- ✅ Correct: the compositor can't be bypassed, no usable bootloader unlock, the practical conclusion "Quest 2 is not for 20 ms; monitor for baseline" [01, 03].

## Implementation (2026-09-26)

A native OpenXR APK built on PixelPilot: fork `tmariovlad/PixelPilot`, branch `xr-native`, locally at
`c:/xampp/htdocs/pixelpilot-xr/` → guide + smoke checklist + measurement matrix:
[docs/xr-quest.md](../../../xr-quest.md); design: `docs/superpowers/specs/2026-09-26-quest-openxr-viewer-design.md`.
Implements path C (surface swapchain + head-locked quad, 120 Hz) + switchable decoder levers (picture-order, operating-rate,
low_latency component, whole-AU) — all measurable A/B. **Status: builds + unit tests OK; not yet run on the Quest** [PROVEN: build/test logs 2026-09-26].
Independent final review (Fable): 0 Critical / 8 Important (all fixed, commit `a89774f`) / 11 Minor deferred → [pixelpilot-xr-final-review.md](pixelpilot-xr-final-review.md). Branch pushed: `tmariovlad/PixelPilot@xr-native` (`c020572`, then up to `ea9cadf`).
Post-review work (2026-09-26, no headset): RTP-marker parser tests (mutation-checked), deferred minors fixed, AU close-reason counters on the `dec:` line, new lever `xr_thread_hints`, and an **emulator run** (x86_64 API 34, ARM translation): 2D app unchanged after the refactor [PROVEN: screenshot — status + UDP fallback lines], XR activity fails cleanly without a runtime [PROVEN: logcat `XR unavailable`], and an upstream NULL-`memcpy` crash on codec error was found and fixed (`43876ae`) [INFERRED cause: uninitialised `inputBufferSize` + NDK source; seen as SIGSEGV @0x0]. Decode itself could not be verified on the emulator (its goldfish HEVC decoder failed under the software GPU; the host-GPU rerun was blocked by C: filling up).
**On the Quest 2 (2026-09-26, Wi-Fi test streams, no RTL):**
- XR works: FOCUSED, 120 Hz, video on the compositor surface [PROVEN: logcat].
- **Max operating rate** is the big decoder lever: upstream decode is ~10 ms on the lossy stream, and operating rate roughly halves it.
- On clean streams, **LL keys + operating rate** is the fastest combination:
  - 1.56 ms at H.264 720p, 1.79 ms at H.265 720p, 2.32 ms at H.265 1080p;
  - it is the default on Meta headsets.
- The default OMX decoder beats `c2.qti` by about 1 ms.
- H.264 is slightly faster than H.265.

Tables + CSV: [decoder-levers.md](../../decoder-levers.md) §"First on-device results" [PROVEN]. The "not yet run on the Quest" status above is historical.

**Compositor phase, measured on the Quest (Perfetto trace, 2026-09-26):**
- Horizon latches the video frame **2.1 ms before vsync**, a fixed time: the same at 90 Hz and in timestamp mode [PROVEN].
- Latch → light is **~11.9 ms on average** (10.2 / 13.5 ms for the two halves) [INFERRED: measured latch + kernel flash offsets, report 04 corrected].
- A decoded frame waits **0–8.2 ms (mean 4.0)** for the latch. This is the only term left to optimize: a higher air fps, or phase-locking the air unit to the Quest.
- Estimated G2G with air at 480p/167 fps: **~23–33 ms, mean ~27.5 ms** (the 20.3 ms monitor chain + the Quest terms) [INFERRED].
- **Phase lock, headset side built and proven (commit `60c4f57`):**
  - The app measures frame → latch and reports it (UDP `PPXR1`).
  - A PC stand-in for the air unit, with a PI loop that only adjusts the frame period, brought the mean wait from **~4.0 to ~1.55 ms** (trace-verified, N=2 per arm). ~11% of frames still miss the latch because of Wi-Fi jitter [PROVEN].
  - The Quest 2 display actually runs at **119.70 Hz** [PROVEN].
  - The air-unit side (uplink + VMAX) is not built yet. Details: [compositor-phase.md](../../compositor-phase.md) §"Phase lock".
- **First real link (2026-09-26): Quest 2 + RTL8812AU + OpenIPC air unit at 166 fps. It works.**
  - Real-stream decode was **96 ms**: the decoder held ~16 frames. With `dec_picture_order` (now the default on Quest) it is **~1.4 ms** (N=3 per state) [PROVEN].
  - Compositor wait at 166 fps: 3.08 ms on average [PROVEN].
  - Setup needed: the air unit on wfb-ng with link id 7669206 and a key that matches PixelPilot.
  - Details: [real-link.md](../../real-link.md).
- **G2G budget on the real link (estimated, ~31 ms mean):**
  - Air ~9.3 ms (HIL).
  - Transport ~1.9 ms floor (HIL) + **2.9 ms excess** [PROVEN]: packets are paced ~0.68 ms apart within a frame; cause open.
  - Decode 1.55 ms [PROVEN].
  - Compositor wait 3.1 ms [PROVEN].
  - Panel 11.9 ms (kernel).
  - Details: [g2g-budget.md](../../g2g-budget.md).



## Recommendation

- **For flying with 20 ms → HDZero Goggle 2** (HDMI 720p100, no frame buffer) — see [the EV200D summary §3b](c:/xampp/htdocs/ev300d/tasks/cfw-research-2026-09-26/00-INDEX-SYNTHESIS.md).
- **Quest 2 = relaxed/immersive flying:** PixelPilot ≥ v0.25.0 + 120 Hz right away; a native OpenXR APK only if you want to squeeze out the Quest (target ~30 ms total, not 20).
