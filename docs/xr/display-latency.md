# Decode → photon on Quest 2: refresh rate, compositor latch, levers (2026-09-28)

Question: what shortens the segment from **"MediaCodec has released a decoded frame into the Android-surface
swapchain"** to **"photons leave the Quest 2 panel"**, and what does each lever buy. Two directions from the user:
(1) a higher refresh rate, (2) making frames show sooner.

Status: **research done; slot T (Perfetto refresh bracket) done, §4; slot O (ESP32/LDR on the lens) pending.**
Headline from slot T: at 167 fps in, the wait for the compositor latch is ~3 ms at 72, 90 and 120 Hz alike, because
it is bounded by the source interval rather than the refresh period. Whatever 120 Hz buys has to be after the latch,
which only slot O can see.
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
| Does the 167 fps video queue up behind the panel? | **No, at 72, 90 and 120 Hz**: buffer-queue depth max 1 in all six slot-T traces; 456–829 of ~1448 frames per 9 s are simply never shown. (First seen in `scripts/quest/out/mode_a480_d.pftrace`: `dequeueBuffer` p95 0.38 ms, never blocks.) | [PROVEN: §4 slot T; `latch_analyze.py` + `bq_stats.py`] |
| Any path that bypasses the compositor? | None documented for Quest apps (no front-buffer/direct-scanout extension; VrApi is deprecated). | [INFERRED (absence): [01 §6](research/2026-09-28-display-latency/01-official-sources.md)] |
| Published decode → photon for Quest 2? | **None found.** Nearest: camera-measured motion-to-photon at 120 Hz, Link USB, minimal OpenXR app 31–32 ms; Virtual Desktop over Wi-Fi 42.7 ms while its overlay said 30 ms. In-app overlays (ALVR/WiVRn/VD) report `predictedDisplayTime`, not light. | [PROVEN: sources in [02 §4 and table b](research/2026-09-28-display-latency/02-vendors-community.md); anecdotal-vs-official split kept there] |

## 2. Working model

`decode→photon = W + L` [INFERRED: [01 §9](research/2026-09-28-display-latency/01-official-sources.md)]:

- **W**, released buffer → compositor acquire: uniform over one compositor period P when the source is not
  phase-locked, mean P/2 (4.2 ms at 120 Hz, 6.9 ms at 72 Hz) [INFERRED]. The one existing trace gives 3.0 ms mean
  at 120 Hz [PROVEN, §1], below P/2, so the latch cadence or phase is not what the simple model assumes (the same trace
  shows a compositor pass every 4.18 ms, i.e. twice per 8.33 ms refresh [PROVEN: `TW pass interval` p50]) — slot T
  settles this per rate. **Corrected by slot T (§4):** with a 167 fps source into a mailbox, W ≈ half the *source*
  interval (~3 ms) at every refresh rate, not P/2; the refresh rate only moves the tail [PROVEN: §4 table].
- **L**, acquire → mid-flash of the backlight: remaining scan-out + LC settle + half the flash. No official number;
  plausible 0.6–1.4 × P = 5–12 ms at 120 Hz [SPECULATION]. Only slot O (light on the lens) can measure L.

Estimate: **≈ 9–16 ms at 120 Hz, ≈ 13–24 ms at 72 Hz** [SPECULATION on L, INFERRED on W].

## 3. Levers, ranked by expected gain

