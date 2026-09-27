# Phase lock: the PPXR1 report and the reference controller

Quest XR docs: [guide](../xr-quest.md) · [compositor phase + phase lock](compositor-phase.md) · [G2G budget](g2g-budget.md) · [real link](real-link.md) · [troubleshooting](troubleshooting.md) · repo rules in [CLAUDE.md](../../CLAUDE.md)

The headset measures where decoded frames land relative to the compositor latch and reports it; the video source owns the control loop and steers only its frame period (on the air unit: sensor VMAX). This page is the contract for an air-side implementation (OpenIPC AU-04). The measured result of the proof of concept is in [compositor-phase.md](compositor-phase.md#phase-lock-steering-the-source-onto-the-compositor-latch-proof-of-concept-2026-09-26).

## The report (headset → source)

- **Transport:** one UDP datagram per report, one ASCII line, `\n`-terminated, US locale [PROVEN: `app/xr/src/main/java/com/openipc/xr/PhaseReport.java:17-18`].
- **Format:** `PPXR1 seq=<n> frames=<n> wait_us=<int> conc=<0.000..1.000> period_us=<int>\n`, e.g. `PPXR1 seq=7 frames=1 wait_us=1500 conc=1.000 period_us=8333` [PROVEN: `PhaseReportTest.java:10`]. The `PPXR1` prefix is the version and the only discriminator.
  - `seq`: report counter, +1 per report, from 1 (per app session).
  - `frames`: decoded frames measured in this report's window.
  - `wait_us`: **circular mean** of the wait from frame-ready to the next compositor latch, in [0, period) [PROVEN: `PhaseMeter.java`].
  - `conc`: mean resultant length of those phases; 1 = all frames at the same phase, 0 = spread uniformly.
  - `period_us`: display period, from OpenXR `predictedDisplayPeriod` (Quest 2 "120 Hz" is **119.70 Hz, 8354.5 µs**) [PROVEN: compositor-phase.md calibration].
- **Rate:** once per stats tick, every **250 ms** (`XrVideoActivity.java:35`), over the frames decoded since the previous tick. Only sent when the display grid is on CLOCK_MONOTONIC (`CompositorPhase.java` `monotonic`).
- **Destination:** the pref `xr_phase_report` = `host:port`; empty = reporting off (`LatencyExperiments.KEY_XR_PHASE_REPORT`, `PhaseReport.Target.parse`). The PC stand-in used port **5610** (`scripts/quest/quest_env.py:57`). For the air unit over the wfb tunnel: `10.5.0.10:5610` (Quest `tun0` 10.5.0.3 → uplink radio port 160 → the air unit's `wfb_rx -u 5800` → `wfb_tun` at 10.5.0.10; see the tunnel entry in [troubleshooting.md](troubleshooting.md)). Any free UDP port works as long as both ends agree; 5610 avoids 5600–5602 and 9999 (adaptive link).
- **Reference points:**
  - frame-ready = `clock_gettime(CLOCK_MONOTONIC)` right after `AMediaCodec_releaseOutputBuffer(..., render=true)` for the displayed decoder (`app/videonative/src/main/cpp/VideoDecoder.cpp`, `checkOutputLoop`);
  - latch = OpenXR `predictedDisplayTime − xr_latch_to_display_us`, default **3407 µs** (`LatencyExperiments.DEFAULT_LATCH_TO_DISPLAY_US`), calibrated from the compositor's `acquireBuffer` in a Perfetto trace (`scripts/quest-latch/calibrate_latch.py`).
  - So `wait_us` ≈ the time a finished frame waits for the compositor; the source wants it small but not so small that jitter makes frames miss the latch.
- **Loss:** reports travel on the tunnel uplink (FEC 1/5) and can be lost (the first tunnel test lost ~20 % of pings end to end); `seq` gaps show it. The controller must simply hold its last output when reports stop.

## The reference controller (PC stand-in)

[scripts/quest-latch/rtp_pace.py](../../scripts/quest-latch/rtp_pace.py), class `PhaseLock`; offline check [test_rtp_pace.py](../../scripts/quest-latch/test_rtp_pace.py).

- **Input:** `err = wrap(wait_us − target_us, period_us)`, wrapped into (−period/2, period/2] so a wait just below a period and just above zero are near each other (no jump across the phase wrap). Reports with `frames < 3` are ignored.
- **Sign:** `err > 0` → frames wait too long → the source is early → **lengthen** the frame period (drift later). On the air unit: +VMAX.
- **Law:** PI on the phase error, output = frame-period correction `u` (seconds), applied as `period = 1/fps + u`; the phase is never jumped.
  - `u = kp·err/fps + I`, `I += ki·err/fps`, with `kp = 0.5`, `ki = 0.05`;
  - both `I` and `u` clamped to `±max_ppm·1e-6/fps`, `max_ppm = 5000`;
  - updated once per report (4 Hz); no deadband.
- **Target:** `--target-us` (1000 µs in the test; 1200 in the A/B). The margin trades mean wait against misses.
- **Result** (60 fps source into the 119.70 Hz display, over Wi-Fi): mean wait 4.1/3.9 → 1.60/1.53 ms (**−2.4 ms**), median −3.4 ms, ~11 % of frames still missed a latch because of Wi-Fi arrival jitter; the loop settled at +42…47 µs per frame, i.e. it tracked the 119.70 vs 120 Hz offset [PROVEN: compositor-phase.md, data/measurements-2026-09-26-quest2-phase-lock.csv].

## Notes for an air-unit implementation

- **The source must run at the display rate (119.70 fps) or an integer multiple.** `PhaseMeter` averages the phase of every decoded frame; a 166 fps source against a 119.70 Hz latch grid sweeps through all phases (`conc` near 0) and there is nothing to lock. At 480p167 (the W3 latency winner, [g2g-budget.md](g2g-budget.md#mode-choice-for-minimum-latency-1080p90-vs-720p120-vs-480p167-w3-2026-09-27)) the compositor already takes the newest frame each period (wait ~3.1 ms mean); a lock would need 480p at ~119.7 fps (or ~239.4) and is worth it only if its mean wait beats that [INFERRED].
- **A source at 2× the display rate breaks the current report.** At ~239.4 fps consecutive frames sit at phases 0 and P/2 of the latch grid; the circular mean over all frames cancels (`conc` ≈ 0, `wait_us` meaningless). An air unit locking at 2× needs an app change first: measure the phase modulo P/2 (the same `PhaseMeter` with half the period) or only the frames that were actually latched, and mark it in the report (a new field or `PPXR2`) [INFERRED from `PhaseMeter.measure`]. **Update:** ~239.4 fps is not reachable on the IMX415 (VMAX floor ~1205–1222 lines vs the ~847 needed) [OpenIPC repo 8dfc426, AU04-A report (session c8)], so this case is moot for this air unit and 119.7 fps is the only lock point. Earlier reasoning: at 119.7 fps the lock's gain (~3.0 → ~1–1.5 ms wait) is eaten by the longer capture phase (an event waits period/2 for the next exposure: 4.18 vs 3.0 ms) and the larger frames [INFERRED].
- **Actuator resolution:** one VMAX line = 1H ≈ 4.9 µs on the current IMX415 driver (HMAX 365 at 74.25 MHz; OpenIPC `w3-readout-per-mode.md`). The reference `u` is continuous; on the air unit accumulate the fractional lines (dither) rather than rounding each update, or the loop limit-cycles by ±1 line. `max_ppm = 5000` at 120 fps is ±41.7 µs, i.e. about ±8 lines.
- **Loop timing:** reports arrive every 250 ms plus tunnel delay; the reference gains were tuned for that rate. Hold the output on missing reports; restart the integrator after a mode/fps change.
