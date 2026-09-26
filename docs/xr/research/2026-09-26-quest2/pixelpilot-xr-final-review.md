# Final whole-branch review — `xr-native` (3d6ca17..e28bd0e)

- **Reviewer:** Claude (Fable 5.1), read-only pass, 2026-09-26
- **Scope:** 9 commits, 48 files (+5561/−155). Every non-doc file in the range was read in full at `e28bd0e`;
  the modified upstream files were read as diffs against `3d6ca17`. Spec, plan and the executor ledger
  (`progress.md`, 6 rulings) were read. Two spec texts were fetched to check claims
  (`XR_KHR_android_surface_swapchain`, `XR_FB_android_surface_swapchain_create`, Khronos OpenXR-Docs main).
- **Not exercised by anyone yet:** a headset. Everything below about runtime behaviour on Quest is
  code-level reasoning, tagged `[INFERRED]`; things read in the code are `[PROVEN: file:line]`.
- Done in one pass; no subagents were used.

## Executor rulings (progress.md) — weighed

| Ruling | Verdict |
|---|---|
| T2: marker assignment inserted after each validate block separately | Correct; `ParseRTP.cpp:139,269` [PROVEN]. |
| T4: `requestCode == 100` → `WfbServiceControl.VPN_REQUEST_CODE` | Correct SSoT move, same value. |
| T6: USB receiver registration moved into `WfbLinkManager.register()/unregister()` | Good: removes a duplicated API-33 branch; flags identical to upstream (`WfbLinkManager.java:53-68`). |
| T6: lint gate = no new errors in touched files (3 upstream errors) | Reasonable; I confirmed none of the three are in this branch's lines. |
| T6: dropped `screenOrientation=landscape` on `XrVideoActivity` | Correct — orientation is meaningless for an immersive activity; the spec (§2) still says `landscape`; the spec sync in Task 7 did not update that sentence (Minor 7). |
| T7: push after the whole-branch review | Correct. |

Unrecorded deviation found: spec §2 says `XrVideoActivity` gets "the same USB intent filter" as `VideoActivity`; the manifest gives it none (`app/src/main/AndroidManifest.xml:83-96`). I think that is the better choice (attaching the adapter should open the 2D app), but it is a deviation that should be written into the spec (Minor 7).

---

### Strengths

