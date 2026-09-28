# In-headset menu: map of the existing code (2026-09-29)

Scope: a factual map of the code a right-thumbstick-only menu would build on. No design, no code changes.
Baseline: branch `xr-native` at `2df7979` (2026-09-29 02:12). All file:line refs were read in this session unless
marked [unverified]. Paths relative to `C:/xampp/htdocs/pixelpilot-xr/`.

**Headline:** a thumbstick preset menu already exists (commit `eb116f5`). It is text-only, drawn on the same stats
panel surface, and bound to *both* thumbsticks. There is no second layer, no pointer/aim pose, and no in-headset
path to change latency levers.

---

## 1. Stats overlay: how it is composed, rendered and shown

| What | Where | Fact |
|------|-------|------|
| Text lines | `XrVideoActivity.statsLines()` app/src/main/java/com/openipc/pixelpilot/XrVideoActivity.java:419-448 | Builds the lines in priority order: `link: sig %d pkt %d lost %d fec %d bad %d decerr %d` (:428-430, from `WfbNGStats.avg_rssi/count_p_*`), telemetry (`TelemetryLine.format`, :431), video `WxH fps Mbit/s` + preset suffix (:432-434), decode times (:437-438), `linkStatus` (:439), UDP fallback (:440), compositor phase (:441), `XR Hz / comp GPU / drop` (:442-444), `dec:` decoder summary (:445), `exp:` `LatencyExperiments.summary()` (:446). |
| Headline (NO ADAPTER / NO SIGNAL …) | `SignalState` app/xr/src/main/java/com/openipc/xr/SignalState.java:147-163 | `message(kind, since)`: `NO ADAPTER - plug in the RTL8812AU` (:151), `NO SIGNAL (%.1f s)` (:153), `WRONG KEY` (:155), `WAITING FOR VIDEO` (:157), `VIDEO STALLED` (:159); `VIDEO RESUMING`/`SETUP: …` at :116-117. `needsAction()` (:138-140) picks red vs amber and whether the panel moves over the video. |
| Headline arbitration | `XrVideoActivity.drawPanel()` :229-242 | Preset headline (`vmode.headline()`) wins while a switch runs or the video is OK; else the signal headline. When the menu is open its lines are **prepended** to the stats lines (:233-238). |
| Line filter | `PanelMode.select()` app/xr/src/main/java/com/openipc/xr/PanelMode.java:27-30 | detailed (all) / compact (first 3 = link, telemetry, video) / hidden (none; the alert headline still draws). |
| Rendering | `XrStatsRenderer.draw()` app/src/main/java/com/openipc/pixelpilot/XrStatsRenderer.java:42-75 | **Android Canvas → Surface**: `surface.lockHardwareCanvas()` (:46), clear `0xB0000000` (or transparent if nothing, :53), optional red/amber band 54 px with 36 px bold mono headline (:55-61), then 28 px monospace lines every 33 px (:62-67), `unlockCanvasAndPost` (:70). Lines are truncated to width by `PanelText.fit` (app/xr/.../PanelText.java:12-21); lines past the bottom are dropped (:64). No GL, no app render pass. |
| Surface | `XrRuntime::setup()` app/xr/src/main/cpp/XrRuntime.cpp:263-268, `createSurface()` :301-325 | The stats surface is an **OpenXR Android surface swapchain** (`xrCreateSwapchainAndroidSurfaceKHR`, XR_KHR_android_surface_swapchain), created once at start at `statsImageW x statsImageH`; only the video chain has a resize path (:472-478). |
| Layer | `XrLayers::build()` app/xr/src/main/cpp/XrLayers.cpp:56-64 | Head-locked `XrCompositionLayerQuad` in VIEW space, `BLEND_TEXTURE_SOURCE_ALPHA`, pose `(0, statsY, statsZ)`, size `statsWidthM x statsHeightM`. |
| Size / position | `LayerLayout.compute()` app/xr/src/main/java/com/openipc/xr/LayerLayout.java:53-68 | Image **1024x256 px** (:13-14). Quad width = 0.5 x video width (:18, :61), height keeps 4:1; at distance **2 m** (:15). Normally right under the video (:65); while `needsAction()` it is lifted over the lower part of the video (:63-64, lift 6 %). Layout pushed with `XrBridge.setLayout()` (app/xr/.../XrBridge.java:81-87) → `nativeSetLayout` (app/xr/src/main/cpp/xr_jni.cpp:57-80). |
| Capacity | [INFERRED from XrStatsRenderer.java:19-22 + LayerLayout.java:13-14] | ~60 columns; ~6 text lines under a headline, ~7 without. An open preset menu (4 lines, PresetMenu.java:120) pushes the lower stats lines off the panel. |
| Update rate | `statsTick` XrVideoActivity.java:85-119, `STATS_PERIOD_MS = 250` (:39) | Redrawn every **250 ms** on the UI thread (`ui.postDelayed`, :117); started in `onResume` (:208), stopped in `onPause` (:215). Link stats arrive every 300 ms (WfbNgLink.java:70-75), DecodingInfo every 1 s (VideoDecoder.h:184). The native XR loop only re-submits the two layers each frame (XrRuntime.cpp:483-493). |
| Second panel / layer? | `XrLayers.h:38-43`, XrLayers.cpp:64 | **No.** Exactly two layers (`mPtrs[2]`, `mCount = 2`): video (quad or cylinder) + stats quad. Menu, preset headline and alerts are all text on the one stats surface. No toast layer (a Toast is invisible in XR, XrVideoActivity.java:135-136). |

