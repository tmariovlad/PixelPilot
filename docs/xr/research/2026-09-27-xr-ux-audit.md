# XR mode: robustness and UX audit, from the pilot's seat (2026-09-27)

Read-only code audit of branch `xr-native` at `20d3ba5` plus the uncommitted working tree of the same day
(`TxFrame.cpp/.h`, `WfbngLink.cpp` modified by another session). Nothing was built, run or put on a device.
Question asked: what goes wrong, or what the user cannot see, when they put the headset on and fly?

Tags: **[PROVEN: file:line]** means read in the code. **[INFERRED: from ...]** means deduced from proven facts.
**[SPECULATION]** means a hypothesis about Horizon OS or runtime behaviour that the code cannot settle; each one
says how to check it on the Quest. "Panel" means the XR stats panel. Paths are relative to the repo root.

Excluded on purpose, because they are already known and handled:

- The `startService` crash with the display off. It is fixed by binding (`1b32770`, `cae687c`) and verified in
  [troubleshooting.md](../troubleshooting.md). The bind change covers every path: no production code calls
  `startService`/`startForegroundService`/`stopService` any more, and the only binds are
  `VideoActivity.java:1391,1546` and `XrVideoActivity.java:115` [PROVEN: grep over `app/src/main/java`].
- The UDP 8001 leak. It is reported in [troubleshooting.md](../troubleshooting.md) and a fix is in progress in the
  working tree (see X22).

---

## Status of the fixes (updated 2026-09-27)

