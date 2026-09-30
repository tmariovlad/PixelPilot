# Channel survey before a flight: design (2026-09-30, no code yet)

**Status: phase 1 built on branch `survey` (§7), not merged, not on the headset; phases 2–3 (menu, push to the air) not started.** From [BACKLOG.md](../../BACKLOG.md), first item: a calibration mode that says which 5 GHz
channel is free right now, shows the strong signals as a graph, and moves the link there.
- **Why measure instead of hard-coding:** on 2026-09-29, ch165 cut residual loss 3.5–6× vs ch157, with the neighbour
  "Staff" VHT80 on 149–161 ([channel A/B](link-envelope.md), [air log](data/air-chan-ab7-2026-09-29.txt)). R3′ on
  2026-09-28 found the opposite: 165 lost as much as 157, and a beacon-locked source was active on 165 that night
  (link-envelope R3′). The best channel depends on the neighbours at the time [PROVEN: both runs].
- **Scope:** UNII-1 36–48 and UNII-3 149–165. DFS 52–144 is excluded, because the air has no radar detection.

Keywords: channel survey, spectrum, site survey, busy time, CCA, NHM, noise histogram, neighbour AP, BSS load,
foreign frames, bad FCS, recommended channel, VMODE1 ch=, A6a chan, calibrare canal, canal liber, grafic spectru.

## 1. Sources

### 1a. The RTL8812AU through devourer (primary: sees our band and our link's frames)

What devourer exposes (submodule `devourer` @ `af0ae6d`):

| What | Where | Notes |
|---|---|---|
| Retune | `IRtlDevice::SetMonitorChannel` (`src/IRtlDevice.h:67`), `FastRetune(channel)` (`:78`, the lean intra-band hop) | Hop cost: a ~1.5 ms VCO settle floor [PROVEN: `docs/frequency-hopping.md:373-375`]. devourer's sweep reports the measured `retune_us` per dwell [PROVEN: `docs/rx-spectrum-sensing.md:164-166`]. |
| Frame-free energy | `GetRxEnergy(with_nhm)` (`src/IRtlDevice.h:530`, struct `src/RxSense.h:30-60`; 8812A reader `src/jaguar1/RtlJaguarDevice.cpp:274-316`) | Per call, deltas since the previous call: OFDM/CCK false-alarm and **CCA (channel-busy)** counts (BB 0xF48 / 0xA5C / 0xF08). DIG gain index `igi` (0xC50): higher = noisier. With `with_nhm`, the **NHM** 12-bucket in-band power histogram (~2 ms window). |
| NHM busy | `rx.nhm` semantics (`docs/rx-spectrum-sensing.md:100-117`) | `busy` = percent of samples above the lowest bucket, a **time share of energy, frame-free**: it also sees non-Wi-Fi interferers. `peak` = fullest bucket. |
| Absolute noise floor | `RxEnergy.abs_noise_floor_dbm` | **Not per channel on the 8812A:** the RX-idle CAL is taken at bring-up and not re-run after a hop [PROVEN: `RtlJaguarDevice.cpp:308-313`]. Not a survey signal. |
| Per-frame attributes | `RxAtrib` (`src/RxPacket.h:37-66`): `crc_err`, `icv_err`, `data_rate`, `bw`, `rssi[4]`, `snr[4]`, `evm[4]` | Frames with a bad FCS reach the app only with `keep_corrupted` on (`RxDiag`, [fec-block-probe §1](fec-block-probe.md)). |
| Sweep reference | `DEVOURER_RX_SWEEP` in devourer's rxdemo (`docs/rx-spectrum-sensing.md:151-170`) | The RX loop runs on a worker thread while another thread calls `FastRetune` between reads. Per bin it gives energy counters + a per-dwell frame aggregate (frames, RSSI, SNR, EVM). A per-SA filter exists (`DEVOURER_RX_AGG_SA`). This is the pattern to copy. |