## 2. Controller input (OpenXR actions)

| What | Where | Fact |
|------|-------|------|
| Action set + actions | `XrInput::setup()` app/xr/src/main/cpp/XrInput.cpp:45-93 | One action set `viewer` (:47-49). Actions: `panel_detail` (bool), `panel_visibility` (bool), `preset_stick` (**vector2f, subaction paths left+right**, :55), `preset_apply` (bool thumbstick click, :56). |
| Bindings | XrInput.cpp:63-78 | `oculus/touch_controller`: A (right) + X (left) → detail; B (right) + Y (left) → visibility; **both** `/user/hand/{left,right}/input/thumbstick` → stick; **both** `…/thumbstick/click` → click. `khr/simple_controller`: `select/click` on both hands → detail. No trigger, grip, menu button, aim/grip pose, or haptics. |
| When set up | XrRuntime.cpp:254 | After `xrCreateSession`, before surfaces; failure is non-fatal (viewer works without input). |
| Polling | `XrRuntime::renderFrame()` XrRuntime.cpp:496-500 → `XrInput::poll()` XrInput.cpp:136-149 | Once per frame on the XR thread **after `xrEndFrame`**, traced as `ppxr_input_sync`. `xrSyncActions` must return `XR_SUCCESS` (only a FOCUSED session reports input, :143). |
| Stick → events | `XrInput::stickEvents()` XrInput.cpp:104-134, thresholds XrInput.h:33-34 | Per hand: a flick fires once when deflection > **0.7**, dominant axis → `kStickLeft/Right/Up/Down`; re-armed below **0.3**. Click → `kStickPress` / `kStickRelease` (edge). Left and right hands produce the **same** bits (the hand is not reported to Java). |
| Hand-off to Java | `XrInput::take()` XrInput.h:41; `XrBridge.takeInputEvents()` XrBridge.java:133-135; bit values XrBridge.java:121-128 (= XrInput.h:23-32) | Events are OR-ed into an atomic bitmask (`fetch_or`, XrInput.cpp:148) and taken by the UI thread in the 250 ms stats tick (XrVideoActivity.java:99). [INFERRED: two flicks in the same direction within one tick collapse into one bit; response latency is up to ~250 ms.] |
| What they do | XrVideoActivity.java:99-107; `PanelMode.apply()` PanelMode.java:18-24; `PresetMenu.update()` PresetMenu.java:56-90 | A/X: compact ↔ detailed (or un-hide). B/Y: hide/show panel; with the menu open, B/Y closes the menu instead (`passThrough`, PresetMenu.java:51-53). Any flick opens the preset menu; then left/right = MODE, up/down = QUALITY; hold click **1 s** = apply, **3 s** on the active choice = save default; idle **6 s** closes (PresetMenu.java:12-14). |
| Test injection | `DebugInput` app/xr/.../DebugInput.java:16-29; receiver XrVideoActivity.java:76-83, :245-254 | Debug builds: `adb shell am broadcast -a com.openipc.pixelpilot.xr.DEBUG_INPUT --es input right|left|up|down|press|release|detail|visibility` → `XrBridge.injectInputEvents()` (XrBridge.java:138-140), same path as real input. Used by `scripts/quest/preset_flow.py`. |
| Tests | app/xr/src/test/java/com/openipc/xr/ | `PresetMenuTest`, `PanelModeTest`, `DebugInputTest` exist (JVM). No native test for XrInput [unverified: none found under app/xr]. |
| Real-controller status | docs/xr/presets-design.md:3 | "real thumbsticks … pending": the menu was exercised on the headset via the debug broadcast, not by hand [PROVEN: doc status line; not re-verified on device here]. |

