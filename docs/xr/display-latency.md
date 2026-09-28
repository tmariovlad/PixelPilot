# Decode → photon on Quest 2: refresh rate, compositor latch, levers (2026-09-28)

Question: what shortens the segment from **"MediaCodec has released a decoded frame into the Android-surface
swapchain"** to **"photons leave the Quest 2 panel"**, and what does each lever buy. Two directions from the user:
(1) a higher refresh rate, (2) making frames show sooner.

Status: **research done, measurements pending** (slot T = Perfetto refresh bracket, slot O = ESP32/LDR on the lens).
Research was done from primary sources and code, from zero; the repo's earlier notes on this topic are audited only at
the end (§6), per the user's rule. Research reports (full citations):
[official sources](research/2026-09-28-display-latency/01-official-sources.md) (OpenXR spec, Meta docs, AOSP) ·
[vendors and community](research/2026-09-28-display-latency/02-vendors-community.md) (ALVR, WiVRn, Virtual Desktop,
Moonlight, forum measurements).

## 1. Answers so far

| Question | Answer | Tag |
|---|---|---|
| A refresh rate above 120 Hz on Quest 2? | **No.** Quest 2: 72/80/90/96/100/120 Hz (60 for media apps). "Meta Quest 3 supports display refresh rates above 120 Hz, up to 240 Hz. This is exclusive to Meta Quest 3 … not available on any other headset." | [PROVEN: <https://developers.meta.com/horizon/documentation/native/android/mobile-display-refresh-rate/>, fetched 2026-09-28] |
| Does the app already ask for 120 Hz? | Yes, by default (`LatencyExperiments.java:41-42`); it picks the highest supported rate ≤ the request (`XrRuntime.cpp:496-516`). | [PROVEN: code] |
| Is 120 Hz guaranteed once requested? | **No.** "If an app with a display refresh rate higher than 72 Hz experiences thermal events, dynamic throttling may change the refresh rate to 72 Hz as a first step." The app does not handle `XrEventDataDisplayRefreshRateChangedFB` (`XrRuntime.cpp:358-375`) and does not log the rate it reads back (`XrRuntime.cpp:551`, HUD only), so a drop to 72 Hz is invisible in logs. | [PROVEN: same Meta doc; code] |
| When does the compositor take the video frame? | Once per **compositor** frame, the newest buffer (mailbox), not per app `xrEndFrame`: without `SYNCHRONOUS` the BufferQueue "always replac[es] the last buffer"; Meta's docs say the Timewarp layer samples the surface. The KHR spec itself says nothing about latch timing. | [PROVEN: spec text quoted in [01 §2](research/2026-09-28-display-latency/01-official-sources.md#2-android-surface-swapchain-when-the-compositor-takes-the-buffer); "per compositor frame" INFERRED] |
| Does the 167 fps video queue up behind a 120 Hz panel? | Not in the one trace examined: buffer-queue depth max 1, decoder `dequeueBuffer` p95 0.38 ms (never blocks), 488/1446 frames never shown (166.2 decoded/s, 110.6 latched/s), decoded → latch mean 3.03 / p95 6.37 ms. Rechecked per step in slot T. | [PROVEN for `scripts/quest/out/mode_a480_d.pftrace` via `latch_analyze.py` + `bq_stats.py`, 2026-09-28] |
| Any path that bypasses the compositor? | None documented for Quest apps (no front-buffer/direct-scanout extension; VrApi is deprecated). | [INFERRED (absence): [01 §6](research/2026-09-28-display-latency/01-official-sources.md)] |
| Published decode → photon for Quest 2? | **None found.** Nearest: camera-measured motion-to-photon at 120 Hz, Link USB, minimal OpenXR app 31–32 ms; Virtual Desktop over Wi-Fi 42.7 ms while its overlay said 30 ms. In-app overlays (ALVR/WiVRn/VD) report `predictedDisplayTime`, not light. | [PROVEN: sources in [02 §4 and table b](research/2026-09-28-display-latency/02-vendors-community.md); anecdotal-vs-official split kept there] |

## 2. Working model

`decode→photon = W + L` [INFERRED: [01 §9](research/2026-09-28-display-latency/01-official-sources.md)]:

- **W**, released buffer → compositor acquire: uniform over one compositor period P when the source is not
  phase-locked, mean P/2 (4.2 ms at 120 Hz, 6.9 ms at 72 Hz) [INFERRED]. The one existing trace gives 3.0 ms mean
  at 120 Hz [PROVEN, §1], below P/2, so the latch cadence or phase is not what the simple model assumes (the same trace
  shows a compositor pass every 4.18 ms, i.e. twice per 8.33 ms refresh [PROVEN: `TW pass interval` p50]) — slot T
  settles this per rate.
- **L**, acquire → mid-flash of the backlight: remaining scan-out + LC settle + half the flash. No official number;
  plausible 0.6–1.4 × P = 5–12 ms at 120 Hz [SPECULATION]. Only slot O (light on the lens) can measure L.

Estimate: **≈ 9–16 ms at 120 Hz, ≈ 13–24 ms at 72 Hz** [SPECULATION on L, INFERRED on W].

## 3. Levers, ranked by expected gain

| # | Lever | Mechanism | Expected Δ at 120 Hz | Tag | Status |
|---|---|---|---|---|---|
| 1 | Run at 120 Hz, not 72 (and make sure it is really granted) | Shorter P shrinks W and L | vs 72 Hz −5 to −10 ms; vs 90 Hz −2 to −4 ms | INFERRED (W) / SPECULATION (L) | Default already 120. **Measure: slot T (W) + slot O (W+L), 72/90/120.** |
| 2 | Detect a silent thermal drop to 72 Hz | Handle `XrEventDataDisplayRefreshRateChangedFB`; log the read-back rate | Avoids a hidden +5–10 ms regression | PROVEN mechanism | Code change prepared after the slots (needs a build) |
| 3 | Phase-align the source to the latch (air-side phase lock) | W from P/2 to the safety margin | up to −3 to −4 ms mean, lower jitter | INFERRED | The only vendor technique that transfers: WiVRn's pacer aims "decoded" at a p99.5 margin + client margin before the headset uses the frame and moves the phase by 1/10 of the error per step [PROVEN: WiVRn `server/compositor/pacer.cpp` L65-69, L161, checked in a local clone]. Needs the air side (coordinator). |
| 4 | Keep non-SYNCHRONOUS (mailbox) | No queue behind the latch | avoids +8.3 ms per queued buffer | PROVEN semantics | Already so |
| 5 | Do not use `USE_TIMESTAMPS` for latency | Can only defer a buffer | 0 at best, +8.3 ms per deferral | INFERRED | Off by default |
| 6 | Match the air fps to the refresh (167 → 120) | Would only help if frames queue | ~0 (no queuing seen) | INFERRED from §1 | **Closed unless slot T shows queuing** (changing the Race preset goes through the coordinator) |
| 7 | CPU/GPU perf levels | `SUSTAINED_HIGH` is already the spec default | 0 | PROVEN default | — |
| 8 | Phase Sync, late latching, SpaceWarp, TimeWarp, FFR | Act on app eye buffers and poses; head-locked layers bypass TimeWarp | 0 | PROVEN (bypass) / INFERRED | Closed by documentation |
| 9 | Compositor bypass / refresh > 120 Hz | Not available on Quest 2 | n/a | PROVEN / INFERRED | Closed |

Correctness finding, no latency effect expected: `XrRuntime.cpp:309` chains `XrAndroidSurfaceSwapchainCreateInfoFB`
with `createFlags = 0`, which the spec forbids ("createFlags must not be 0") [PROVEN:
<https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrAndroidSurfaceSwapchainCreateInfoFB.html>]. Fix: chain the
struct only when a flag is set. Held until after slots T and O so both run on the same build.

## 4. Measurements

### Slot T: Perfetto refresh bracket (pending)

`bash scripts/quest/refresh_bracket.sh rb1 12 120 72 90 72 120 90` (72/90/120 × N=2, shuffled; real link, REC air
config with alink off; the user's prefs backed up and restored; APK md5 recorded at the start). Per step: decoded →
latch (mean/p95), latch → vsync, compositor cadence, frames never shown, buffer-queue depth, and three read-backs of
the rate (trace vsync/compositor cadence, app log, `dumpsys display`). Summary:
`python3 scripts/quest-latch/rb_summary.py docs/xr/data/<csv> <steps.txt> <traces>`.

### Slot O: ESP32/LDR on the lens (pending, needs the user)

`scripts/quest/optical_step.sh backup|step|restore` switches the rate (and XR size 90°) through prefs with the headset
untouched; 25-sample rig runs on COM5 per step (skill `/g2g-latency`), 72/90/120 × N=2 shuffled. This measures the
effect (light), not the proxy (latch).

## 5. Open questions only the device can answer

From [01 §10](research/2026-09-28-display-latency/01-official-sources.md#10-open-questions-that-need-a-device-measurement):
which rates this Quest grants (enumeration vs read-back); one latch per refresh or two; L at 72/90/120; backlight
global or segmented and flash length; `createFlags = 0` ignored or rejected; time to thermal throttle under a
sustained 120 Hz video load.

## 6. Audit of prior notes

To be written after slots T and O (the earlier notes are read only at the end, so they do not anchor the research):
[compositor-phase.md](compositor-phase.md), [phase-lock-protocol.md](phase-lock-protocol.md),
[g2g-budget.md](g2g-budget.md), [decoder-levers.md](decoder-levers.md), and in the OpenIPC repo
`repos/tasks/research/07-meta-quest-2-display.md` and `47-quest2-compositor-bypass-deep-research.md`.

Disclosure: while adding this file to the index in [xr-quest.md](../xr-quest.md) (after §1–§3 were written), the
index's one-line summaries of the earlier notes were visible (latch ~2.1–2.2 ms before vsync, latch → light ~11.9 ms,
display at 119.70 Hz, phase-lock proof of concept −2.4 ms). None of them is used above; the audit will check them
against slots T and O.