- **The per-frame critical path really has no app code on it.** `XrRuntime::renderFrame` only re-submits two layers (`XrRuntime.cpp:332-372`); the decoder renders into the compositor surface via `releaseOutputBuffer(render=true)` unchanged (`VideoDecoder.cpp:294`). Nothing in the XR loop can add latency to video; the OpenXR thread could stall for a whole second and video would still update. This is the right architecture for the goal. [PROVEN]
- **2D defaults are provably identical to upstream.** `DecoderLevers{}` → exactly upstream's `writeAndroidPerformanceParams` key set, pinned by `DecoderLevers_test.cpp:14-26`; `LatencyExperiments` keeps `"general"` / `"low_latency_decoder"` / default `true` (`LatencyExperiments.java:12-14,66`); `au_aggregation` and the three codec extras default `false`, so `interpretNALU` takes the upstream branch (`VideoDecoder.cpp:113-119`) which feeds the same bytes with the same CODEC_CONFIG rule as before. `registerReceivers`/`startVpnService`/`onPause` in `VideoActivity` are pure extractions with identical flags/intents. [PROVEN]
- **Extension handling against the spec is careful:** `xrInitializeLoaderKHR` via `xrGetInstanceProcAddr(XR_NULL_HANDLE)` (`XrRuntime.cpp:105-111`), required vs optional extension split with every optional pfn null-checked before use, `xrGetOpenGLESGraphicsRequirementsKHR` before `xrCreateSession`, EGL context created and made current on the same thread that creates the session, `format/sampleCount/faceCount/arraySize/mipCount` left zero for the surface swapchain as the KHR extension requires, `XrAndroidSurfaceSwapchainCreateInfoFB` chained only when the FB extension is present, `XrFrameEndInfo` with `layerCount=0` when `shouldRender` is false (`XrRuntime.cpp:359-370`), VIEW reference space for a head-locked layer. Struct `type` fields are initialised everywhere by aggregate init. [PROVEN]
- **JNI hygiene:** surface `jobject` from the runtime is promoted to a global ref and the local freed only if it was local (`XrRuntime.cpp:238-241`); the XR thread is attached once for its life and detached at exit; the listener uses `GetEnv` on that thread and clears pending exceptions (`xr_jni.cpp:38-44`); `XrBridge` is kept by proguard consumer rules. [PROVEN]
- **Threading model is simple and mostly correct:** `mMutex` guards exactly what the header says (`XrRuntime.h:88`); all session-state, `mRunning`, `mVideoAllowed` live on the XR thread; `mAuAggregationActive`/`mAssembler`/`mKeyFrameFinder` are only touched under `mMutexInputPipe` (`VideoDecoder.cpp:88,36`); `mLevers` under its own mutex, copied once at configure time so no nested locking. `videoAttached` is UI-thread only. [PROVEN]
- **`AccessUnitAssembler` is a clean, pure, host-tested unit** with the right invariants: config NALUs pass alone, AUD/first-slice/parameter-set start a new AU, oversize guard, first-NALU timestamp carried for the parse-latency stat (`AccessUnitAssembler.h`, 9 gtests). The lost-marker case is covered by `LostMarkerSplitsOnNextFirstSlice` and by the parser itself (a FU whose end fragment is lost is discarded at the next FU start, `ParseRTP.cpp:163-180`), so two pictures cannot be merged when the marker packet is lost. [PROVEN]
- **`LatencyExperiments` is a genuine single source of truth**: keys, defaults, validation and the summary string live in one class; both activities and the decoder consume it; `PrefSource` makes it JVM-testable without Android, and unknown/out-of-range values fall back (`validRefresh`, `clamp` with NaN guard, `LayerShape.parse`), all tested. [PROVEN]
- **Failure policy is honoured:** no silent fallback when XR is unavailable (`XrVideoActivity.java:67-75`), refresh "highest supported ≤ requested" with the actual value shown on the panel, `LayerLayout.compute(0,0,…)` returns a 16:9 fallback with no NaN (tested). [PROVEN]
- **Docs are honest** about what is and is not verified ("Not yet run on a headset"), and the smoke checklist maps to specific log lines that exist in the code.

---

### Issues

#### Critical (Must Fix)

None found. No data-loss, security or unconditional-crash defect; the two crash paths below are narrow races and are listed as Important.

#### Important (Should Fix)

1. **Native handle used after `XrBridge.stop()` → SIGSEGV window on exit.**
   - `xr_jni.cpp:57-89` (`nativeSetLayout`, `nativeInfo` dereference `handle(h)` unchecked), `XrBridge.java:61-69` (no `handle == 0` guard), `XrVideoActivity.java:114-119,172-179` (`xr` is never nulled after `stop()`).
   - Scenario: `onDestroy` → `detachVideo()` → `videoPlayer.stop()` cancels the 200 ms `Timer`, but a `TimerTask` already inside `nativeCallBack` still delivers `onVideoRatioChanged` → `ui.post(applyLayout)`; the post runs after `onDestroy`, `xr != null`, `handle == 0` → `reinterpret_cast<Handle*>(0)->runtime.setLayerConfig` → native crash. Same for `info()` if a `statsTick` is still queued. Window is small (ratio changes only on first frame / resolution change) but it is a hard crash on the exit path. [INFERRED from the code above]
   - Fix: in `XrBridge`, make every method a no-op (or return a default `Info`) when `handle == 0`; in `XrVideoActivity.onDestroy` set `xr = null` after `stop()` and keep the existing `xr != null` checks.

