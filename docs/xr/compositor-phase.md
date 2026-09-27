# Compositor phase and phase lock (Quest 2)

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

When Horizon takes the video frame relative to vsync, how long a decoded frame waits, and the phase-lock proof of concept that removes most of that wait. Tools: [scripts/quest-latch/](../../scripts/quest-latch/). "Research report 04" below is [04-compositor-latch-timing.md](research/2026-09-26-quest2/04-compositor-latch-timing.md) (index: [Quest 2 research synthesis](research/2026-09-26-quest2/00-INDEX-SYNTHESIS.md)).

## Compositor phase, measured (2026-09-26)

Question: when does Horizon take the video frame relative to vsync, and how long does a decoded frame wait?

Method: a system-wide Perfetto trace (9 s) while the XR app shows H.264 720p60 over Wi-Fi. Config and analysis: [scripts/quest-latch/](../../scripts/quest-latch/) (`compositor.pbtx`, `latch_analyze.py`).
- Anchors:
  - the display HAL's DRM vsync callback (`SDM_EventThread` `HWEventsDRM::VSyncHandlerCallback`);
  - the latch, i.e. `acquireBuffer` of our video `SurfaceTexture` on `OVR::TimeWarp` in `com.oculus.vrruntimeservice`;
  - the compositor passes (`dequeueBuffer - TotallyFake`);
  - frame ready (`queueBuffer` on the decoder's `CodecLooper`).
- Kernel `drm`/`sde` ftrace events are not recorded on this user build. The SurfaceFlinger `HW_VSYNC` counter jitters by ±0.5 ms, so it is not used.

| Quantity | 120 Hz | 120 Hz + timestamps | 90 Hz |
|---|---|---|---|
| Latch → next vsync (mean, p5–p95) | **2.14** (1.93–2.39) | 2.15 (1.98–2.32) | 2.22 (2.13–2.34) |
| Latch → compositor pass start | 0.40 | 0.40 | 0.42 |
| Compositor pass interval | 4.18 (2 per frame) | 4.18 | 5.57 |
| Frame ready → latch (mean, p5–p95, max) | **4.03** (0.13–7.64, 8.20) | 4.12 | 5.19 (max 10.82) |
| Decoded frames never latched | 99 / 513 | 5 / 522 | 16 / 522 |

- **The latch comes a fixed ~2.1–2.2 ms before vsync**, whatever the refresh rate and timestamp mode. It is not a full frame, nor half a frame [PROVEN: trace]. The earlier half-frame estimate (research report 04) is corrected there.
- The compositor runs two passes per frame, one per display half. **The video buffer is taken only before the first pass**, and the second pass (~2.2 ms after vsync) reuses it [PROVEN].
- **Latch → light.** The kernel places each backlight half's flash at ~8.0 ms and ~11.35 ms after vsync at 120 Hz (0.5–0.8 ms long depending on brightness) [PROVEN: `dsi_panel.c:780-860` in Meta's Quest 2 kernel + `hollywood-dsi-panel-boe-dsc-4k-120Hz-video.dtsi`]. So latch → mid-flash is **10.2 / 13.5 ms, ~11.9 ms averaged** [INFERRED: measured latch + kernel offsets; not yet photodiode-checked].
- **The wait is the only term the app side can still shrink.** It is uniform between 0 and the smaller of the air frame period and the display period. That gives a mean of ~4.2 ms with a 120 fps air unit, ~3.0 ms at 167 fps and ~2.1 ms at 240 fps [INFERRED]. With a 120 fps air unit and an unsynchronised clock, the phase drifts slowly, so latency wanders across the whole 0–8.3 ms range over minutes [INFERRED: crystal ppm offsets].
- Buffer selection:
  - Without timestamps, 99 frames that arrived in pairs over Wi-Fi were replaced before any latch. That fits replace-latest, i.e. mailbox, behaviour [INFERRED].
  - With timestamps, almost every frame was shown, which fits queue (FIFO) behaviour that would add latency. This is a single run [SPECULATION], so keep `xr_use_timestamps` off.
- **Levers that do not move the latch:** refresh rate, timestamp mode [PROVEN]. Research report 04 found no property or extension that moves it either. At 120 Hz a 60 fps stream is latched at the next opportunity, and 120 Hz beats 90 Hz by ~1.2 ms of wait plus the shorter panel path.
- Side note: the OpenXR runtime client calls `eglGetDisplay` and `open` once per frame on our XR thread, ~30 µs each time. This is not on the video path.

**Resulting G2G estimate, with the air unit at 480p/167 fps:**

| Segment | ms | Tag |
|---|---|---|
| LED → RTP arrival (air + link) | ~11.2 | from the measured 20.3 ms monitor chain |
| Decode | ~1.5 | measured |
| Wait for latch | ~3.0 (0–6) | inferred |
| Latch → light | ~11.9 (10.2–13.5) | inferred |
| **Total** | **~27.5 (≈23–33)** | inferred |