## 3. Preset / VMODE1 client code

| Class | Where | What it does |
|-------|-------|--------------|
| `VmodeProtocol` | app/src/main/java/com/openipc/pixelpilot/VmodeProtocol.java:15-106 | Pure line format `VMODE1 <verb> key=value`: `list`, `apply` (preset and/or kbps, `revert_s`), `commit token`, `save_default`; `parse()` → `Reply` (seq -1 = 1 Hz state beacon). |
| `VmodeSender` | VmodeSender.java:6 | One-method transport interface (`request(verb, build)`), faked in tests. |
| `VmodeClient` | VmodeClient.java:23-124 | UDP to **`10.5.0.10:9998`** (:25), pref override `vmode_air` = `a.b.c.d:port` (:27, :54-58); one socket; resend every `retryMs` up to `tries` (activity uses 300 ms x 5, XrVideoActivity.java:274); rx thread `vmode-rx` (:62). |
| `VmodeSession` | VmodeSession.java:19-176 | Menu action → `apply`/`save_default` (:57-66); list keepalive 60 s (:23, :75); `CommitGate` sends `commit` once the new mode decodes (:76-77); headline via `PresetStatus`; `videoSuffix()` for the video line (:90-97). |
| `CommitGate` | CommitGate.java:1-51 | Commit only after the air reports pending with our token and N frames decode at the new size (:4-6, :19-33). |
| `PresetCatalog` / `PresetStatus` / `PresetMenu` | app/xr/src/main/java/com/openipc/xr/ | Catalog from the `list` reply (modes with label/desc/fov/g2g, qualities with kbps/cost); headline strings (≤ 40 chars); the menu state machine (§2). |
| Wiring | `XrVideoActivity.startPresets()` :257-282, called from `onCreate` :164 | Only when the wfb link starts (not with a bad key / no link). Callbacks posted to the UI thread; ticked in `statsTick` :103-107; closed in `onDestroy` :288-290. |
| UI that triggers it | — | **Only the thumbstick menu** (and its debug broadcast). The 2D `VideoActivity` has no preset UI [INFERRED: no Vmode* reference outside XrVideoActivity/Vmode* files in the grep]. |
| Design doc refs from code | grep `presets-design` | Javadoc/comments in VmodeClient.java:18, VmodeProtocol.java:12, VmodeSession.java:14, CommitGate.java:4, XrVideoActivity.java:71, XrInput.h:9, PresetCatalog.java:7, PresetMenu.java:6, PresetStatus.java:6, scripts/quest/vmode_fake.py:1. |
| Air side | docs/xr/HANDOFF.md:17 | `vmoded` (`4908c6e8`, UDP 9998) exists on the air unit but is **started by hand**, not at boot. Fake air for tests: `scripts/quest/vmode_fake.py`; headset flow `scripts/quest/preset_flow.py`. |