2. **INACTIVE detach depends on the UI thread; its 2 s budget is shorter than the 3 s wfb-ng join that the UI thread may be inside → `xrEndSession` while MediaCodec is still writing (review focus 3).**
   - `XrVideoActivity.java:129-143` (latch, `INACTIVE_TIMEOUT_MS = 2000`, on timeout only a warning and the XR thread continues into `xrEndSession`), `XrVideoActivity.java:104-111` (`onPause` calls `wfbLinkManager.stopAdapters()` on the UI thread), `WfbNgLink.java:153,162` (`joinBounded` waits `JOIN_TIMEOUT_MS = 3000` per adapter).
   - Scenario: user presses the Meta button. Android delivers `onPause` on the UI thread, which enters `stopAll()`; the RX thread is blocked in a USB bulk transfer, so `join` waits up to 3 s. Meanwhile the runtime delivers STOPPING; the XR thread posts `detachVideo` (queued *behind* `onPause`), waits 2 s, times out, calls `xrEndSession` — the decoder is still rendering into the surface, which the KHR extension text says the app "must ensure" is not happening before `xrEndSession`, and writing outside VISIBLE/FOCUSED is undefined. The spec's own stated rule (§3) is violated on exactly the path it was written for. [INFERRED; timings PROVEN at the lines cited]
   - Also: `onDestroy` while an INACTIVE latch is pending stalls the UI thread for the full 2 s (`xr.stop()` joins a thread that is waiting for a runnable behind `onDestroy`). Bounded, not a deadlock, but 2 s in `onDestroy`.
   - Fix (removes the timeout and the onDestroy stall together): detach on the XR thread directly. `VideoPlayer.stop()`/`setVideoSurface()` are `synchronized`/native and do not require the main looper (`verifyApplicationThread` only logs, `VideoPlayer.java:80-84`). Guard `videoAttached` with one lock held by `attachVideo`, `detachVideo` and `onDestroy`; `onSessionEvent(INACTIVE)` then calls `detachVideo()` synchronously and returns only when the codec is stopped. Keep `attachVideo` on the UI thread if you want, or do it on the XR thread under the same lock. If the latch design is kept instead, at minimum make the timeout ≥ `JOIN_TIMEOUT_MS + margin` and reorder `onPause` so that video is detached before adapters are stopped.

3. **Abrupt `stop()` ends a running session without the STOPPING transition (spec order violated, error swallowed).**
   - `XrRuntime.cpp:56-60` (`stop` sets `mExit`, joins), `:256` (`if (mRunning) endSession()`), `:325-330` (`xrEndSession` return value ignored), then `teardown` destroys swapchains/session.
   - Per the core spec `xrEndSession` is only valid in STOPPING and returns `XR_ERROR_SESSION_NOT_STOPPING` otherwise; the correct exit is `xrRequestExitSession` → pump events until STOPPING → `xrEndSession` → EXITING → destroy. Today the error is silently ignored and the session is destroyed while running (legal for `xrDestroySession`, but the runtime never sees an orderly end, and a future "already started" on relaunch would be the first symptom — the smoke checklist even asks for that check). Reached whenever the activity is destroyed while FOCUSED (config change not in `configChanges`, `finish()` from a future UI action, process trim). [INFERRED]
   - Fix: on `mExit`, if `mRunning`, call `xrRequestExitSession` and keep polling events (with a bounded wait, e.g. 500 ms) until STOPPING has been handled by `onStateChanged`, then fall through to teardown. Log non-success `XrResult`s from `xrBeginSession`/`xrEndSession`/`xrEndFrame`.