| # | Lever | Mechanism | Expected Δ at 120 Hz | Tag | Status |
|---|---|---|---|---|---|
| 1 | Run at 120 Hz, not 72 (and make sure it is really granted) | Shorter P shrinks L; W barely moves at 167 fps in | W: −0.4 ms mean / −1.5 ms p95 vs 72 Hz [PROVEN, slot T]; L: −2 to −7 ms [SPECULATION] | PROVEN (W) / SPECULATION (L) | Default already 120 and granted. **L: slot O decides.** |
| 2 | Detect a silent thermal drop to 72 Hz | Handle `XrEventDataDisplayRefreshRateChangedFB`; log the read-back rate | Avoids a hidden regression after the latch (size = what slot O measures for 72 vs 120) | PROVEN mechanism | **Done and verified on the headset** (`ce885fb`, APK `a6f1f2a5`, §4): the event is logged (from → to), the rate read back after the request is logged, `RefreshWatch` logs every applied-rate change and marks the HUD line " BELOW REQUEST" (JVM test `RefreshWatchTest`). The "(requested -1)" wording for a rate seen before the request is fixed in `4908857` (not installed yet). |
| 3 | Phase-align the source to the latch (air-side phase lock) | W from its current mean to the safety margin | at most ~−2 to −2.5 ms mean at 167 fps (W is ~3 ms, not P/2 — slot T), and it needs the source at the display rate (fewer fps) | INFERRED | The only vendor technique that transfers: WiVRn's pacer aims "decoded" at a p99.5 margin + client margin before the headset uses the frame and moves the phase by 1/10 of the error per step [PROVEN: WiVRn `server/compositor/pacer.cpp` L65-69, L161, checked in a local clone]. Needs the air side (coordinator). |
| 4 | Keep non-SYNCHRONOUS (mailbox) | No queue behind the latch | avoids +8.3 ms per queued buffer | PROVEN semantics | Already so |
| 5 | Do not use `USE_TIMESTAMPS` for latency | Can only defer a buffer | 0 at best, +8.3 ms per deferral | INFERRED | Off by default |
| 6 | Match the air fps to the refresh (167 → 120) | Would only help if frames queue | ~0; lowering the source rate would *raise* W (a 120 fps source has an 8.3 ms frame interval instead of 6.0 ms) | PROVEN (no queuing at 72/90/120, slot T) / INFERRED | **Closed** |
| 7 | CPU/GPU perf levels | `SUSTAINED_HIGH` is already the spec default | 0 | PROVEN default | — |
| 8 | Phase Sync, late latching, SpaceWarp, TimeWarp, FFR | Act on app eye buffers and poses; head-locked layers bypass TimeWarp | 0 | PROVEN (bypass) / INFERRED | Closed by documentation |
| 9 | Compositor bypass / refresh > 120 Hz | Not available on Quest 2 | n/a | PROVEN / INFERRED | Closed |

Correctness finding, no latency effect expected: `XrRuntime.cpp:309` chains `XrAndroidSurfaceSwapchainCreateInfoFB`
with `createFlags = 0`, which the spec forbids ("createFlags must not be 0") [PROVEN:
<https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrAndroidSurfaceSwapchainCreateInfoFB.html>]. Fix: chain the
struct only when a flag is set. **Fixed in `5a483d3` and verified on the headset** (APK `a6f1f2a5`, §4): video
attaches, no swapchain-creation error, and the mailbox is unchanged (buffer-queue depth max 1, decoded → latch ~3 ms).

## 4. Measurements

### Slot T: Perfetto refresh bracket (done 2026-09-28, Quest epoch 1790582178–1790582340)

Setup [PROVEN: air read by the coordinator at 1790582163]: real link, air unit REC (480p167, 2000 kbit/s, MCS2,
STBC/LDPC, FEC 4/8, 12 dBm, 42 °C), `alink_air` stopped so the link stays fixed. Headset stationary, Guardian paused
during the slot and restored after. APK md5 `65deee8d4e27b88ed84495f31a6773a2` (0.23.0-xr-debug) [PROVEN: `pm path` +
`md5sum` on the headset]. Run: `bash scripts/quest/refresh_bracket.sh rb1 12 120 72 90 72 120 90`; summary
`python3 scripts/quest-latch/rb_summary.py docs/xr/data/display-latency-rb1.csv <steps.txt> <6 traces>`.
Raw per-step data: [data/display-latency-rb1.csv](data/display-latency-rb1.csv).

| Step | Requested | Applied: app log / `dumpsys` active mode / latched per s | Decoded → latch mean / p50 / p95 (ms) | Never shown (of ~1448 in 9 s) | BQ depth max |
|---|---|---|---|---|---|
| 1 | 120 | 120 / 120.00001 / 114.4 | 3.02 / 2.61 / 6.51 | 456 | 1 |
| 2 | 72 | 72 / 72.00001 / 71.3 | 3.47 / 2.97 / 8.09 | 829 | 1 |
| 3 | 90 | 90 / 90.0 / 88.5 | 3.38 / 3.26 / 7.75 | 679 | 1 |
| 4 | 72 | 72 / 72.00001 / 71.2 | 3.38 / 3.03 / 7.95 | 829 | 1 |
| 5 | 120 | 120 / 120.00001 / 114.1 | 2.98 / 2.59 / 6.43 | 461 | 1 |
| 6 | 90 | 90 / 90.0 / 88.3 | 3.37 / 3.17 / 8.13 | 682 | 1 |