## 4. Latency-experiment prefs: read and applied when

| Point | Where | Fact |
|-------|-------|------|
| Keys + defaults | app/videonative/src/main/java/com/openipc/videonative/LatencyExperiments.java:15-46 (keys), :103-140 (read) | Prefs file `general`. Decoder-config levers: `low_latency_decoder`, `dec_picture_order`, `dec_operating_rate`, `dec_prefer_low_latency_component`, `au_aggregation`, `dec_debug_key_mask`, `dec_component`. Stream levers: `rtp_tight_reorder` (default true), `feed_incomplete_frames`, `request_idr_on_loss` + `idr_min_interval_ms`, `freeze_until_idr`. XR: `xr_refresh_hz`, `xr_use_timestamps`, `xr_layer_shape`, `xr_perf_sustained_high`, `xr_fov_deg`, `xr_flip_vertical`, `xr_thread_hints`, `xr_autostart`, `xr_phase_report`, `xr_latch_to_display_us`. |
| Read in XR | XrVideoActivity.java:125 | `LatencyExperiments.load(this)` **once in `onCreate`**; the snapshot drives `xr.start(...)` (:128-129), `CompositorPhase` (:143), `setDecoderLevers` (:147), layout (:358-362), thread hints (:113) and the `exp:` line (:446). Nothing re-reads prefs during the session. |
| `setDecoderLevers` | VideoPlayer.java:152-159 (Java) → VideoPlayer.cpp:382-439 (JNI) → VideoPlayer.h:61-74 | Called only at XR `onCreate` (XrVideoActivity.java:147) and 2D `initializeVideoPlayers` (VideoActivity.java:436). |
| Could be live natively | VideoPlayer.h:63-74; ParseRTP.h:45,90; FreezeUntilIdr.h:13,21,59; IdrRequester.h:32,56; BufferedPacketQueue.h:73,159-160 | FIF, IDR-on-loss (+ interval), freeze-until-IDR and tight reorder are atomics/setters safe from another thread, so a new `setDecoderLevers` call would take effect at the next packet [INFERRED from the atomics + VideoPlayer.java:149-150 comment]. **Today no code calls it mid-session.** |
| Only at decoder configure | VideoDecoder.h:95-100 | LL / PO / OR / LLC / AU / debug mask / component are stored and used "the next time the decoder is configured, not to a running decoder". [INFERRED: an XR video detach/attach (session INACTIVE→ACTIVE, XrVideoActivity.java:337-356) reconfigures the decoder and would pick them up.] |
| XR levers | XrRuntime.cpp:406-407, :254-272; LayerLayout | Refresh rate, perf level, timestamps are applied at session start/READY; FOV/shape/flip at layout (could be re-pushed live via `setLayout`, but the stats swapchain size is fixed at start). |
| `sameXrStart` | LatencyExperiments.java:208-219; used at XrVideoActivity.java:172-178 | Compares only XR levers (refresh, timestamps, shape, perf, FOV, flip, thread hints, phase report, latch offset). Used in `onNewIntent`: if a re-launch of the singleInstance XR activity sees changed XR levers, it calls **`recreate()`** (full onCreate again: new XrBridge, link, player). Decoder levers are deliberately not compared (:210-211). Test: LatencyExperimentsTest.java:214-220. |
| Existing restart paths | VideoActivity.java:269-282 `resetApp()` | Launch intent with `NEW_TASK | CLEAR_TASK`, `finish()`, **`System.exit(0)`**; prefs written with `commit()` first (:802-808, :898-901). Used by the 2D "Low latency" toggle (:797-808), 2D decoder toggles `addRestartingToggle` (:830-837, :891-904), and the object-detection renderer swap (:2145-2155). No `Process.killProcess`. |
| 2D menu coverage | VideoActivity.java:828-865 | "Latency experiments" has decoder toggles (PO, OR, LLC, AU; restart) and XR items (refresh, FOV, curved, timestamps, perf, hints, flip; `apply()`, no restart, picked up at next XR start). **No menu item for FIF, request_idr_on_loss, freeze_until_idr, rtp_tight_reorder** (grep found no such key in VideoActivity). |
| How those are set today | scripts/quest/quest_adb.py:10, :38-50, :110-113; pref_ab.sh:16 | Scripts rewrite `shared_prefs/general.xml` via adb while the app is stopped, `am force-stop`, then relaunch XR. |