**What the app adds per dwell** (in `WfbngLink`'s RX callback, which already classifies every frame:
`IsValidWfbFrame` / `MatchesChannelID`, `WfbngLink.cpp:236-306`):
- **Own vs foreign frames.** A frame is "own" when it is a valid wfb frame with our channel id; everything else is
  foreign.
- **Foreign airtime share:** Σ (frame length × 8 / PHY rate from `data_rate`/`bw`) over the dwell. This is the
  frame-based busy share that excludes our own link [INFERRED from the RxAtrib fields; the rate→µs table is new code].
- **Strongest foreign RSSI** (dBm = raw − 110, devourer `LinkHealth.cpp:8`).
- **Bad FCS per second** (keep_corrupted on).
- **Energy:** CCA / FA deltas and NHM `busy` / `peak`.

### 1b. The Quest's internal Wi-Fi scan (secondary: names the neighbours)

`cmd wifi start-scan` then `cmd wifi list-scan-results` give SSID, BSSID, primary frequency, channel width / centre and
RSSI per BSS [SPECULATION on Horizon OS: not probed yet. Probe: `adb shell cmd wifi start-scan; sleep 5; adb shell cmd
wifi list-scan-results`]. It shows **which 20 MHz channels an 80/160 MHz BSS covers**, which the RTL cannot tell from
energy alone.
- **BSS load** (channel utilization, 0–255) is in the beacon IE, but `list-scan-results` may not print it
  [SPECULATION]. `WifiManager.getScanResults()` exposes the raw IEs.
- **From the app:** it needs `ACCESS_FINE_LOCATION` + `CHANGE_WIFI_STATE`; the manifest has only
  `ACCESS_WIFI_STATE` today [PROVEN: `app/src/main/AndroidManifest.xml:12`]. Android also throttles `startScan` for
  foreground apps (4 per 2 min) [SPECULATION for Horizon OS].
- **Caveat:** an active scan transmits probe requests from the internal radio. Next to the RTL that disturbs the link,
  as streamed logcat over Wi-Fi did (T4, [uplink analysis](uplink-t4-analysis.md)). So the Quest scan runs **before**
  the RTL sweep, never during a link run [INFERRED].

The PC is not a source: its card scans only 36–100 (BACKLOG).

## 2. Duration, and the link

- **One adapter:** the RTL is also the video receiver, so a sweep means **no video** for its duration. The survey is a
  pre-flight mode, not a background task [PROVEN: one adapter in the app; `WfbngLink` owns it].
- **Dwell 1 s per channel.** That covers ~10 beacon intervals (102.4 ms) and 4 reads of 250 ms, each read the energy
  deltas plus one NHM (~2 ms).
- **Three interleaved passes** over the 9 channels (36 40 44 48 149 153 157 161 165), so a neighbour's burst does not
  land on one channel only: **~27 s + 27 hops × ~2 ms**. A "thorough" option: 3 s per dwell, ~80 s.
- **The air keeps transmitting on its channel** during the sweep:
  - Its frames are counted as own and left out of the foreign share.
  - CCA / NHM on the link channel include our own energy, and the adjacent channels include its leakage at ~1 m
    [INFERRED]. So the graph marks the link channel's energy bar "incl. our link", and the score uses the frame-based
    foreign share there.
  - VMODE1 has no "quiet" verb [PROVEN: [menu-design §7](menu-design.md) lists none]. A short air TX pause for the
    sweep would be a new verb, optional.
- **After the sweep** the app retunes back to the link channel and waits for video. The existing health log records
  the gap (PPXR_EVENT) [PROVEN: [health-logging](health-logging.md)].

## 3. Score, graph, script

> **Correction (2026-09-30, phase 1):** devourer already has a channel-survey library, `src/chanmig/`: the `SurveyDwell` record with own/other airtime (`frame_airtime_us`), `ScanPlan`, JSONL emitters and parsers, and a pure scoring engine `RecommendEngine` with `PolicyConfig` (qualify ≤ 20 % occupancy, burstiness, min 3 rounds / 3 s per bin, hysteresis margin) [PROVEN: `src/chanmig/ChannelScore.h:71-163`, `SurveyRecord.h`, `chanmig/CLAUDE.md`]. The app already compiles it (`CMakeLists.txt:52-53`). Phase 1 uses that engine, not the hand-made cost below, which stays only as the design-time sketch. The graph and the log follow chanmig's schema.