**Next lever: phase-lock the air unit to the Quest.**
- The app can see the vsync grid (Choreographer or `xrWaitFrame`'s `predictedDisplayTime`) and each frame's arrival time.
- It would send the air unit a small frame-period correction, a few sensor lines of VMAX, so frames arrive ~1 ms before the latch. That gives a mean wait of ~1 ms and stable latency, −2…3 ms [INFERRED].
- It needs an uplink and air-side support, so it is a separate project.
- **Update, same day:** the headset side is built and proven against a PC stand-in for the air unit: mean wait −2.4 ms. See "Phase lock" below.

## Phase lock: steering the source onto the compositor latch (proof of concept, 2026-09-26)

**Goal:** remove the 0–8 ms wait for the latch by having the video source time its frames so they land just before it. On Quest 2 this is the practical equivalent of "vsync off": the display timing cannot be changed, so the source is locked to it instead.

**Headset side (the app only measures):**
- The decoder records the time each frame is handed to the surface (`FrameTimeLog`, CLOCK_MONOTONIC).
- `XrRuntime` records `predictedDisplayTime` and the period from every `xrWaitFrame`, converted to CLOCK_MONOTONIC via `XR_KHR_convert_timespec_time`.
- Every 250 ms, `CompositorPhase` computes the circular mean of the wait until the next latch with `PhaseMeter` (latch = `predictedDisplayTime − xr_latch_to_display_us`).
- It shows the result on the stats panel (`phase:` line). If `xr_phase_report` = `host:port` is set, it also sends one `PPXR1 …` UDP line (`PhaseReport`) to the source.

**Source side:** [scripts/quest-latch/rtp_pace.py](../../scripts/quest-latch/rtp_pace.py) is a stand-in for the air unit. It runs a PI controller that changes **only the frame period**, the way an air unit would nudge sensor VMAX, and never jumps the phase. Its offline check is [test_rtp_pace.py](../../scripts/quest-latch/test_rtp_pace.py): simulated at 60 fps into 120 Hz with 80 ppm offset and 0.5 ms jitter, the wait falls from 4.16 ms to 1.03 ms.

**Calibration** ([calibrate_latch.py](../../scripts/quest-latch/calibrate_latch.py), using the app's `ppxr_*` trace markers) [PROVEN: Perfetto trace]:
- latch → `predictedDisplayTime` = **3407 µs** (p5–p95 3270–3617). This is `LatencyExperiments.DEFAULT_LATCH_TO_DISPLAY_US`.
- App frame-ready → compositor `queueBuffer` = 175 µs median, 622 µs p95. The margin has to cover this.
- **The Quest 2 "120 Hz" display runs at 119.70 Hz** (period 8.3545 ms from `predictedDisplayPeriod`). Against a 60.000 fps source that is ~2500 ppm, or ~2.5 ms/s of phase drift.

**A/B on the Quest** (Wi-Fi stream from the PC, 40 s runs, alternating lock/open, N = 2 each; judged by the Perfetto trace of the last 9 s, not by the app's own report). Raw: [measurements-2026-09-26-quest2-phase-lock.csv](data/measurements-2026-09-26-quest2-phase-lock.csv).

| Wait, compositor `queueBuffer` → latch | open loop | **phase lock** (target 1.2 ms) |
|---|---|---|
| mean | 4.10 / 3.88 ms | **1.60 / 1.53 ms** |
| median | 4.50 / 4.05 ms | **0.91 / 0.87 ms** |
| frames waiting > half a period (missed latch when locked) | 53 / 49 % (uniform phase) | 11.1 / 10.5 % |

- **Mean wait −2.4 ms (−61 %), median −3.4 ms** [PROVEN].
- The controller settled at **+42…47 µs per frame**, matching the 119.70 Hz display [PROVEN: pace logs]. A real air unit and the Quest will also differ by hundreds to thousands of ppm, so a fixed "120 fps" never stays aligned without this loop [INFERRED].
- **~11 % of frames still miss the latch** and wait a full period. The cause is Wi-Fi arrival jitter in this rig [INFERRED: missing frames cluster where the Wi-Fi stream bunches]. With the RTL8812AU the transport jitter is different and has to be re-measured. The margin (`--target-us`) trades mean wait against misses.
- **Air-unit side, not built yet:** receive `PPXR1` over the uplink and nudge the frame period. The report format and the reference controller are specified in [phase-lock-protocol.md](phase-lock-protocol.md). PixelPilot's adaptive-link already sends messages up to the air unit, so that is the natural transport. On the air unit, a PI loop on sensor VMAX (1 line ≈ µs) is needed; see the `imx415`/`waybeam` work in the OpenIPC project.

**Known issue seen during this work (upstream wfb path, not the phase lock):**
- Hot-plugging the RTL8812AU while the app runs crashed it twice [PROVEN: tombstones 2026-09-26 20:51/20:52].
  1. `devourer::UsbTransport::ctrl_read` threw `ios_base::failure` ("rtw_read") from the EEPROM read in `CreateRtlDevice`, and nothing catches it in `WfbngLink::run` → abort.
  2. `libusb_submit_transfer` segfaulted in `~RtlJaguarDevice` → `rtw_hal_deinit` on a device that had already gone.
- The third enumeration worked. This needs a fix (catch and retry in `WfbngLink::run`; skip hardware de-init on a dead handle).