## 5. Link and decoder stats available in the app

| Source | Where | Fields |
|--------|-------|--------|
| `WfbNGStats` (Java) | app/wfbngrtl8812/src/main/java/com/openipc/wfbngrtl8812/WfbNGStats.java:7-21 | `count_p_all`, `count_p_dec_err`, `count_p_dec_ok`, `count_p_fec_recovered`, `count_p_lost`, `count_p_bad`, `count_p_override`, `count_p_outgoing`, `avg_rssi` (0-100 link-quality score, not dBm), `rssi_a`/`rssi_b` (raw gain_trsw, 1 dB units), `snr_a`/`snr_b` (raw rxsnr, 0.5 dB units). Video channel only; per 300 ms window. |
| Producer | WfbngLink.cpp:488-553 `nativeCallBack`; timer WfbNgLink.java:69-75 (300 ms) | Takes and resets the video + tunnel aggregator windows under `agg_mutex` (:496-502); `avg_rssi` = `calculate_signal_quality().quality` mapped -1024..1024 → 0..100 (:528-529). Tunnel window only logged (`tunnel window: pkts … lost … fec_recovered … dec_err`, :508-516), **not** passed to Java. Callback `onWfbNgStatsChanged` → XrVideoActivity.java:384-388. |
| `SignalQualityCalculator` | app/wfbngrtl8812/src/main/cpp/SignalQualityCalculator.h:17-30 | Per 1 s window: `lost_last_second`, `recovered_last_second`, `quality`, `snr`, `idr_code`, per-chain RSSI/SNR averages. Fed from the RX lambda: `add_rssi`/`add_snr` with `RxAtrib.rssi[0..1]`, `snr[0..1]` (WfbngLink.cpp:235-237); `add_fec_data` in the stats callback (:526). |
| `DecodingInfo` | app/videonative/src/main/java/com/openipc/videonative/DecodingInfo.java:10-19 | `currentFPS`, `currentKiloBitsPerSecond`, `avgParsingTime_ms`, `avgWaitForInputBTime_ms`, `avgHWDecodingTime_ms`, `avgTotalDecodingTime_ms`, `nNALU`, `nNALUSFeeded`, `nDecodedFrames`, `nCodec`. Recomputed every 1 s (VideoDecoder.cpp:404-424, interval VideoDecoder.h:184). Also `getDecoderSummary()` string and `drainFrameReadyTimes()` (VideoPlayer.java:163-178). |
| XR runtime | XrRuntime.h:33-40; XrBridge.Info | `refreshHz`, `requestedHz`, `compositorGpuMs`, `droppedFrames`, `motionToPhotonMs`, read every 30 frames (XrRuntime.cpp:501-505, :563-575). |
| Per-packet MCS/GI/STBC/BW/LDPC | devourer: app/wfbngrtl8812/src/main/cpp/devourer/src/RxPacket.h:22-66; jaguar1/FrameParser.cpp:112-123 | **Parsed but not used.** devourer fills `RxAtrib.data_rate` (16-bit rate code, HT 0x80+/VHT 0x100+), `bw`, `stbc`, `ldpc`, `sgi`, `evm[4]`, `tsfl`, `ppdu_cnt`, `ppdu_type` from the RX descriptor. The app's RX lambda (WfbngLink.cpp:221-237) reads only `crc_err`/`icv_err`, `rssi[0..1]`, `snr[0..1]`; a grep for `data_rate` / `RxAtrib.stbc|sgi|bw|ldpc|evm` outside devourer found nothing. NSS is not a separate field [INFERRED: encoded in the VHT rate code]. There is no radiotap RX parsing in the app path (devourer's Radiotap* files are TX-side builders/peek) [unverified in detail]. |
| TX-side link knobs (GS uplink) | LinkOptions.java:18-29; WfbngLink.cpp:305-330 | adaptive link on/off, TX power, FEC/LDPC/STBC use, FEC thresholds, uplink rate/FEC/MCS (`uplink_*` prefs). Applied once at XR `onCreate` (XrVideoActivity.java:162). |