**Per channel c:**
- `occ(c)` = max(RTL foreign airtime %, the highest BSS load % among Quest-scan BSSs whose span covers c).
- `sig(c)` = the strongest foreign RSSI on c (RTL frames, or a covering BSS from the Quest scan), dBm.
- `noise(c)` = NHM busy % on non-link channels (non-Wi-Fi energy).
- `fcs(c)` = bad FCS per second.
- **cost(c) = occ(c) + 0.5 × max(0, sig(c) + 90) + 0.5 × noise(c) + 2 × fcs(c)**. The weights are starting values,
  to be calibrated by §5 [SPECULATION until then].
- **Recommended** = argmin cost over the channels the air lists (VMODE1 `list`, `channels:`), with hysteresis: propose a
  move only if cost(best) < 0.8 × cost(current).

**Graph (in-headset menu, [menu-design](menu-design.md) "Link ▸ Channel survey"):**
- 9 bars over two groups, 36–48 | 149–165, with the DFS gap drawn empty.
- Bar height = occ %. Colour = sig: green < −80, amber −80…−65, red > −65 dBm.
- An outline marks the current channel, a star the recommended one, and "incl. our link" labels the link channel.
- Actions:
  - **Run survey (video off ~30 s)**;
  - **Switch to ch N**, the two-phase A+Q switch of §4, only for a channel the air lists.
- Right thumbstick only, like the rest of the menu.

**Log and script:**
- One line per dwell, tag `PPXR_SURVEY`: `pass= ch= dwell_ms= retune_us= own= foreign= foreign_air_pct= foreign_rssi_max=
  bad_fcs= cca_ofdm= fa_ofdm= igi= nhm_busy= nhm_peak=`. Captured detached like the other tags (`ab_detached.sh` -s
  list).
- `scripts/quest/channel_survey.py` (new, [SPECULATION until written]) joins the PPXR_SURVEY lines with a saved
  `cmd wifi list-scan-results` and prints the per-channel table, the score and a text bar chart (PNG optional).
  Offline tests on recorded lines.

## 4. How the recommended channel reaches the air

- **The air side exists: VMODE1 `apply ch=<n>`**, two-phase [PROVEN: OpenIPC `repos/tools/vmoded/src/sm_ext.c` (`ch=`
  validation `:382-384`, the `ch_to=` / `switch_in_ms` announce in the beacon `:212-221`, resume on restart
  `:134-136`), design and implementation notes in `repos/tasks/vmode-presets-2026-09-27/03-DESIGN-menu-extension.md`
  and `04-IMPL-menu-extension.md:171-178`].
  - The air acks `switch_at_ms = air epoch + 1500`, and both ends switch then.
  - The air retunes through `linkmode-air.sh chan <ch>`, the A6a patch: no waybeam or wfb_tx restart, and a verdict
    `AIR_STATE=wfb FREQ= CH= BCN=` [PROVEN: `deploy/a6/linkmode-air.sh.A6a:287-292`].
  - The app commits after 30 frames. Otherwise the air reverts after `revert_s`, and the app does the same on its own
    after `revert_s` + 2 s without video ([menu-design §7.4](menu-design.md)).
  - The deployed air logs `EXT on: … ch=165 chan_verb=1` [PROVEN: vmoded logs in the OpenIPC deploy dirs].
- **The Quest side is not built.** The app sets its channel from its preference (`VideoActivity.getChannel`,
  `WfbLinkManager.setChannel`, `VideoActivity.java:181, 1693`) and does not read `ch_to` / `switch_in_ms` yet
  [PROVEN: grep, no hit]. It is menu phase 2 ([menu-design §8](menu-design.md)).