4. **AU aggregation can drop whole pictures that the per-NALU path would have decoded.**
   - `VideoDecoder.cpp:234-238` (`size > inputBufferSize` → `return`, the entire buffer is discarded), `AccessUnitAssembler.h:87` (`maxBytes = 1 MiB`, unrelated to the codec's input buffer), no `AMEDIAFORMAT_KEY_MAX_INPUT_SIZE` is set anywhere (`AndroidMediaFormatHelper.h`, grep confirmed).
   - Scenario: multi-slice IDR at 1080p on a high-bitrate air unit; the slices sum to more than the decoder's default input buffer. Per-NALU mode feeds each slice and decodes; AU mode assembles them and drops the *whole IDR* with "Nalu too big", so every frame until the next IDR is corrupt. A lever meant to reduce latency silently produces a worse stream, and a measurement would attribute the corruption to the link. [INFERRED; the drop path is PROVEN]
   - Fix: when `auAggregation` is on, set `AMEDIAFORMAT_KEY_MAX_INPUT_SIZE` to at least the assembler cap (or size the cap from the codec's reported input buffer after `start`), and on "too big" fall back to feeding the AU's NALUs individually instead of returning. Add a counter (`nAuTooBig`) to `DecodingInfo` so the panel shows it.

5. **Assembler closes an AU only on a VCL NALU carrying the marker; a marker on a trailing non-VCL NALU defers the flush to the next picture (+1 frame, silently).**
   - `AccessUnitAssembler.h:116-119` (`if (n.isVcl && n.endOfAu) flush`).
   - Scenario: an H.265 stream that ends each AU with a suffix SEI (type 40) or filler (38), or an H.264 stream with trailing SEI/filler — the marker packet is the SEI, `isVcl` is false, the AU stays pending until the next first slice → every frame is delivered one frame late. The lever then *adds* one frame of latency, and nothing in the stats reveals it. Whether majestic ever does this is unknown to me; the assembler should not depend on it. [INFERRED]
   - Fix: close on `n.endOfAu && mHasVcl` (config NALUs are already emitted alone before this point, and an AUD never carries the marker). Add two counters, "closed by marker" / "closed by next picture", to `DecodingInfo` and the `dec:` panel line so a measurement can see which path it ran on.

6. **`AMediaCodec_start` is unchecked, so the configure-retry (review focus 2) only covers half the rejection surface.**
   - `VideoDecoder.cpp:164` (`AMediaCodec_start(decoder.codec[idx])` result ignored, then `configured[idx] = true`).
   - Scenario: `c2.qti.hevc.decoder.low_latency` or a vendor key is accepted at `configure()` (Codec2 tends to ignore unknown params there) but the component fails at `start()`; the app now believes it is configured, `checkOutputLoop` exits on the first error, and no frame is ever decoded — with no retry and only a debug log. [INFERRED]
   - Fix: check `start()`; on failure delete the codec and retry with `onlyBase()` exactly as the configure path does. Same for `AMEDIACODEC_INFO`-level errors in `checkOutputLoop` — at least log at error level with the applied summary.

7. **Decoder summary can claim `LLC` when the low-latency component was not used → wrong label on the measurement.**
   - `VideoDecoder.cpp:175-183,207-208`: if `createCodecByName` returns null the code falls back to `createDecoderByType` but `mAppliedSummary` is built from `leversSummary(levers)`, which still lists `LLC`. The panel then reads e.g. `default video/hevc | LL LLC`. [PROVEN]
   - Fix: build the summary from what actually happened (clear `preferLowLatencyComponent` in a local copy when the by-name creation failed).

8. **`XrStatsRenderer.unlockCanvasAndPost` runs outside the try/catch → uncaught exception on the exit race.**
   - `XrStatsRenderer.java:27-41`: `lockHardwareCanvas` is guarded, `unlockCanvasAndPost` in `finally` is not.
   - Scenario: EXITING → XR thread tears down the swapchains immediately (`XrRuntime.cpp:442-443`) while the UI thread is between lock and unlock (4 Hz × ~1 ms, so rare but real) → `IllegalArgumentException` from `unlockCanvasAndPost` → crash instead of a clean exit. [INFERRED]
   - Fix: catch `RuntimeException` around the unlock as well; stop drawing once EXITING/INACTIVE has been seen.

#### Minor (Nice to Have)

1. `XrRuntime::start` "already started" path leaks the caller's activity global ref (`XrRuntime.cpp:35-38`, header promises ownership at `:49-51`). Delete it before returning.
2. SSoT leaks in the layout plumbing: `xr_jni.cpp:76` derives `statsImageH = statsImageW / 2` (duplicating `LayerLayout.STATS_IMAGE_H`), and `XrLayers.h:7-25` `LayerConfig` defaults re-state `LayerLayout`'s numbers (they matter: the video swapchain is created from them before Java calls `setLayout`, `XrRuntime.cpp:185-192`). Pass `STATS_IMAGE_H` through and create the swapchains from a layout the Java side supplies with `start()`.
3. Review focus 4, the half not covered: `LatencyExperiments.load` (`:83-91`) handles unknown *values* but not wrong *types*; a pref stored as the wrong type throws `ClassCastException` from `SharedPreferences` and kills the activity at startup. Catch it per key and fall back to the default (cheap, and it makes the "unknown pref → default" promise complete).
4. `xr_use_timestamps` is inert as implemented: the buffer timestamp MediaCodec attaches is the input-queue PTS (`VideoDecoder.cpp:242-245`, monotonic µs at feed time), always ≤ the compositor's display time, so "most recent buffer whose timestamp ≤ display time" is the same choice as mailbox. Say so in `docs/xr-quest.md` (or set PTS to a target display time when the lever is on, which is a separate experiment).
5. `xrSetAndroidApplicationThreadKHR` hints only the XR loop thread (`XrRuntime.cpp:398`), which does no latency-relevant work; the threads that matter are `UdpReceiver` and `LLDCheckOutput` in videonative. Not wrong, just not yet useful — see Recommendations.
6. `onCreate` blocks the UI thread for up to 10 s in `xr.start` (`XrRuntime.cpp:45`); a stalled runtime would ANR before the timeout fires. Consider 4–5 s, or start asynchronously and post the result.
7. Spec/doc sync: spec §2 still says `screenOrientation=landscape` and "same USB intent filter" for `XrVideoActivity`; neither is in the manifest (rulings/decisions were right, the spec was not updated). `docs/xr-quest.md:66` expects `120 Hz -> 120 Hz` but on a Quest 2 with 120 Hz not enabled under Settings → System → Display, `applyRefreshRate` silently picks 90 (`XrRuntime.cpp:385-388`); say so next to the checklist item.
8. `XrVideoActivity` never finalises `VideoPlayer`/`WfbNgLink` (relies on `finalize()`), so each XR launch leaks a native player and a wfb-ng instance until GC. Upstream's 2D activity has the same pattern; here the activity is designed to be entered and left repeatedly (smoke item "relaunch twice").
9. `XR_JNI(jobject, nativeVideoSurface)` reads `mVideoSurface` from the UI thread while the XR thread may be nulling it in `teardown` (`XrRuntime.h:55-56`, `XrRuntime.cpp:455`). Benign today (Java gets null and `setOutputSurface(null)` is a no-op), but it is an unsynchronised cross-thread read; make it atomic or read it under `mMutex`.
10. `feedDecoder`'s "Nalu too big" log is `MLOGD` (`VideoDecoder.cpp:236`); with AU mode it should be `MLOGE` and counted (ties to Important 4).
11. `SUPPORTED_REFRESH_HZ` includes 80 (`LatencyExperiments.java:27`) while the spec §4 table lists 72/90/120 — fine for Quest 2, just update the spec table.

---

### Review focus checklist (from the plan)

| # | Focus | Result |
|---|---|---|
| 1 | Lost RTP marker must not merge two pictures | **Holds.** Parser discards an incomplete NALU at the next FU start (`ParseRTP.cpp:163-180`); assembler flushes a pending AU on the next first slice / AUD / parameter set (`AccessUnitAssembler.h:91-100`), tested. Residual: a marker on a *non-VCL* trailing NALU delays the flush (Important 5) — the opposite failure (late, not merged). |
| 2 | Decoder rejecting new keys must still play | **Holds for `configure()`** (`VideoDecoder.cpp:152-156`), **not for `start()`** (Important 6). Summary may mislabel the component (Important 7). |
| 3 | STOPPING / SYNCHRONIZED must stop the decoder before `xrEndSession`, no deadlock with `onDestroy` | **No deadlock** (bounded by the latch timeout and the `destroying` flag). **Ordering can break** when the UI thread is inside the 3 s wfb-ng join (Important 2). Abrupt `stop()` also skips the STOPPING handshake (Important 3). |
| 4 | Unknown / out-of-range prefs → defaults | **Holds for values** (tested: refresh 144/0, FOV 500/1/NaN, shape "sphere"). Wrong-typed prefs still throw (Minor 3). |
| 5 | Zero video size before SPS → no zero/NaN layer | **Holds.** `LayerLayout.compute` falls back to 1280×720 (tested); `LayerConfig` defaults are non-zero; `xrUpdateSwapchainFB` is only issued with real dimensions after a ratio change. |

Latency vs the 2D path: nothing on the branch makes the decoder or the RTP path slower than upstream when the levers are at their defaults (same key set, same feeding code, same `releaseOutputBuffer` call). With levers on, Important 4 and 5 are the two ways AU aggregation could make it *worse* without the panel saying so.

---

### Recommendations

- Put the three decoder-side counters on `DecodingInfo` and the `dec:` line before the first measurement session: AUs closed by marker, AUs closed by next-picture, AUs dropped as too big. Without them the AU lever cannot be interpreted.
- Plumb a thread-hint hook from `app/xr` into videonative so `UdpReceiver` (feeds the codec) and `LLDCheckOutput` (releases output buffers) can be registered as `XR_ANDROID_THREAD_TYPE_RENDERER_WORKER_KHR`/`APPLICATION_WORKER` with the runtime; the current `RENDERER_MAIN` hint on the layer-submitting thread does nothing for glass-to-glass.
- Log every non-success `XrResult` (begin/end session, end frame, request refresh, update swapchain) once at error level; today the only observable of most failures is silence.
- Treat `XrBridge` as the single Java owner of the native lifetime: guard on `handle == 0`, and make `XrVideoActivity` hold it only between `onCreate` and `onDestroy`.
- Consider `askIfMissing=true` for the VPN consent in XR only if the consent dialog is confirmed to work over an immersive activity on Horizon OS; otherwise keep today's message (the manifest exposes `MAIN` + `com.oculus.intent.category.VR`, so the Quest library can launch XR directly without the 2D run the docs assume).

---

### Declined to judge

Behaviours considered and set aside as outside the plan/spec, or belonging to upstream; the executor rules on each:

- Whether Horizon OS composites an Android-surface swapchain as replace-latest (mailbox) without `SYNCHRONOUS_BIT` — spec text supports the assumption, but it is a device question the docs already list as open.
- Whether the Khronos loader on current Horizon OS needs `<uses-native-library android:name="libopenxr_forwardloader.oculus.so">` or `com.oculus.vr.focusaware` meta-data — Meta packaging detail, not in the spec; surfaces on first launch.
- Whether the Quest 2 Codec2 HAL honours `low-latency`, `priority`, `operating-rate`, `vendor.qti-ext-dec-picture-order.enable`, or exposes `c2.qti.*.decoder.low_latency` — spec §6 says measured, not assumed.
- `operating-rate = 32767` (moonlight precedent) vs `INT32_MAX` (ALVR) — spec left the choice to implementation; either is defensible.
- H.265 FU end fragments are forwarded even when a middle fragment was lost (`ParseRTP.cpp:311-317`, no `flagPacketHasGoneMissing` check) — upstream behaviour, unchanged; it only affects AU closing by delivering a corrupt NALU with a valid marker.
- `WfbLinkManager.activeWifiAdapters` is `static` and now shared by two activities with two `WfbNgLink` instances in one process — upstream design; the branch's onPause/onResume ordering makes it work (`startAdapters` re-starts the tracked adapters), and the refactor did not change the semantics.
- `VideoPlayer`/`WfbNgLink` native cleanup via `finalize()` — upstream pattern (see Minor 8 for the XR-specific consequence).
- The three pre-existing `lintDebug` errors (`VideoActivity:1525/2464`, manifest `BIND_VPN_SERVICE`) — not from this branch.
- Stereo, MAVLink OSD, DVR, audio and an in-VR settings UI are absent from XR — spec non-goals.
- `<meta-data android:name="com.oculus.vr.application.type" android:value="openxr">` — I could not confirm this key against Meta documentation; harmless if unknown.

---

### Assessment

**Ready to merge? With fixes.**

**Reasoning:** The architecture is right for the goal — the decoder writes straight into the compositor surface and the OpenXR loop is off the video path — and the 2D app is provably unchanged at defaults, with the levers and their prefs in one tested place. What needs fixing before a headset session is (a) the shutdown ordering (Important 1–3: a null-handle crash window, the INACTIVE detach that can lose the race with the 3 s wfb-ng join, and the missing `xrRequestExitSession` handshake) and (b) two ways the AU-aggregation lever can silently make latency or picture quality worse and the retry/summary gaps that would mislabel a measurement (Important 4–7). All are small, local changes; none require re-architecting. The on-device smoke checklist remains the real gate, and it has not run.