| Fix | Items | Commit | On the headset |
|---|---|---|---|
| 1 signal state + alert | X10, X06, X08, X09, X05 | `8d7728e`, `487832b` (+ native X08 `dc58403` by 2c6ae8) | verified ([xr-quest.md](../../xr-quest.md#use)) |
| 2 readable panel | X11 | `8d7728e`, `487832b` | verified |
| 5 per-launch leaks | X21 | `8d7728e` | weak evidence (N=2) |
| key validation | X24 | `8d7728e` | verified (32-byte key → SETUP, no crash) |
| 4 link self-healing, USB attach/permission | X17, X14 (part X15) | `c27f8aa` (Java), `ac740e0` (native guard) | link restarts by itself after a replug, 3/3 ([hands-on checks](#hands-on-checks-with-the-user-2026-09-28)); no permission dialog appeared |
| 3 telemetry + MAVLink lifecycle | X12 | `a6c28f2`, home fix `11cb1a7` | telemetry line verified with synthetic MAVLink; 2D↔XR restart weakly; home fix verified in the [final slot](#final-slot-on-the-headset-2026-09-27) |
| X15 attach pulls XR to 2D | X15 | **confirmed 3/3** on the headset; the manifest trampoline is next | the pilot stayed in 2D after the 2nd replug ([hands-on checks](#hands-on-checks-with-the-user-2026-09-28)) |
| XR start errors visible, levers re-applied, bandwidth fallback, loop back-off | X13, X04, X27, X25 | `a8b35de` | not yet |
| minimal input in XR (panel detail / hide) | X01 | `3a37a88` | A and B verified on the headset; X/Y share the bindings, not pressed ([hands-on checks](#hands-on-checks-with-the-user-2026-09-28)) |
| VPN null establish() / bind leak | X26 | fixed by session 2c6ae8 ("survives a null establish()") | - |
| decoder rebuilds after failures (a, b); ~~and on SPS change (c)~~ | X23 | `c0f41f2`; (c) withdrawn in `501094a` | (c) measured slower on a live mode switch and removed ([final slot](#final-slot-on-the-headset-2026-09-27)); (a, b) not triggered on the headset yet |
| open | X18 (autostart during OS dialogs) | - | - |

### Final slot on the headset (2026-09-27)

OLD = the canonical build, APK md5 `7b8baadb` (`e889479`; pulled from the Quest and its md5 checked). NEW = APK md5 `b8b6dcc3`
(`d8b6498`: every fix above plus the uplink change of the 2c6ae8 session). Real link, air unit on REC (480p167 / 2000 kbit/s /
FEC 4/8 / MCS2 / 12 dBm), Guardian paused. Data: [build A/B](../data/2026-09-27-final-build-ab.csv) ([steps](../data/2026-09-27-final-build-ab-steps.txt)),
[latch and input sync](../data/2026-09-27-final-latch-input.txt), [mode switches](../data/2026-09-27-final-switch-gap.txt).
APK files on PC-VLAD (gitignored; a rebuild from git gives another md5): `7b8baadb` = `scripts/quest/out/apks/w5b-e889479.apk`, `b2249f15` = `scripts/quest/out/apks/ppxr-b2249f15-501094a.apk`; `b8b6dcc3` was not kept (rebuild `d8b6498` if needed).

1. **No latency regression.** One in-trace A/B, OLD NEW OLD NEW NEW OLD × 45 s ([ab_segments.py](../../../scripts/quest-latch/ab_segments.py), drift fitted on OLD). NEW is +0.20 ms at frame complete and +0.21 ms decoded. The decoder's share is equal (decoded − last 1.48 vs 1.49 ms), fps 166.5 on both, loss ≈ 0. The shift is in arrival and lies inside the spread of the steps (OLD 1.60–1.73, NEW 1.74–2.02 ms) [PROVEN: data above].
2. **The input sync costs nothing on the frame path.** `ppxr_input_sync` p50 68 µs, p95 79 µs, max 0.33 ms (2 traces × ~1045 frames). It runs after `xrEndFrame`. Phase-to-latch is unchanged: ready → latch mean 3.05–3.19 ms, about 35 % of frames miss a latch, on both builds (2 OLD, 4 NEW traces) [PROVEN: data above].
3. **Home is taken once per arming** (`11cb1a7`). With `mavlink_fake.py 40 --arm-after 5`: `disarmed … HOME …`, then `ARMED … HOME 48m` and `HOME 155m` as the fake position drifts north [PROVEN: [screenshots](../img/w5-panel-home.jpg)].
4. **Live mode switch 480p167 ↔ 1080p90 without an app restart** (N = 4 per build; the OpenIPC session restarted waybeam on a timed loop, isperr 0 on all 8). The picture is gone ~3.0–3.2 s per switch on both builds, almost all of it the air unit's restart (first new RTP packet ~3.0–3.1 s after the last frame). Decoder part (first new RTP packet → first decoded frame): **OLD 55 / 52 / 45 / 48 ms (mean 50), NEW 131 / 5 / 99 / 101 ms (mean 84)**. Decode after every switch was healthy on both (1.47 ms at 480p, 2.33 ms at 1080p), so the 78 ms stall that (c) was meant to cure ([troubleshooting](../troubleshooting.md)) did not occur on either build [PROVEN: data above]. (c), rebuilding the decoder on every SPS change, is therefore slower and brings no measured benefit. It was removed in `501094a` (APK md5 `b2249f15`; host gtests 55/55); (a) and (b) stay. The build without (c) gets its own check (4 switches + a short latency A/B) in a later slot. Its extra ~35 ms is [INFERRED: from the per-switch numbers] the release and re-creation of the MediaCodec pair, compared with the decoder adapting in place.
5. **Last slot: the build without (c)** (APK md5 `b2249f15`, `501094a`), against `b8b6dcc3`. No mode switches this time: they write `/etc/waybeam.json`, and the air unit's `/overlay` was nearly full.
   - **Latency:** 4 steps, `b8b6dcc3` `b2249f15` `b2249f15` `b8b6dcc3` × 45 s. The build without (c) is +0.09 ms at frame complete and +0.08 ms decoded, inside the spread of the steps (1.41–1.70 vs 1.58–1.72 ms); fps 166.3 on both [PROVEN: [data](../data/2026-09-27-last-build-ab.csv), [steps](../data/2026-09-27-last-build-ab-steps.txt)].
   - **Recovery after one same-mode waybeam restart** (config untouched): picture gone 3564 ms, of which 3535 ms before the first new packet and **29 ms decoder**. Decode 1.46 ms afterwards [PROVEN: [data](../data/2026-09-27-last-restart-gap.txt)].
   - **On a resolution switch the build without (c) behaves like OLD**, which has the same decoder code on this path: 45–55 ms decoder part (item 4) [INFERRED: `501094a` restores the pre-`c0f41f2` SPS handling; not re-measured, no switches allowed].
   - `b2249f15` stays installed. The Quest was restored afterwards (Guardian on, `automation_disable`).
6. **Note (2026-09-27, later): the prefs writes in items 1 and 5 did not land, and the results still hold.**
   - From 18:16 to 22:34, `quest_adb.write_prefs` did not replace `general.xml` on the Quest. The atomic write of `ff19253` chained `&& mv` inside one `adb exec-in`, and only the `cat` ran in run-as (found by the 2c6ae8 session, fixed in `3cb6ea1`; see [troubleshooting](../troubleshooting.md)).
   - Both build A/Bs above (`pref_ab.sh`, 18:36 and ~19:05) wrote prefs in that window. Every step asked for the prefs that were already on the headset: `gs.key`, `od_enabled` false, `adaptive_link_enabled` true [PROVEN: `run-as … cat shared_prefs/general.xml` before each run]. So the read-back matched and the prefs in effect were the intended ones.
   - Only the APK changed between steps, and `adb install` was not affected. The results stand [INFERRED: from the two facts above].

### Hands-on checks with the user (2026-09-28)

03:32–03:46. Build `c31ddd0f` (`672aaa6`), headset on the table, the user on the controller and the RTL adapter; the
coordinator relayed each step. The monitor was [physical_step.sh](../../../scripts/quest/physical_step.sh): logcat of the
app tags plus `ActivityTaskManager` and `UsbHostManager`, and screenshots. Data: [filtered log](../data/2026-09-28-physical-x15.txt).

1. **X01, A and B** [PROVEN: [screenshots](../img/w5-buttons.jpg)]:
   - one A: detailed (7 lines) → compact (link / telemetry / video);
   - one B: the panel hides, the video keeps running;
   - a second B: the panel comes back, still compact.

   X and Y are bound to the same actions in `XrInput.cpp` and were not pressed.
2. **Preset menu** [PROVEN: [screenshot](../img/w5-menu-open.jpg), 03:36:47]: a thumbstick flick opens the menu. It
   shows `PRESETS  no list from the air unit yet`, which is right while the air runs no `vmoded`.
   - After the flick → flick → B sequence the menu was closed and the panel still visible. So B was taken by the menu
     and did not hide the panel [INFERRED: the moment of closing was not caught, and the 6 s idle close cannot be ruled
     out for it].
   - The strict B-closes-the-menu proof waits for the test with the real `vmoded`.
3. **RTL unplug 10 s + replug, N = 2, plus one unplanned replug** (the user put the Quest on its charger at 03:41:28,
   which moved the cable) [PROVEN: log + [replug 1](../img/x15-replug-1.jpg) / [replug 2](../img/x15-replug-2.jpg)]:

   | | Replug 1 (03:38:01) | Replug 2 (03:39:54) | Unplanned (03:41:31) |
   |---|---|---|---|
   | detach | `NO ADAPTER - plug in the RTL8812AU` (red), link thread stopped cleanly | same | - |
   | attach: XR's link | restarted at once (`c27f8aa`) | restarted at once | restarted at once |
   | X15: `START VideoActivity` from `USB_DEVICE_ATTACHED` | yes, ×2 | yes, ×2 | yes, ×2 |
   | back in XR? | yes: VideoActivity was new, and its XR autostart relaunched XR 0.5 s later | **no**: VideoActivity already existed (onNewIntent, no autostart). Horizon's placeholder stayed in front with the 2D panel visible | yes (VideoActivity was new again) |
   | second link on the same adapter | yes: 2× `did not stop within 3000ms`, `adapter still in use after 10000 ms` | yes: `adapter still in use after 10000 ms` | yes: 2× `did not stop`, `still in use` |
   | picture back | 03:38:12, ~11 s after the attach | the link ran, but the pilot was in 2D | yes |

   - **X15 is real and worse than a flicker.** On a replug the system starts the 2D `VideoActivity` (it owns the
     `USB_DEVICE_ATTACHED` filter).
   - The first time, its autostart bounces back to XR. After that the instance is kept (singleInstance), so a later
     replug leaves the pilot in 2D. That matches the audit's prediction for X15 and X03.
   - Each time, the 2D activity also starts its own link on the adapter XR is already using. Most of the ~11 s to
     picture is probably that fight plus the XR session cycling (`video detached`/`attached`) [INFERRED from the log order].
   - **Self-healing works:** XR's link restarted on every attach with no dialog [PROVEN].
4. **Restore:** force-stop, then a clean XR start (03:45:50). Result: one link start, no `still in use`, 167 fps with 0
   lost, no VideoActivity instance, Guardian restored.

**Next:** the X15 trampoline (Fix 4, optional part), now justified. `USB_DEVICE_ATTACHED` moves to a no-display activity.
It finishes at once when XR is in front, since XR's receiver already restarts the link; otherwise it opens
`VideoActivity`. That also removes the second link start.

## 0. Findings at a glance (ranked; details below)

Score = impact (1-5) × likelihood (1-5) / effort (1-5). Every score is an estimate, so read the scores as [INFERRED].

| # | ID | Problem the user meets | Score |
|---|----|------------------------|-------|
| 1 | X08+X09 | The panel shows **stale** numbers: link counters freeze when packets stop, and after a sleep/wake or reattach the fps and resolution are still the old values | 15 |
| 2 | X10 | When the video stops mid-flight, the **last frame stays frozen**, full size and head-locked. There is no "NO SIGNAL"; only a small "0 fps" (after up to 2 s) and "rssi 0" at the edge of the panel | 12.5 |
| 3 | X06 | **Wrong key is invisible**: the link looks healthy ("rssi" high, 0 lost), the video says "waiting for stream", and decrypt errors are not shown | 12 |
| 4 | X05 | **One status slot**: messages overwrite each other (the VPN hint hides adapter errors, the UDP fallback hides "could not be started"), and success is never reported ("Starting wfb-ng…" stays forever) | 12 |
| 5 | X11 | The panel is **hard to read**: about 39 columns, so most lines and every long error are clipped. It sits about 25-29° below centre, head-locked, so the user cannot look at it. It cannot be toggled, and it holds debug data rather than flight data | 10 |
| 6 | X12 | **No flight telemetry in XR** (battery, arm state, altitude, GPS). Also, MAVLink is dead for the rest of the process after the 2D activity's first `onStop` (entering XR is one) | 8.3 |
| 7 | X21 | **Leak on each XR launch**: the `WfbNgLink` Timer thread, the native link and the whole destroyed activity (through the stats callback) are never released | 8 |
| 8 | X17 | A **dead wfb link thread** (devourer runtime error, lock timeout) is neither noticed nor restarted, and nothing is reported. Non-`runtime_error` exceptions crash the app | 6 |
| 9 | X24 | A short or missing `gs.key` makes the native link constructor throw, so the app **crashes when XR starts** (inferred). The key is also written to logcat in hex | 5 |
| 10 | X15 | **Plugging the adapter in while in XR** brings the 2D activity to the front, which pulls the user out of XR. Autostart does not fire because the instance already exists | 4 |
| 11 | X01 | **No input at all in XR**: no setting (channel, key, levers, panel) can be reached without leaving XR | 4 |
| 12 | X14 | USB permission in XR: the grant result is ignored, and a denial is asked again on every `onResume` (possible prompt loop) | 3 |
| 13 | X13 | An XR start failure is shown as a **Toast**, which cannot be seen in immersive mode, and then the activity finishes | 3 |
| 14 | X23 | Decoder failures are silent: a configure failure retries on every NALU, a codec in error state freezes until the next session cycle, and a mid-stream SPS/codec change is not handled | 2.7 |
| 15 | X04 | XR levers are cached in `onCreate`. When the existing XR instance is brought back, lever changes made in 2D are silently not applied | 2.7 |
| 16 | X18 | Autostart on first run: the 2D consent/permission dialogs and a full chip bring-up and stop run right before XR launches (blocked launch; adapter lock wait of up to 10 s) | 2 |
| 17 | X20 | The Meta menu or a Guardian/tracking dialog mid-flight may pause the activity, which stops the link while the video layer stays up [SPECULATION] | ? |
| 18 | X19 | Sleep/wake recovers (proven) but gives no "reconnecting" feedback; the time until video returns is unmeasured | 2 |
| 19 | X25-X27 | Minor: the XR loop spins if `xrWaitFrame` keeps failing, VPN failure is not visible in XR, and an unknown bandwidth pref causes an NPE | ≤2 |

Section 9 gives the five proposed fixes.

---

## 1. Settings in XR, leaving XR, getting back

**X01: nothing can be set from inside XR.** [PROVEN]
- The OpenXR runtime creates no action set and syncs no input. `XrRuntime.cpp:173-274` (setup) and `:323-335`
  (loop) only poll session events and submit two layers. A grep for `ActionSet`/`xrSyncActions` in `app/xr/src`
  finds nothing but the prebuilt loader binaries.
- `XrVideoActivity` overrides no key or motion handler (`XrVideoActivity.java:28-259`).
- So channel, bandwidth, key, link options, levers and the panel cannot be reached in XR. Every setting lives in
  the 2D `VideoActivity` popup menu (`VideoActivity.java:723-842`).

**X02: leaving XR.** [PROVEN] / [SPECULATION]
- The only way out is the Meta button → Quit. The runtime then sends `EXITING`/`LOSS_PENDING`
  (`XrRuntime.cpp:407-411`), and the activity finishes (`XrVideoActivity.java:168-170`).
- The comments say the user then lands in the 2D activity, "to the settings" (`VideoActivity.java:364-365`,
  `LatencyExperiments.java:107`). XR runs in its own task (`AndroidManifest.xml:83-96`,
  `taskAffinity=com.openipc.pixelpilot.xr`), so whether Horizon brings the 2D task forward or goes to Home is not
  set by the code [SPECULATION].
- *Check on the Quest:* quit XR from the Meta menu, then run `dumpsys activity activities | grep -E "Resumed|topResumed"`.

**X03: getting back into XR.** [PROVEN] + [INFERRED]
- The only way back is Menu → Video → **Launch XR (Quest)** (`VideoActivity.java:789-793`), which is two submenu
  levels deep with the controller pointer.
- Autostart fires only when the 2D activity is created fresh (`savedInstanceState == null`, `VideoActivity.java:366`).
- Once the 2D activity exists (it is `singleInstance`, `AndroidManifest.xml:56`, and has no `onNewIntent`), opening
  the app from the Library again brings the existing 2D instance forward with no `onCreate`. The user stays in 2D
  even though "Start in XR" is on [INFERRED: from `:366` and no `onNewIntent` in `VideoActivity.java`].

**X04: lever changes made in 2D can be silently ignored.** [INFERRED]
- `XrVideoActivity` reads `LatencyExperiments` once, in `onCreate` (`XrVideoActivity.java:76`). The refresh rate,
  FOV, shape, flip, timestamps and perf level all come from that snapshot (`:79-80`, `:194-195`).
- The 2D menu says "XR levers are read when the XR activity starts, so they need no restart" (`VideoActivity.java:816`).
- XR is `singleInstance` too (`AndroidManifest.xml:86`). If the XR instance is still alive in its own task when
  **Launch XR** is pressed, Android brings it forward through `onNewIntent`, which is not overridden, and does not
  create it again. The new prefs are then not applied, although the panel's `exp:` line does show the old values.
- Whether the instance survives a switch to the 2D panel depends on Horizon (see X02) [SPECULATION].
- Decoder levers are not affected: `addRestartingToggle` restarts the whole process (`VideoActivity.java:868-880`,
  `resetApp` `:247-260`).

## 2. Errors as seen in XR

There is one text overlay: the panel under the video. Its last line is a **single** status string, `linkStatus`
(`XrVideoActivity.java:52,224-231,252`). Nothing else in XR shows state. The table lists what the panel shows in
each case.

| Situation | What the panel shows | Evidence |
|---|---|---|
| **No adapter plugged in** | `No compatible wifi adapter found.`, which is **replaced at once** by `No adapter - push RTP to udp://<ip>:5600` when the Quest is on Wi-Fi. The link line keeps its last counters; "rssi" drops to 0 within about 1 s; the video line stays at its last value (see X09) | [PROVEN: `WfbLinkManager.java:217-230`; `XrVideoActivity.java:223-231`] |
| **Adapter found but start failed** | `Wifi adapter found but could not be started - see the log.`, which is **overwritten** by the UDP fallback line, as above. The user never sees it when Wi-Fi is on | [PROVEN: same lines] |
| **USB permission not granted** | `No permission for wifi adapter(s) /dev/bus/usb/…`, clipped to about 39 characters (X11). If the VPN is also not granted, the VPN line (next row) replaces it, because `bind` runs after `refreshAdapters` | [PROVEN: `WfbLinkManager.java:173-174`; order `XrVideoActivity.java:113-117`] |
| **VPN permission not granted** | `VPN not granted - start PixelPilot in 2D once to allow it` (57 characters, so clipped). Video is not affected: it arrives on UDP 5600 from the aggregator, not through the tunnel | [PROVEN: `XrVideoActivity.java:115-117`; `WfbngLink.cpp:84`] |
| **VPN granted but the tunnel fails** | Nothing. The binding has no callback and the service only logs the failure | [PROVEN: `WfbServiceControl.java:29-33`; `WfbNgVpnService.java:106-119`] |
| **Wrong key** (air and ground keys differ) | "rssi" looks healthy, and `lost 0 fec 0 bad 0`. The video line says `waiting for stream` (or stale values, X09). **Decrypt errors are not shown.** The RSSI is recorded for every frame with the right channel id **before** decryption, and wfb counts session-decrypt failures in `count_p_dec_err`, which the panel never prints | [PROVEN: `WfbngLink.cpp:206-208` (RSSI before decrypt); `rx.cpp:611-619` (`count_p_dec_err`); panel prints only rssi/lost/fec/bad, `XrVideoActivity.java:250-251`] |
| **Wrong channel / wrong link id / air unit off** (no wfb packets, quality -1024) | `rssi 0`. `lost/fec/bad` **frozen** at their last values (X08). The status line still says `Starting wfb-ng channel N with [VID:PID]` | [PROVEN: quality → 0..100 `WfbngLink.cpp:452-453`; empty RSSI window gives -1024 `SignalQualityCalculator.cpp:82-90`; counter reset only on a video packet, `WfbngLink.cpp:220-223`] |
| **Decoder cannot be configured** | Nothing new. `dec:` keeps its previous text or stays empty, because `mAppliedSummary` is only set on success | [PROVEN: `VideoDecoder.cpp:160-163,222`] |
| **Decoder in an error state** | fps drops to 0 **only while the output thread still runs**. If `dequeueOutputBuffer` returns an error, the thread exits and the info freezes (X23) | [PROVEN: `VideoDecoder.cpp:361-366,368-388`] |
| **No video at all** | `video: waiting for stream`, but **only if no DecodingInfo has ever arrived in this activity instance**. The field is never reset (X09) | [PROVEN: `XrVideoActivity.java:50,214-216,242`] |

**X05: one status slot, and "success" is never reported.** [PROVEN]
- `linkStatus` is one volatile string that every message overwrites (`XrVideoActivity.java:224-231`).
- Order in `onResume`: `refreshAdapters()` / `startAdapters()` post adapter messages (`:113-114`), then the VPN
  message overwrites them (`:115-117`).
- `refreshAdapters()` posts the real error and then the UDP-fallback hint (`WfbLinkManager.java:221-229`).
- On success, the last message is `Starting wfb-ng channel …` (`WfbLinkManager.java:260-262`). It is never replaced
  by "link up", so a stopped link and a running link show the same text.

**X06: wrong key.** See the table [PROVEN chain]. This is the most common setup mistake with a new air unit, and in
XR it cannot be diagnosed at all. The same applies to key changes on the air side mid-session.

**X07: "rssi" is not RSSI.** [PROVEN] `avg_rssi` is `quality` (-1024..1024) mapped to 0..100 (`WfbngLink.cpp:452-453`).
`quality` is itself the RSSI average over the last 1 s, mapped from 0..80 (`SignalQualityCalculator.cpp:88-100`).
The label and the absence of units mislead anyone who knows dBm.

## 3. The stats panel (the only "OSD" in XR)

**What it shows** [PROVEN: `XrVideoActivity.java:233-254`], 8 lines redrawn every 250 ms (`:31,55-70`):
1. XR refresh rate, requested rate, compositor GPU ms, dropped frames
2. resolution, fps, Mbit/s (or `video: waiting for stream`)
3. decode / parse / wait-for-input ms
4. `dec:` codec name and accepted levers
5. `phase:` compositor-phase meter
6. `exp:` lever summary
7. `link: rssi lost fec bad`
8. `linkStatus`

**Where it is drawn** [PROVEN + INFERRED]
- It is its own compositor surface (512 × 256, `LayerLayout.java:8-9`), drawn with a hardware canvas
  (`XrStatsRenderer.java:24-46`), as a head-locked quad **below** the video (`XrLayers.cpp:56-64`,
  `LayerLayout.java:50-52`).
- With the default FOV of 60° (`LatencyExperiments.java:41`) and the 2 m distance, the video is 2.31 × 1.30 m.
  The panel is 0.81 × 0.40 m, centred 0.92 m below the view axis: about **24.6° below centre, bottom edge at
  about 29°** [INFERRED: `LayerLayout.compute`, `:42-54`].
- Because it is head-locked (VIEW space, `XrRuntime.cpp:251`), tilting the head does not bring it closer. The user
  has to look down with the eyes into the edge of the Quest 2 lens, where the image is blurry.

**X11: readability** [INFERRED]
- The text is 21 px monospace (`XrStatsRenderer.java:12-13`). The Android monospace font advances about 0.6 em per
  character, so one line holds about (512 - 10) / 12.6 ≈ **39 characters**.
- Typical lines are longer: line 1 (`XR 120.0 Hz (req 120)  comp GPU 1.9 ms  drop 0.0`) is about 48 characters, the
  `exp:` line about 43, and every error message 51-58. They are **clipped on the right**; `drawText` does not wrap
  (`XrStatsRenderer.java:36`).
- *Check:* take a headset screenshot of the panel with the adapter unplugged.

**Toggle / priority / content** [PROVEN]
- The panel is always submitted (`mCount = 2`, `XrLayers.cpp:63-64`). It has no pref and no input to hide or move it.
- Line order puts developer data first (refresh, compositor, levers, phase) and link state last.
- Nothing on it is flight data (X12).

**"No signal" state.** None, as a distinct state. The only hints are `rssi 0`, `0 fps` (after the next 2 s window)
and a status line that may not have changed (X05, X10).

## 4. Autostart and hot-plug

**X18: autostart on first run.** [INFERRED: from `VideoActivity.java:356-368,1627-1651`]
- `VideoActivity.onCreate` binds the VPN with consent (`startVpnService` → `bind(this, true)`, `:363,1391`). On the
  first run that starts the system consent dialog.
- It then calls `launchXr()` straight away (`:366-368`).
- The 2D `onResume` also runs `refreshAdapters()`, which asks for USB permission (another system dialog), and
  `startAdapters()`, which brings the RTL chip up, only to stop it again in `onPause` (`:1600-1614`).
- Consequences:
  - (a) XR can be launched while an OS dialog is pending. [troubleshooting.md](../troubleshooting.md) records
    "Launch is blocked because: a Reprojected OS dialog is currently showing", and a blocked start ends in the
    invisible Toast of X13.
  - (b) XR's own `nativeRun` waits up to 10 s for the adapter lock that the 2D link still holds
    (`WfbngLink.cpp:128-144`), which delays the first picture.
- These are not reproduced on the Quest [SPECULATION for (a); INFERRED for (b)]. Fixing them means editing
  `VideoActivity`, which conflicts with session 2c6ae8.

**X15: plugging the adapter in while in XR.** [PROVEN: manifest + receiver] + [INFERRED: outcome]
- Only `.VideoActivity` declares `USB_DEVICE_ATTACHED` (`AndroidManifest.xml:66-72`).
- `WfbLinkManager.onReceive` does **nothing** on `ATTACHED`; its comment says the 2D activity handles it
  (`WfbLinkManager.java:109-114`).
- So a replug while flying in XR resolves to the 2D `VideoActivity`, possibly after Horizon's USB "open with"
  dialog (troubleshooting "may open the wrong app"). It comes forward, `onResume` takes the adapter, and XR is paused.
- Autostart does not fire again because the instance already exists (X03). The pilot ends up in 2D.
- A loose USB-C connector during a flight is a realistic trigger.

**X16: unplugging while in XR.** [PROVEN]
- `DETACHED` → `refreshAdapters()` → `stopAdapter()` → `WfbNgLink.stop()`, which joins the RX thread for up to
  **3 s on the UI thread** inside `onReceive` (`WfbLinkManager.java:103-108,191-200`; `WfbNgLink.java:153,162,199-212`).
- The stats tick stalls while that happens, but it stays under the ANR limit.
- The device survived an unplug on 2026-09-27 ([troubleshooting.md](../troubleshooting.md)).

**X14: USB permission from XR.** [PROVEN] + [INFERRED]
- `refreshAdapters()` asks for permission on every `onResume` for each adapter without permission, and then returns
  early (`WfbLinkManager.java:172-189`).
- The `ACTION_USB_PERMISSION` result is only logged (`:115-117`). The adapter therefore starts only on the **next**
  `onResume`; this works today only because the system dialog pauses and resumes the activity [INFERRED].
- The receiver is unregistered while the activity is paused (`XrVideoActivity.java:126`), so the result broadcast
  is lost anyway.
- A **denial** is followed by a new request on the next `onResume`, which can loop while the user keeps saying no
  [INFERRED].

**2D ↔ XR adapter handoff.** [PROVEN]
- The two activities own separate `WfbNgLink` instances but share the static `activeWifiAdapters`
  (`WfbLinkManager.java:24`).
- The native per-adapter lock waits up to 10 s (`WfbngLink.cpp:128-144`) so that XR can claim the RTL after the 2D
  link has stopped. This is covered by the 2026-09-27 lock fix.
- If a join times out, the thread and its connection are kept (`WfbNgLink.java:163-175`), and `isRunning()` stays
  true (`:65-67`). The next `startAdapters()` then returns early (`WfbLinkManager.java:248-251`), so the link does
  not come back until a replug (see X17).

## 5. Sleep/wake, lifecycle, leaks, recovery

**X19: headset off / on.** [PROVEN: code + troubleshooting]
- `onPause` stops the stats tick, the USB receiver, the wfb link and the VPN binding
  (`XrVideoActivity.java:121-129`).
- The session goes SYNCHRONIZED/STOPPING, which fires `INACTIVE` → `detachVideo()`, synchronously on the XR thread
  (`XrRuntime.cpp:401-406,424-430`; `XrVideoActivity.java:159-167`).
- The detach stops the UDP/UDS receivers and the codec, and **resets the keyframe finder** (`VideoDecoder.cpp:40-53`).
- On wake:
  - `onResume` restarts the adapters (a full chip bring-up) and rebinds the tunnel (`onRebind`).
  - READY → `xrBeginSession` (`XrRuntime.cpp:382-396`); VISIBLE/FOCUSED → `attachVideo()`.
  - The decoder then waits for the next SPS/PPS/IDR.
- Verified on the Quest: 2 sleep/wake cycles with the same pid and video back
  ([troubleshooting.md](../troubleshooting.md), stop-order and stopAudio sections).
- Not covered: how long it takes until video returns (chip init + lock + GOP), and the feedback meanwhile, which is
  none. The panel shows pre-sleep values (X09).

**X20: a short Meta-menu press or a Guardian/tracking dialog during a flight.** [SPECULATION]
- `setVideoAllowed(true)` holds for VISIBLE as well as FOCUSED (`XrRuntime.cpp:397-400`), so the video layer stays.
- But if Horizon calls `Activity.onPause` when the universal menu or a system dialog takes focus, `onPause` stops
  the **wfb link** (`XrVideoActivity.java:127`). The video then freezes until the menu closes, followed by a
  multi-second restart.
- *Check:* during a live stream, open and close the Meta menu N ≥ 2 times with
  `logcat -s pixelpilot-xr pixelpilot PixelPilotXr`, and look for `onPause` / `wfb-ng thread … done`.
- Outdoors or in the dark, "tracking lost" dialogs are the same case. Flying with the Guardian on is the default for
  a normal user; the repo's hygiene rule pauses it only during tests.

**X21: per-launch leaks.** [PROVEN code] / [INFERRED impact]
- Each `XrVideoActivity.onCreate` creates a new `WfbNgLink` (`XrVideoActivity.java:100-101`). Its constructor starts
  a `java.util.Timer` that calls native code every 300 ms (`WfbNgLink.java:53-63`).
- **Nothing cancels that Timer or frees the native `WfbngLink`.** No `close`/`destroy` method exists, and a grep
  finds no `delete` of the native instance.
- The Timer keeps `WfbNgLink.this` alive, which keeps `statsChanged`, which is the destroyed `XrVideoActivity`
  (`WfbNgLink.java:214-224`). So every quit and relaunch of XR in the same process leaks one Timer thread, one
  native link (three aggregators with FEC buffers) and one activity (with its `XrBridge`, `VideoPlayer` and panel
  state).
- `VideoPlayer`'s native side is freed only in `finalize()` (`VideoPlayer.java:293-300`).
- The same applies to the 2D `VideoActivity`'s link, but it lives as long as the process.

**X22: UDP 8001 socket per link restart.** This is the known leak. The **uncommitted** working tree already
contains a fix: `FdGuard` closes the TX socket when `TxFrame::run` exits, and each TX thread gets a fresh `TxFrame`
(`git diff` on `TxFrame.cpp` and `WfbngLink.cpp:282-291`). Another session is working on it, so this audit does not
touch it. It needs the `/proc/net/udp` count from [troubleshooting.md](../troubleshooting.md) after N sleep/wake cycles.

**X17: the link dies and nothing notices.** [PROVEN code] / [INFERRED behaviour]
- `WfbngLink::run` returns -1 without telling Java in three cases: the adapter lock is still busy after 10 s
  (`WfbngLink.cpp:138-144`), `CreateRtlDevice` fails (`:174-179`), or a `std::runtime_error` is thrown during
  bring-up or RX (`:307-321`).
- The Java thread then just ends. `WfbNgLink.isRunning()` counts map entries rather than live threads
  (`WfbNgLink.java:65-67`), so `startAdapters()` refuses to restart (`WfbLinkManager.java:248-251`), and
  `refreshAdapters()` skips the device because it is still in `activeWifiAdapters` (`:204-207`).
- Result: frozen video, a status line that still says "Starting…", and no recovery until a pause/resume or a replug.
- Worse, the `catch` only takes `std::runtime_error` (`WfbngLink.cpp:307`), while devourer also throws
  `std::logic_error` (`devourer/src/jaguar1/HalModule.cpp:2161,2168`, `RadioManagementModule.cpp:181,251,3003`).
  `CreateRtlDevice` (`WfbngLink.cpp:174`) is **outside** the `try` (which starts at `:193`). Any exception there
  unwinds through JNI to `std::terminate`, which kills the process. This is a likely mechanism for the open
  hot-plug crashes in [HANDOFF.md](../HANDOFF.md) item 8 ("devourer EEPROM exception") [INFERRED].

**Recovery after the link drops and comes back.** When the air unit comes back without an adapter change, the RX
loop never stopped, so packets resume. The decoder is still configured with the old SPS and continues from the next
decodable frame. It recovers as long as the resolution and codec are unchanged [INFERRED:
`VideoDecoder.cpp:106-129`]. If the air unit restarts with another resolution or codec, it is not reconfigured
(TODO at `VideoDecoder.cpp:86`). The unexplained "stuck at ~78 ms" episode in troubleshooting.md is the observed
version of that.

## 6. What the user sees when video stops mid-flight

**X10** [PROVEN chain + one SPECULATION]
- Nothing is rendered by the app itself: the compositor samples the Android-surface swapchain that MediaCodec
  writes into (`XrRuntime.cpp:262,300-321`).
- When no new buffer is queued, the compositor keeps showing the last acquired buffer, so the **last decoded frame
  stays on the head-locked quad, full size and apparently live** [SPECULATION: BufferQueue keeps its latest buffer;
  check by powering the air unit off mid-stream and taking a headset screenshot].
- After a session detach and reattach, the same surface is reused, so the **pre-sleep frame** may be shown again
  until the first new frame arrives [SPECULATION].
- Panel hints only:
  - fps falls to 0 at the next 2 s recalculation. `TRY_AGAIN_LATER` falls through to it
    (`VideoDecoder.cpp:357-360,368-388`), but only while the output thread still runs.
  - "rssi" goes to 0 within about 1 s (`SignalQualityCalculator.cpp` 1 s window).
  - `lost/fec/bad` freeze (X08).
  - `linkStatus` does not change.
- There is **no timeout, no "NO SIGNAL", no dimming, and no timestamp of the last frame**. For a pilot a frozen
  image that looks live is the worst failure mode: it looks like a hover while the aircraft keeps moving.

**X08: link counters freeze.** [PROVEN] The native callback sets `should_clear_stats` every 300 ms
(`WfbngLink.cpp:475`), but the counters are cleared only inside the video-packet branch (`:220-223`). With no
packets, the last window's `count_p_*` values are re-sent every 300 ms indefinitely.

**X09: stale decoder numbers.** [PROVEN] `lastDecoding` is never cleared (`XrVideoActivity.java:50,214-216`), not in
`detachVideo()` (`:184-191`) and not in `onPause`. After wake or reattach, the panel shows the old resolution, fps and
bitrate until the new decoder's first 2 s window. `videoW/videoH` also keep their old values.

## 7. Other failure paths

- **X13: XR start failure is invisible.** [PROVEN code; INFERRED visibility]
  - `xr.start()` failure → `Toast` + `finish()` (`XrVideoActivity.java:81-88`). There is no 2D window to show a
    Toast on in immersive mode.
  - Plausible triggers: the 4 s setup timeout (`XrRuntime.cpp:48-53`) while an OS dialog is pending, or a missing
    runtime extension.
  - `xrBeginSession` failure is only logged, which leaves a black session (`XrRuntime.cpp:386-391`).
- **X23: decoder failure paths.** [PROVEN code]
  - After "Cannot configure decoder" (`VideoDecoder.cpp:160-163`), `configured` stays false. Every later NALU
    (keyframes still buffered) calls `configureStartDecoder` again (`:130-140`), which creates and fails a
    MediaCodec per NALU.
  - A codec that enters an error state ends the output thread (`:361-366`) while `configured` stays true, and input
    feeding returns silently (`:248-252,286-291`). The picture stays frozen until the session cycles.
  - An SPS or codec change mid-stream is not handled (TODO at `:86`).
- **X24: key file.** [PROVEN code; INFERRED crash]
  - `GsKeyStore.set` stores any byte count (`GsKeyStore.java:45-55`).
  - `WfbNgLink`'s constructor → `nativeInitialize` → `initAgg()` builds three `AggregatorUDPv4` (`WfbngLink.cpp:75-101,397-402`).
  - The wfb `Aggregator` constructor **throws** if the key file cannot be opened or holds fewer than 64 bytes
    (`wfb-ng/src/rx.cpp:279-292`). There is no `try` in `nativeInitialize`, so a bad imported key crashes XR in
    `onCreate` (`XrVideoActivity.java:100`), and the 2D activity as well.
  - Separately, the private key is logged in hex (`GsKeyStore.java:61`).
- **X25: the XR loop spins.** [INFERRED] If `xrWaitFrame` keeps failing, `renderFrame()` returns at once and
  `loop()` repeats without sleeping (`XrRuntime.cpp:323-334,436`). This is low likelihood.
- **X26: VPN.** [INFERRED] Owned by session 2c6ae8, so it is reported only:
  - `builder.establish()` may return `null` when the app's VPN is revoked or another always-on VPN holds it.
    `startTunnel` then goes on to `startVpnThreads(null, …)` → NPE on `getFileDescriptor()`
    (`WfbNgVpnService.java:107,121,198`). The NPE is on the main thread in `onBind`/`onRebind`, so it crashes the app.
  - `Binding.bind` sets `bound=false` when `bindService` returns false and never unbinds (`WfbServiceControl.java:47`).
    Android asks callers to unbind even then, so the registered connection leaks.
- **X27: bandwidth pref.** [PROVEN] A bandwidth pref other than 20 or 40 leaves `bandWidth` null
  (`WfbLinkManager.java:86-98`), so `startAdapter` throws an NPE (`:263`). The menu offers only 20 and 40, so this
  is low likelihood.
- **Threads not joined.** [PROVEN]
  - MAVLink's thread is detached and its stop is a counter that never resets (see X12).
  - `CompositorPhase` shuts its executor down without awaiting it (`CompositorPhase.java:58-64`), which is harmless.

## 8. X12: no flight telemetry in XR, and MAVLink breaks after entering XR once

[PROVEN]
- `XrVideoActivity` has no MAVLink or OSD code (grep). The 2D activity starts MAVLink only in `onCreate`
  (`setupMavlink`, `VideoActivity.java:356,1266-1269`) and stops it in `onStop` (`:1618`).
- Native side: `nativeStop` increments the global `mavlink_thread_signal` (`mavlink.cpp:387`), and **nothing ever
  resets it** (`:57`). The listen loop runs `while (!mavlink_thread_signal)` (`:95`), so every later `nativeStart`
  thread exits at once.
- Also, a failed `bind` returns without closing the socket (`:78-82`).
- Consequences:
  - (a) In XR the pilot has **no battery voltage or current, no arm state, no altitude, no GPS and no flight mode**.
  - (b) After the first time the 2D activity reaches `onStop` (entering XR, headset sleep), **the 2D OSD's telemetry
    is dead for the rest of the process** too [INFERRED].
- Also missing in XR: DVR recording, and audio (XR never calls `startAudio`).

---

## 9. The five proposed fixes

Two constraints shaped the choice:
- None of them touches `WfbServiceControl`, `WfbNgVpnService` or the VPN code in `VideoActivity` (session 2c6ae8),
  or `scripts/quest-latch/ab_segments.py` (session 22).
- **`WfbngLink.cpp` / `TxFrame.*` have uncommitted edits by another session** (the UDP 8001 fix), so all five
  avoid native link code until that work is committed.

Pure logic goes into `app/xr` (`com.openipc.xr`), so `./gradlew :app:xr:testDebugUnitTest` covers it. That module
already holds `LayerLayout`, `PhaseMeter` and their tests.

### Fix 1: a signal-state model and an alert you cannot miss (covers X10, X06, X08, X09, X05, X19, part of X23)

- **Files**
  - New: `app/xr/src/main/java/com/openipc/xr/SignalState.java`, a pure classifier with primitive inputs.
  - Changed: `XrVideoActivity.java` (`statsTick`, `statsLines`, `detachVideo`, `onLinkStatus`) and
    `XrStatsRenderer.java` (one coloured headline line).
  - Optional step 2: `LayerLayout.java` (an "alert" placement) and `XrLayers.cpp`/`XrRuntime.cpp`/`XrBridge.java`
    (a `setVideoVisible(boolean)` flag). These are in `app/xr`, which no other session is editing.
- **Approach**
  1. Drain `videoPlayer.drainFrameReadyTimes()` **once** per tick. It returns CLOCK_MONOTONIC ns, the same clock as
     `System.nanoTime()` on Android. Pass the array to `phase.tick()` and keep `lastFrameNs = max(array)`. Today the
     drain is consumed only by the phase meter (`XrVideoActivity.java:61-63`).
  2. Feed `SignalState.classify(nowNs, lastFrameNs, framePeriodNs, adapterState, statsAgeNs, qualityPct, pAll,
     decOk, decErr)`. It returns one of `NO_ADAPTER`, `NO_USB_PERMISSION`, `NO_PACKETS`, `WRONG_KEY`
     (`decErr > 0 && decOk == 0`), `WAITING_FOR_KEYFRAME` (packets, no frame since attach), `VIDEO_STALLED` (last
     frame older than max(250 ms, 6 frame periods)) or `OK`, plus a short message.
     - Add hysteresis: enter `STALLED` after 250 ms; return to `OK` only after 5 frames in a row. This keeps the
       alert from flickering at the edge of range.
     - Ignore counters that repeat identically once quality is 0. The native freeze (X08) is handled here without
       touching `WfbngLink.cpp`.
  3. Replace the single `linkStatus` with structured fields. `WfbLinkManager` already calls
     `onLinkStatus`/`onUdpFallbackAddress` separately, so XR can keep the adapter error **and** the fallback hint
     **and** the VPN hint.
  4. Render the state as line 1 of the panel, large and in red or amber. Add `dec_err` and a packet rate
     (`count_p_all`) to the link line, and rename `rssi` to `sig %`.
  5. In `detachVideo()`, set `lastDecoding = null` and the attach time (fixes X09 and gives "WAITING_FOR_KEYFRAME").
  6. *(step 2)* While the state is `STALLED`/`NO_PACKETS`, move the panel over the lower centre of the video
     (`LayerLayout.alert()`), or hide or dim the video layer through a small native flag. That way a frozen frame
     can never pass for live video.
- **Unit tests** (`app/xr/src/test/java/com/openipc/xr/SignalStateTest.java`, JVM)
  - Frames every 8 ms → `OK`.
  - Last frame 400 ms old while packets arrive → `VIDEO_STALLED`.
  - quality 0 → `NO_PACKETS`.
  - `decErr=30, decOk=0` → `WRONG_KEY`.
  - Attach without a frame yet → `WAITING_FOR_KEYFRAME`.
  - A single late frame does not trip the alert, and recovery needs 5 frames (hysteresis).
  - Adapter errors take priority over signal errors.
  - Extend `LayerLayoutTest`: the alert placement keeps the panel within ±10° of centre for FOV 40-90.
- **Device check** (repo rule: N ≥ 2, alternating): power the air unit off mid-stream, unplug the RTL, and swap to
  a wrong key. Take a headset screenshot of each.
- **Conflict risk: low.** The files are `XrVideoActivity`, `XrStatsRenderer` and `app/xr`. `VideoActivity` is not touched.

### Fix 2: a readable panel (covers X11, rest of X05)

- **Files:** `XrStatsRenderer.java`, `LayerLayout.java` (`STATS_IMAGE_W/H`, `GAP_FRACTION`, panel width),
  `XrVideoActivity.statsLines()`, and a new pure `app/xr/.../PanelText.java`.
- **Approach**
  - Double the texture to 1024 × 512 at the same angular size. That is 2× the pixels per degree; the stats swapchain
    is created from `LayerLayout` (`XrRuntime.cpp:263`), so no native change is needed.
  - Wrap or ellipsise each line at the measured column count (`PanelText.fit(lines, cols)`).
  - Reorder the lines: state, then link, then video, then flight data (Fix 3), then the debug lines. The debug lines
    are shown only when a pref is on; read it with a default, so no menu change is needed now.
  - Bring the panel up so that it overlaps the bottom 10-15 % of the video instead of hanging below it. This puts
    it within about 15-18° of centre instead of about 25-29°.
- **Unit tests:** `PanelTextTest` (wrapping, ellipsis, priority order, empty lines dropped). Extend `LayerLayoutTest`:
  the angle of the panel's centre stays below 18° for FOV 40-90, and the panel stays inside the vertical FOV.
- **Conflict risk: low** (`app/xr` and XR-only classes). A pref in `LatencyExperiments` is shared with the 2D menu,
  so add only the key and default, and no menu item yet.

### Fix 3: flight telemetry in XR, and a MAVLink listener that can restart (covers X12)

- **Files:** `app/mavlink/src/main/cpp/mavlink.cpp` (reset the stop flag on start, keep one listener, close the fd
  on every exit path, and join or at least wait for the old thread before re-binding 14550), `XrVideoActivity.java`
  (implement `MavlinkUpdate`; `MavlinkNative.nativeStart` in `onResume`, `nativeStop` in `onPause`,
  `nativeCallBack(this)` from `statsTick`), and a new pure `app/xr/.../TelemetryLine.java` (formats one or two lines:
  battery V/A/mAh, ARM/DISARM, flight mode, altitude, GPS sats and fix, distance home).
- **Approach:** the 2D activity's `onStop` runs after XR's `onResume`, so the native start/stop has to be
  reference-counted or idempotent, with the flag reset on start and cleared only by the last stop. Otherwise the 2D
  `onStop` kills XR's listener. As a side effect this also brings back 2D telemetry after a visit to XR (X12b).
- **Tests**
  - JVM: `TelemetryLineTest` (formatting, units, missing-data placeholders).
  - Native: a host gtest for the start/stop state machine if the listen loop is pulled out of the JNI glue into a
    small class. Otherwise check on the device with `ss -uapn | grep 14550` across 2D → XR → 2D → sleep → wake
    (exactly one socket each time) and telemetry lines updating.
- **Conflict risk: low-medium.** No other session is listed on `mavlink/`. `VideoActivity` keeps calling the same
  two native functions unchanged.

### Fix 4: link self-healing and USB events handled in XR (covers X17, X14, part of X15, X16)

- **Files:** `app/wfbngrtl8812/src/main/java/.../WfbNgLink.java` (Java only: `isRunning()` counts **live** threads,
  and a `pruneFinished()` releases the connections of finished threads) and `WfbLinkManager.java`:
  - `ATTACHED` → `refreshAdapters()`.
  - `ACTION_USB_PERMISSION` with `EXTRA_PERMISSION_GRANTED` → `refreshAdapters()` + `startAdapters()`.
  - A denial is remembered per device name until detach, so the user is not asked again on every resume.
  - A `checkHealth()` called from the XR stats tick restarts a dead link with backoff (1, 2, 4, then 8 s) and
    reports "link restarting (n)".

  Plus a new pure `app/xr/.../RestartPolicy.java`, or in the app module next to `OrderedShutdown`.
- **Optional part for X15**, only if the Quest confirms that attach pulls the user to 2D: move the
  `USB_DEVICE_ATTACHED` filter and its `usb_device_filter` meta-data from `.VideoActivity` to a tiny
  `Theme.NoDisplay` trampoline activity. If XR is in front, the trampoline just finishes (XR's receiver now handles
  the attach); otherwise it starts `VideoActivity`. This changes `AndroidManifest.xml` only, and the user's
  "always open with" choice is reset once.
- **Tests:** `RestartPolicyTest` (backoff sequence, reset after the link has been healthy for N s, no restart while
  paused or with no adapter attached). The permission-denial memory as a pure map test. The native crash paths
  (logic_error / `CreateRtlDevice` outside the `try`) need the `WfbngLink.cpp` change later, after the other
  session commits: widen the catch to `std::exception`, move `CreateRtlDevice` inside the `try`, and add a callback
  so Java learns about the exit.
- **Conflict risk: medium.** `WfbLinkManager` is also used by `VideoActivity`, though not by its VPN code. The 2D
  behaviour changes too (attach and permission are handled in-app), and that change is wanted.

### Fix 5: lifecycle hygiene for repeated XR entries (covers X21, X04, X13)

- **Files:** `WfbNgLink.java` (add `close()`: `timer.cancel()`, `statsChanged = null`; the native delete comes
  later, in `WfbngLink.cpp`, once the other session is done), `XrVideoActivity.java`, and `VideoPlayer.java` (add an
  explicit `release()` that calls `nativeFinalize` once and makes `finalize()` a no-op afterwards).
  `XrVideoActivity.java` gets:
  - In `onDestroy`: `wfbLinkManager.stopAdapters()` as a guard, `wfbLink.close()` and `videoPlayer.release()`.
  - `onNewIntent`: if `LatencyExperiments.load(this)` differs from the cached XR levers, call `recreate()`. This
    needs an `equals()` on a small XR-lever value object in `app/xr` (X04).
  - The Toast on start failure is replaced by starting `VideoActivity` with an extra error text for the 2D
    `tvMessage`. This makes the failure visible where the user lands. It touches only a read of an intent extra in
    `VideoActivity`, so it can be deferred if 2c6ae8 is mid-edit (X13).
- **Tests:** a JVM test for the lever value object's `equals` and "needs recreate" logic (`app/xr`). `WfbNgLink`
  loads a native library in its static initialiser, so it cannot be JVM-tested directly; move the timer into a
  small injectable `PeriodicCallback` and test that, or check on the device: count `Timer-*` threads
  (`ps -T -p $(pidof com.openipc.pixelpilot.xr)`) after 5 XR quit/relaunch cycles, before and after (N = 2 each).
- **Conflict risk: low.** It becomes medium only for the optional `VideoActivity` extra.

### Next in line (not in the top 5)
- **X01: in-XR controls.** An OpenXR action set in `XrRuntime`: controller A/X cycles the panel mode, B/Y returns to
  the 2D settings, and a hand pinch does the same. High value but more effort; do it after Fix 2, when the panel
  is worth cycling.
- **X24: key validation.** Check the 64-byte length in `GsKeyStore.set` (not in a conflict list; cheap), and stop
  logging the key. The native `try` in `nativeInitialize` waits until `WfbngLink.cpp` is free.
- **X18: first-run autostart ordering.** Defer `launchXr()` until the VPN and USB dialogs are done. This is in
  `VideoActivity`, so coordinate with 2c6ae8.
- **X23: decoder watchdog.** On `STALLED` with packets flowing for more than 2 s, reattach the decoder. This builds
  on Fix 1's state and the
  [decoder-reconfigure patch](../patches/decoder-reconfigure-on-sps-change.patch) noted in troubleshooting.

## 10. Open questions for the device (each one settles a [SPECULATION] above)

1. Where does Quit from the Meta menu land: the 2D task or Home? (X02)
2. Does the Meta universal menu, or a Guardian/tracking dialog, call `onPause` on `XrVideoActivity`? (X20)
3. Is the last frame kept on the quad when the stream stops, and is the pre-sleep frame shown after wake? (X10)
4. Does a USB attach while in XR bring up the 2D activity or a Horizon "open with" dialog? (X15)
5. Screenshot of the panel with long status lines, to confirm the about 39-column clipping (X11).
6. Time from wake to first frame (N ≥ 2), split into chip init, lock wait and keyframe wait (X19).

## Files referenced

- `app/src/main/java/com/openipc/pixelpilot/XrVideoActivity.java`, `XrStatsRenderer.java`, `WfbLinkManager.java`,
  `WfbServiceControl.java`, `WfbNgVpnService.java`, `GsKeyStore.java`, `LinkOptions.java`, `CompositorPhase.java`,
  `VideoActivity.java`
- `app/src/main/AndroidManifest.xml`
- `app/xr/src/main/cpp/XrRuntime.cpp`, `XrLayers.cpp`; `app/xr/src/main/java/com/openipc/xr/XrBridge.java`, `LayerLayout.java`
- `app/videonative/src/main/java/com/openipc/videonative/VideoPlayer.java`, `LatencyExperiments.java`;
  `app/videonative/src/main/cpp/VideoDecoder.cpp`, `VideoPlayer.cpp`
- `app/wfbngrtl8812/src/main/java/com/openipc/wfbngrtl8812/WfbNgLink.java`, `WfbNGStats.java`;
  `app/wfbngrtl8812/src/main/cpp/WfbngLink.cpp`, `SignalQualityCalculator.cpp`, `wfb-ng/src/rx.cpp`,
  `devourer/src/jaguar1/HalModule.cpp`, `RadioManagementModule.cpp`
- `app/mavlink/src/main/cpp/mavlink.cpp`; `app/mavlink/src/main/java/com/openipc/mavlink/MavlinkNative.java`, `MavlinkUpdate.java`
- Docs: [xr-quest.md](../../xr-quest.md), [troubleshooting.md](../troubleshooting.md), [HANDOFF.md](../HANDOFF.md)