[PROVEN: `docs/xr/data/display-latency-rb1.csv`; `scripts/quest/out/rb_rb1.steps.txt`; `rb_rb1_<n>_<hz>.display.txt`]

- **Every requested rate was applied, and no thermal drop happened in the slot**: the three read-backs agree per step
  [PROVEN, table]. Horizon OS on this Quest 2 lists 60–120 Hz in 1 Hz steps as alternative rates of the 120 Hz mode
  [PROVEN: `rb_rb1_1_120.display.txt`, `supportedModes`].
- **The wait for the latch barely depends on the refresh rate at 167 fps in**: 72 → 120 Hz changes it by −0.4 ms mean
  and −1.5 ms p95, with N = 2 agreeing within 0.1 ms [PROVEN, table]. The model in §2 (mean P/2 = 6.9 / 5.6 /
  4.2 ms) is wrong for this source. Because the queue is a mailbox and a new frame arrives every 6.0 ms, the latched
  frame is the newest one, and its age is bounded by the **source** interval: ~3 ms mean, set by the 167 fps
  source rather than by the refresh rate [INFERRED: mailbox (depth max 1) + 166.6 fps decoded + measured means
  ≈ 6.0 / 2]. The small residual rise at 72 Hz is in the tail (p95), where a late frame waits for the next latch.
- **No queuing at any rate** (depth max 1): matching the air fps (lever 6) stays closed [PROVEN, table].
- What the trace cannot show: latch → photon (L). The traces have no vsync callbacks on this build/OS
  (`vsync_period_ms` empty for all six), so any gain from 120 Hz lies in L, and only slot O can measure it
  [INFERRED].
- The `TW pass interval` column is not a usable rate read-back: 4.18 / 4.59 / 6.56 / 9.45 / 4.18 / 4.61 ms across
  steps, inconsistent within the same rate [PROVEN: csv]. The latch rate and `dumpsys` are the read-backs to use.

### Install check of `a6f1f2a5` (2026-09-28, Quest epoch 1790582866–1790582960)

Build `a6f1f2a5231ace8ddf3b04f88a9601b3` = `c2a2043` + `ce885fb` (refresh-rate visibility) + `5a483d3` (createFlags);
rollback copy of the previous `65deee8d` pulled from the headset first. Same air setup as slot T (REC, alink
stopped; coordinator read-back at 1790582844).

- **The event path works** [PROVEN: logcat 11:07:48–49, `scripts/quest/out/install_a6f1_logcat.txt`]: the runtime
  starts the session at its own rate and reports `72 -> 90 Hz` before the app asks; then `requested 120 Hz -> 120 Hz
  (result 0)`; the read-back right after the request still says `90 Hz` (the change is asynchronous); `display refresh
  rate changed 90 -> 120 Hz` arrives 65 ms later. VrApi: `FPS=120/120`. So a read-back taken right after the
  request is not the applied rate; the event is.
- **The createFlags fix kept the mailbox** (`refresh_bracket.sh cf1 12 120 120`,
  [data/display-latency-cf1-a6f1f2a5.csv](data/display-latency-cf1-a6f1f2a5.csv)) [PROVEN]: decoder 166.6 / 166.8 fps,
  latched 114.1 / 113.0 per s, buffer-queue depth max 1, decoded → latch 3.07 / 2.70 / 6.51 and 3.05 / 2.67 /
  6.48 ms (mean / p50 / p95), against 3.02 / 2.61 / 6.51 and 2.98 / 2.59 / 6.43 at 120 Hz in slot T on `65deee8d`.
- Also checked for the coordinator's O114 (a) gate: the tunnel is up (the app sends 4 reports/s; the air unit's
  `wfb-tun` rx counter rose 187 → 207 in 5 s, read by the coordinator).

### Slot O: ESP32/LDR on the lens (pending, needs the user)

`scripts/quest/optical_step.sh backup|step|restore` switches the rate (and XR size 90°) through prefs with the headset
untouched; 25-sample rig runs per step (skill `/g2g-latency`; rig port auto-detected by `find_rig_port.py`, never COM5 = the DPS-150), 72/90/120 × N=2 shuffled. This measures the
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