- **Two risks to settle in that build:**
  - **DFS.** A6a's own list accepts 52–144 (`LINKMODE_CHANNELS` default, `:292`), so the non-DFS restriction must
    come from vmoded's limits (`lim_channel_ok`, `sm_ext.c:384`). `limits.conf` must list only 36–48 and 149–165
    [INFERRED; check the deployed limits.conf].
  - **Persistence.** A live retune wins only until the air reboots: `/tmp/linkmode.chan`, then `hostapd.conf`'s
    `channel=` [PROVEN: `A6a:148-151`]. The app's preference persists, so after an air reboot the two can disagree.
    Fix: the app follows the VMODE1 beacon's `ch=` when it has no video, or the switch also persists the channel on the
    air (`save_default`) [design choice for the OpenIPC side].
- **O123, approved by the coordinator 2026-10-01 (with openipc-…-1f): the air's channel is the truth.**
  - **Rule 1 (built, `ChannelFollow`, branch `o123-chfollow`):** a VMODE1 state beacon's `ch=` updates the stored
    channel (`wifi-channel`, `VideoActivity.storeChannel`) when it is legal (`LegalChannels`), settled
    (`phase` ok / reverted; of vmoded's six phases, `sm.c:36-44`, confirmed by -1f) and carries no `ch_to=`. Not
    `failed`: a failed channel revert keeps vmoded's `ch` at the switch target (`sw_chan.c` TX_REV_WFB → `ext_failed`,
    which does not re-read it; 36's review). It is logged, nothing is sent to the air, the radio is
    not touched (over the default wfb target a heard beacon means the RTL is already on that channel), and the next link start tunes to it.
    Every settled beacon counts, not only the first after a reconnect, so the store step after a completed switch
    (rule 2) is the same code. A v1 beacon has no `ch=` (EXT only: vmoded `sm.c:466-467`) and is ignored
    [PROVEN: `ChannelFollowTest`, 8 tests; 5 mutants killed (the ch_to, phase, failed, verb and DFS checks)].
  - **`LegalChannels`** (36–48, 149–165) is the app's one copy of the air's `lim_channel_allowed()` (OpenIPC
    `repos/tools/air-common/src/limits.c:225`), pinned by `LegalChannelsTest` against the same rule.
  - **Rule 2 (follow `ch_to=` at `switch_in_ms`, live RTL retune, app-side revert):** not built; after the
    2026-10-01 slots.
  - **Save:** no new verb. The existing `save_default` also persists the channel on the air (`/etc/linkmode.chan`),
    new error `state=error reason=chan_fail` [from -1f, commit pending].
  - **Find the air (approved follow-up after rule 2):** when a volatile retune is lost to an air reboot, the app
    listens on the wrong channel, hears no beacon, and rule 1 cannot fire. After ~10 s with no beacon and no video,
    hop the legal set, RX-only (uplink and alink reports paused), starting with the last saved default, then the
    stored channel, then the rest; settle on the first channel with our link id, then rule 1 stores it. The survey's
    single-control-thread rules apply, and each hop is logged.

## 5. Validation plan (before the score drives anything)

1. **Replay the known case.** Run the survey at the 2026-09-29 geometry. It must rank 157 below 165 because of the
   covering VHT80 "Staff" BSS, as that night's A/B found (post-FEC 3.5–6× worse on 157).
2. **A/B on two channels picked by the survey:** the recommended one and the worst allowed one, or the current one.
   - ABAB × 2, 120 s steps, the same geometry and air state (MCS/FEC/bitrate fixed), a detached capture, keep_corrupted
     on.
   - Metrics per step:
     - `crc/s` (bad FCS per second, `RxDiag` / `ppxr_rx_*` counters);
     - `p_data` (accepted wfb data packets per second, and loss before FEC; `link_audit.py`);
     - post-FEC loss (RTP holes: `rtp_holes.py`, `fec_blocks.py`).
   - Run the survey just before and just after the A/B, to see whether the neighbours changed during it.
3. **Pass:** the survey's order equals the A/B's post-FEC order in both repetitions. Then repeat on another day or in
   another position, since the neighbours change (R3′ vs 09-29). Two agreeing days → the score may drive the menu's
   recommendation. A disagreement → recalibrate the weights, e.g. more weight on `fcs` if bad FCS predicts better than
   occupancy.
4. **Record:** results into [link-envelope](link-envelope.md) (channel section), data into `docs/xr/data/`, and this
   doc's weights updated with the evidence.

## 6. Open questions

- Does Horizon OS's `cmd wifi list-scan-results` print the channel width / centre and the BSS load? (§1b probe)
- Is the 8812A's NHM busy % stable enough in 4 reads per second? Or should dwells lengthen on noisy channels? (§5 run)
- Is a short air TX pause (a new VMODE1 verb) worth it, to measure the link channel's energy without our own
  transmitter? (§2)


## 7. Phase 1, built (branch `survey`, 2026-09-30; no menu, no push to the air)

- **Switch:** pref `survey_on_start`, **off by default** (`SurveyPref.java`, JVM test). `LinkOptions.apply` passes it
  to native (`WfbNgLink.setSurveyOnStart`). Native runs it **once per app launch**: the flag clears when the survey
  starts, so a link restart in flight never repeats the ~30 s blackout.
- **Run** (`WfbngLink::run_survey`):
  - at link start, after bring-up, on its own thread while the RX loop feeds it. During the survey every received
    frame goes to the survey instead of the aggregators, so there is no video;
  - 20 MHz, the 9 candidates × 3 rounds, round-major;
  - per dwell: `FastRetune`, 30 ms settle, a discard `GetRxEnergy(false)` (the FA/CCA counters are delta-on-read),
    1000 ms of observation, then `GetRxEnergy(true)` with NHM;
  - then back to the link channel (`SetMonitorChannel`), and **only then** the uplink starts (`start_uplink`), so no
    uplink frame goes out on a surveyed channel;
  - it stops within ~50 ms on a stop request or when the RX loop ends; `run()` joins it before the device is released.
- **Record and score:** devourer's chanmig (`ChannelSurvey.h` is the thin app layer).
  - `DwellBuilder` fills `SurveyDwell`. Own = a valid wfb frame of our video/mavlink/tunnel channel ids, other = the
    rest; both are timed with `frame_airtime_us`. Bad-FCS frames are skipped.
  - `recommend()` feeds `RecommendEngine` (default policy). Pre-flight, with no active-link telemetry, the engine
    holds, but its ranking scores every candidate. The recommendation is the best qualified one.
- **Log:** tag `PPXR_SURVEY`, one JSONL event per line: `survey.start`, 27 × `survey.dwell` (chanmig schema v1),
  `channel.ranking`, `survey.result`. Now in ab_detached.sh's `-s` list.
- **Graph:** [scripts/quest/channel_survey.py](../../scripts/quest/channel_survey.py) (test `test_channel_survey.py`).
  It prints a per-channel text bar chart: foreign airtime %, NHM busy, the strongest foreign signal, the engine's score,
  and the link and the recommendation marked. `--png` gives the same as an image. It only reads what the Quest
  computed.
- **Tests:**
  - host `ChannelSurvey_test.cpp`, 7 tests: plan, schedule, NHM helpers, own/other attribution, a busy channel ranked
    last and not qualified while our 50 % own video on the link channel is not occupancy, the JSONL lines;
  - wfb host suite 80/80;
  - JVM app 156 / videonative 22 / xr 134;
  - `test_channel_survey.py` 3;
  - mutation: counting own frames as other fails the attribution and the ranking tests.
- **After pixelpilot-xr-25's review (2026-10-01):**
  - The lifecycle lives in `SurveyRunner.h`: the thread, the abort flag and the dwell loop, with the device injected
    as `SurveyOps`. Host tests (`SurveyRunner_test.cpp`, 5) run it on a fake device.
  - **B1:** `release_link()` calls `survey.stopAndJoin()` first, on every way out of `run()`, including a throwing RX
    loop. After it returns no device call follows (test: nothing recorded 100 ms after the join; the abort lands within
    200 ms).
  - **B2:** the retune back is retried once. If it fails again, outcome `retune_back_failed`: no uplink, and
    `StopRxLoop()`, so `run()` returns and `WfbLinkManager.checkHealth` restarts the link (RestartPolicy backoff). The
    one-shot flag keeps the survey from repeating.
  - **S1:** a TX power set during a survey is only stored (`tx_power_pending`) and applied when the survey completes,
    before the uplink starts: devourer allows one control thread (IRtlDevice.h:110-117).
  - **M1:** `survey_on_start` is an `std::atomic<bool>`, consumed with `exchange(false)`.
  - An aborted survey does no retune back and starts no uplink (the device is being torn down).
  - `survey.result` carries `outcome` = completed / aborted / retune_back_failed (and `failed` since the re-review below).
  - Mutations: dropping the retry fails the two retune-back tests; a `stopAndJoin` without the abort flag fails the
    join test.
  - Tests: host 85/85, JVM app 156 / videonative 22 / xr 134, test_channel_survey 3.
- **After 25's re-review of 9c10829 (2026-10-01):**
  - **B3 (a regression from 9c10829):** a device exception mid-sweep that nobody asked for (to20 / retune-to-20 /
    energy throwing, no stop) had become `aborted`. That meant no retune back and no uplink: the RX loop stayed on a
    survey channel and the video stayed dead until a manual restart. Now `run()` tells the two cases apart: an
    exception with `cut()` set is still `aborted`; without it the outcome is **`failed`**. A failed survey goes back to
    the link channel (with one retry, then `retune_back_failed`) and logs no ranking. `survey::starts_uplink()`
    (Completed or Failed) tells `WfbngLink`'s done callback to start the uplink.
    [PROVEN: `SurveyRunner_test.cpp` ADeviceErrorMidSweep… (energy throws on its 3rd call: `back` ≥ 1, outcome
    failed) and …WhoseRetuneBackAlsoFails… (retune_back_failed)]
  - **S1 residue:** `SurveyRunner::ifActive(f)` runs `f` under the lock that `run()` also takes to clear `active_`
    before `done()`. `nativeSetTxPower` stores `tx_power_pending` through it, so a set either lands during the survey
    (done() applies it) or after it (applied at once). It can no longer fall between the two.
  - **Nit:** a stop that lands during the retune back now ends as `aborted`, with no uplink for `release_link` to tear
    down.
  - Mutations: an exception mapped to aborted fails both B3 tests; `ifActive` ignoring `active_` fails the ifActive
    test; dropping the `cut()` check after the retune back fails the stop-during-back test.
  - Tests: host 90/90 (SurveyRunner 10); `assembleDebug` builds (APK md5 4ed809d5).
- **25's notes on 1b8c741 (not blockers, 2026-10-01):**
  - `adaptive_tx_power` is now an `std::atomic<int>` (WfbngLink.hpp). The JNI thread writes it while the survey
    thread's done() and the uplink start read it, which was a formal data race.
  - **Not changed: two SetTxPower calls on two threads. The overlap predates the survey.** 25 proposed applying
    the pending power inside run() under the survey's end lock. That would not make devourer's one-control-thread
    rule (IRtlDevice.h:110-117) hold. `start_link_quality_thread` calls `SetTxPower(adaptive_tx_power)` on the link's
    run thread, and `nativeSetTxPower` calls it on the Java thread, and both happen without a survey.
    [PROVEN: OpenIPC master WfbngLink.cpp:246 (run → start_link_quality_thread), :536 (SetTxPower in it), :568
    (SetTxPower in nativeSetTxPower); same lines in the fork's master]. The fix is one control lock around every
    device control call in WfbngLink. That is a separate item, and not survey-specific.
  - Tests: host 90/90; `assembleDebug` builds (APK md5 176588d6, not installed).
- **Device control lock (2026-10-01, 66's priority after 25's finding; branch devctl):**
  - Every control-plane call to the RTL in WfbngLink now goes through `DeviceControl.h` (`devctl`, one mutex):
    InitWrite, GetSelectedChannel, the survey's SetMonitorChannel / FastRetune / GetRxEnergy, and SetTxPower from
    done(), from the uplink start and from nativeSetTxPower. This covers the run thread, the survey thread and the
    JNI threads.
  - **A lock, not a control-thread queue:** devourer ties nothing to a thread's identity (the only `thread_local` is
    log scratch, Event.h:233), and its contract asks for sequencing (IRtlDevice.h:110-117). A queue would make
    nativeSetTxPower asynchronous and add a thread.
  - The lock is held only around the one device call and is always innermost, so it has no ordering with
    thread_mutex or SurveyRunner's locks.
  - Not routed through it:
    - StartRxLoop: it blocks on the run thread;
    - StopRxLoop: the cross-thread stop signal;
    - send_packet: the TX data path. The survey keeps the uplink off while it hops.
  - The survey's `tx_power_pending` stays. Its reason is now semantic (applied after the sweep, before the uplink),
    not safety.
  - Tests (`tests/DeviceControl_test.cpp`, red first):
    - a fake device counts calls inside it at once: 8 threads × 100 mixed control calls give 0 overlaps;
    - a positive control shows the same fake sees overlaps when nothing sequences the calls;
    - a structural scan of WfbngLink.cpp fails on any raw control-plane call. It was red first and listed the 10
      raw calls; its regex is self-checked.
  - Mutants killed: no lock; one lock per method instead of one shared; a raw SetTxPower put back.
  - 20/20 repeats stable. Host 94/94; `assembleDebug` builds (APK md5 27301198, not installed).
  - **After 25's review of 339c72b (F1, F2):**
    - **F1:** release_link's `Stop()` halts TRX DMA and powers the chip down. It is a control-plane call, and it was
      outside the lock: nativeSetTxPower could run concurrently with it.
    - **F2 (older):** nativeSetTxPower looked the device up in `rtl_devices`, an unsynchronised std::map, on the JNI
      thread while run threads inserted and erased. It also fetched the pointer outside any lock, so it could reach
      a destroyed device. One WfbngLink serves every adapter: WfbNgLink.java starts one nativeRun thread per
      UsbDevice.
    - Fix: DeviceControl now owns the devices per fd (`attach` / `detach`), and `rtl_devices` is gone.
      - `detach(fd, stop)` runs Stop() and removes the device under the one lock, then hands the device back.
        release_link destroys it while the USB handle is valid, keeping the 2026-09-27 adapter-lock fix.
      - Every call goes by fd and is a no-op when that fd has no device.
      - StopRxLoop (nativeStop, done(), stopDevice) goes through it for the lifetime. It only sets a flag on every
        devourer generation, e.g. `RtlJaguarDevice.h:97`.
      - `current_fd` is atomic.
    - Tests (7):
      - no call reaches a device after its Stop() while a JNI-like thread keeps calling (50 attach/stop/detach
        rounds);
      - calls for a missing fd are no-ops;
      - devices are per fd, and a throwing Stop() still detaches;
      - the scan now covers WfbngLink.cpp and .hpp, including `Stop` and `StopRxLoop`. It was red first and listed
        4 raw calls.
    - Mutants killed:
      - Stop() outside the lock (10/10 runs caught);
      - no lock;
      - a raw Stop() back in release_link;
      - a missing fd reported as success.
    - 20/20 repeats stable. Host 97/97; `assembleDebug` builds (APK md5 ebe1a623, not installed).
- **Not yet verified** [SPECULATION until a slot]:
  - `FastRetune` / `GetRxEnergy` from the survey thread while the RX loop runs on the RTL8812AU inside the app
    (devourer's own sweep does this on the host, `docs/rx-spectrum-sensing.md:151-157`);
  - the real retune cost and NHM values;
  - the ~30 s blackout end to end.
  - **Headset check:** turn the pref on, relaunch XR with the air on, run a detached capture, then `channel_survey.py`
    on it. Compare with a second survey 5 min later.