## 6. Other code talking to the air over the tunnel

| Channel | Where | Fact |
|---------|-------|------|
| Tunnel itself | WfbNgVpnService.java:155-158, :181-196, :247-249 | VPN `10.5.0.3/24`, route `10.5.0.0/24`; downlink from the wfb UDP aggregator on UDP 8000 (WfbngLink.cpp:101-107), uplink to local wfb TX at `127.0.0.1:8001`. Bound by both activities (XrVideoActivity.java:205, `vpnBinding`). |
| Adaptive-link uplink | `WfbngLink::start_link_quality_thread` WfbngLink.cpp:564-675; started in `run()` :341-344 | UDP to **`10.5.0.10:9999`**, length-prefixed text `<time>:<score>:<score>:<fec_rec>:<lost>:<score>:<snr>:0:-1:<fec_change>:<idr_code>` (:647-657), paced by `UplinkSchedule` (:633-643). Note: the `rssi_dB` slot carries `quality.quality`, not an RSSI (:655) [PROVEN from the format args]. |
| IDR request | `IdrRequester` app/videonative/src/main/cpp/IdrRequester.h:18-40, .cpp:80-110 | TCP HTTP `GET /request/idr` to **`10.5.0.10:80`** (waybeam), on its own thread, when `request_idr_on_loss` is on and the parser reports an RTP gap. |
| Presets | VmodeClient (§3) | UDP **`10.5.0.10:9998`**, `vmoded`. |
| Phase report | `CompositorPhase` app/src/main/java/com/openipc/pixelpilot/CompositorPhase.java:23-35, :69; docs/xr/phase-lock-protocol.md:17 | PPXR1 UDP to pref `xr_phase_report` (`host:port`, empty = off); for the air the doc suggests `10.5.0.10:5610`. |
| Air web UI | VideoActivity.java:1998-2008 | 2D only: `WebView.loadUrl("10.5.0.10")` in a dialog. |
| MAVLink | WfbngLink.cpp:93-99 | Separate wfb radio port (0x10) → local UDP 14550; `MavlinkNative` in the stats tick (XrVideoActivity.java:89). Not the IP tunnel. |
| Sidecar UDP 5602 | — | **No app code.** Only the PC script `scripts/quest-latch/sidecar_log.py` (subscribe to waybeam's per-frame sidecar on 5602) and docs (g2g-budget.md). In the working tree there is an **untracked, uncommitted test** `app/src/test/java/com/openipc/pixelpilot/stats/SidecarProtocolTest.java` for a not-yet-existing `SidecarProtocol` class, and `app/xr/src/test/java/com/openipc/xr/OptionCostsTest.java` (+ `app/xr/build.gradle` org.json test dep, modified) for a not-yet-existing `OptionCosts` / `res/raw/option_costs.json` — another session's work in progress (test-first). |

## Gaps relevant to a right-stick-only menu (facts, not design)

- Stick and click are bound on **both** hands and merged into one bitmask; nothing distinguishes the right hand in Java (XrInput.cpp:68-71, :104-134).
- Input reaches Java only at the 250 ms stats tick, as edge bits (XrVideoActivity.java:39, :99).
- One text surface, 1024x256, shared by headline, menu and stats; the stats swapchain cannot be resized after start (XrRuntime.cpp:264, :472-478).
- No live re-apply of latency prefs in XR; the only restarts are `recreate()` on `onNewIntent` (XR levers only) and 2D `resetApp()` / `System.exit(0)`.
- Per-packet rate/BW/STBC/LDPC/SGI are available in devourer's `RxAtrib` but dropped by the app.
