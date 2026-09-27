# Link operating envelope (W2): TX power × MCS × bitrate × FEC

Quest XR docs: [guide](../xr-quest.md) · [G2G budget](g2g-budget.md) · [real link](real-link.md) · [troubleshooting](troubleshooting.md) · run plan [plan-2026-09-27-optimize.md](plan-2026-09-27-optimize.md)

**Goal.** For the video downlink (air unit → RTL8812AU on the Quest), find which MCS / bitrate / FEC keeps the picture
clean at which link margin, and what each costs in capture → decoded latency. The link margin is emulated by lowering
the air unit's TX power; nothing is moved (Quest on the balcony, air unit indoors, both fixed). Output: the operating
envelope and the policy table the adaptive link (W1 phase 2) will follow. Owner: session pixelpilot-xr-22 (Quest,
analysis); air-unit changes by openipc-…-3a. Runs at the resolution mode chosen by W3.

## Instruments

| What | Where | Source |
|---|---|---|
| capture → frame complete / decoded, spread, loss after FEC (lost/s, %), frames without a decoded mark | [ab_segments.py](../../scripts/quest-latch/ab_segments.py) | app RTP marks `ppxr_rtp_*`, `ppxr_frame_ready` |
| packets received over the air (data + parity), FEC repairs, still lost after FEC, RSSI | [ab_link.py](../../scripts/quest-latch/ab_link.py) | app counters `ppxr_wfb_*` from [WfbStatsTrace.java](../../app/wfbngrtl8812/src/main/java/com/openipc/wfbngrtl8812/WfbStatsTrace.java) (one sample per ~300 ms wfb-ng stats poll) |
| pre-FEC loss = 1 − Quest rx/s ÷ air tx/s | `ab_link.py` | air `tx=` (cumulative wlan0 tx_packets) on every step line; an upper bound, other wlan0 traffic counts as video [INFERRED] |
| air SoC temperature | `ab_link.py` | air `temp=` on every step line |
| Quest thermal status, CPU/SoC/battery °C, battery % | [quest_thermal_log.sh](../../scripts/quest/quest_thermal_log.sh) → `ab_link.py --thermal` | `dumpsys thermalservice`, `dumpsys battery` |

Method as in [slot 3](g2g-budget.md#mcs--bitrate-at-1080p90-measured-in-one-trace-2026-09-27-slot-3): one long Perfetto
trace per run ([ab_long.sh](../../scripts/quest/ab_long.sh)), a timed loop on the air unit, 12 s steps, 2 s guard around
every switch, drift fitted on the reference state A, N = 2 per state, states alternated with A.

## Air loop contract (for openipc-…-3a)

- One line per step, written after the step's last command: `<air epoch> <label> tx=<wlan0 tx_packets> temp=<SoC °C>`;
  the END line carries `tx=` and `temp=` too (it closes the last step's TX rate). Failed commands: `<epoch> ERR …`.
- Labels: `p<power>m<MCS>b<Mbit/s>` plus `f<k><n>` when FEC differs from 4/6, e.g. `p10m4b12`, `p10m4b12f45`.
- All changes hot: MCS with `wfb_tx_cmd set_radio` (all fields resent, `get_radio` before/after), bitrate through
  waybeam's API, FEC with `wfb_setfec`, TX power with the hot mechanism 3a confirms for the 8822EU (to be named with its
  valid range; the video `wfb_tx` is not restarted).
- Order inside a switch: raise capacity before load (TX power, then MCS, then bitrate); lower load before capacity
  (bitrate, then MCS, then power).
- Stop rule: a step whose air SoC temperature keeps rising without levelling, or exceeds the board limit the OpenIPC
  project documents, ends the run; revert to the pre-run state. On the Quest: thermal status ≥ 3 (severe) or battery
  < 30 % ends the run.
- Revert at the end: the pre-run power, MCS, bitrate and FEC (1080p90 / 8000 / MCS2 / 4/6 unless W3 changed the mode).

## Plan

| Phase | What | States | Trace | Est. time |
|---|---|---|---|---|
| 0 | Install a build with `WfbStatsTrace` (built from a clean checkout of HEAD, not the shared working tree); 60 s dry run: counters present, `tx=`/`temp=` parsed | – | 60 s | 15 min |
| 1 | **Power ladder** at MCS2 / 8 Mbit/s: RSSI, pre-FEC loss and loss after FEC vs TX power, to find the cliff | A = max power; 5 levels from max to min, each N = 2 | ~4.5 min | 10 min |
| 2+3 | **Matrix with FEC** at 17 / 12 / 8 dBm (chosen from phase 1, see Results; 5 dBm adds nothing over 8) at the mode W3 picks. On-air rate = bitrate × n/k must fit the MCS: injection carries roughly 60 % of the PHY rate [INFERRED: slot 2 measured ~97 % airtime at 8 Mbit/s, FEC 4/6, MCS2], i.e. ~7.8 / 11.7 / 15.6 / 23 Mbit/s at MCS1/2/3/4. So strong FEC is paired with MCS4, and block length is compared at equal airtime (4/8 vs 8/16) and against 8/12. Longer blocks cover bursts better but wait longer to fill (K = 8 in slot 2 cost ≈ 0 ms at 640×480; K = 12 cost 3–4 ms on the OpenIPC side). | A = `m1b4f46` (6 Mbit/s on air, the most robust point, same reference in every trace so deltas compare across levels); `m2b4f46`, `m2b8f46` (today's default, 12 on air: saturated), `m2b4f48`, `m3b8f46`, `m4b8f46`, `m4b8f48`, `m4b8f816`, `m4b8f812` | ~7 min per level | 25 min |
| 3b | **Adaptive link on/off** at 17 and 8 dBm (air power fixed per run). It is a Quest pref read at start-up, so it runs with [pref_ab.sh](../../scripts/quest/pref_ab.sh) (app restart per step, guard ≥ 10 s), ABBA order ≥ 2× so a time trend cancels. The [slot 3d run](troubleshooting.md#does-the-quests-uplink-hurt-the-video-slot-3d-2026-09-27) found no effect, but a loss trend during the run masked it | on, off | ~4 min per level | 15 min |
| 4 | Analysis, envelope + policy table, docs, commit | – | – | 30 min |

About 75 min on the devices and 105 min in total. Guardian paused and `prox_close` only while a trace runs, restored
after each phase.

**Not in scope:** the Quest RTL's TX power (it only carries the uplink, which W1 owns).

## Output formats

**Envelope** (one row per power level): RSSI · pre-FEC loss at m2b8 · states with ≤ 0.1 % loss after FEC and no frames
without a decoded mark · the fastest of those (Δ capture → decoded vs m1b4) · temperatures.

**Policy table for W1 phase 2** (one row per link-quality band, measured by what the receiver can see: RSSI, FEC
repairs/s, pre-FEC loss): chosen MCS / bitrate / FEC, the switch-down and switch-up thresholds with hysteresis, and
the latency cost at that band.

## Results

**Phase 2: MCS × bitrate × FEC at 640×480 @ 167 fps, 17 / 12 / 8 dBm (2026-09-27 17:36–18:01, Quest on the balcony, air unit indoors).**
- **Method.** One trace per power level ([ab_long.sh](../../scripts/quest/ab_long.sh)), 12 s steps, anchor `m1b2f46` between every state, each state N = 2 in two differently shuffled passes (N = 1 not used). A short extra run `p17b` added `m2b2f48` and `m2b3f46` at 17 dBm. Adaptive-link uplink live (~51 Quest TX/s in every step), W1 tunnel up. Build `cd5fa436`.
- **Air unit.** Every run ended without ERR or reset, at 46–48 °C, and reverted to its pre-run state. `waybeam.json` was byte-identical to its backup after ~100 live bitrate sets.
- **Quest.** Thermal status 0, CPU 54–56 °C (live HAL values), battery 96 %.
- **Step alignment.** `--fit-offset` from packets/frame at 17 and 12 dBm (+0.25 / +0.27 s, within 0.07 s of the clocks). At 8 dBm loss makes packets/frame noisy: the fit moved 0.54 s, so the measured offset (+0.341 s) was used. Both give the same deltas within 0.05 ms.
- **Data.** Per level: latency/loss [p17](data/measurements-2026-09-27-quest2-w2-480-p17.csv) · [p12](data/measurements-2026-09-27-quest2-w2-480-p12.csv) · [p8](data/measurements-2026-09-27-quest2-w2-480-p8.csv) · [p17b](data/measurements-2026-09-27-quest2-w2-480-p17b.csv); link [p17](data/link-2026-09-27-w2-480-p17.csv) · [p12](data/link-2026-09-27-w2-480-p12.csv) · [p8](data/link-2026-09-27-w2-480-p8.csv) · [p17b](data/link-2026-09-27-w2-480-p17b.csv); air step logs [p17](data/steps-2026-09-27-w2-480-p17.txt) · [p12](data/steps-2026-09-27-w2-480-p12.txt) · [p8](data/steps-2026-09-27-w2-480-p8.txt) · [p17b](data/steps-2026-09-27-w2-480-p17b.txt); Quest thermal [p17](data/thermal-2026-09-27-w2-480-p17.csv) · [p12](data/thermal-2026-09-27-w2-480-p12.csv) · [p8](data/thermal-2026-09-27-w2-480-p8.csv) · [p17b](data/thermal-2026-09-27-w2-480-p17b.csv).

Each cell: Δ capture → decoded vs the anchor in the same trace · loss after FEC · frames without a decoded mark (of ~2800 per state; the anchor has ~24 000). "On air" = bitrate × n/k.

| state (on air) | 17 dBm (RSSI 68.5) | 12 dBm (RSSI 64) | 8 dBm (RSSI 54) |
|---|---|---|---|
| `m1b2f46` anchor (3 Mbit/s) | 0 · 0.21 % · 25 (p17b: 0.18 %, 7/7145) | 0 · 0.28 % · 31 | 0 · **0.75 %** · 49 |
| `m2b2f46` (3) | **−0.43 ms** · 0.32 % · 3 | **−0.13 ms** · 0.67 % · 7 | +1.71 · 7.3 % · 43 |
| `m2b2f48` (4) | **−0.10 ms · 0.00 % · 0** (p17b) | – | +1.09 · 3.8 % · 21 |
| `m2b3f46` (4.5) | +0.06 · 0.29 % · 1 (p17b) | – | +2.16 · 8.5 % · 41 |
| `m2b4f46` (6) | +0.72 · 0.47 % · 0 | +1.04 · 1.86 % · 3 | +2.81 · 10.9 % · 38 |
| `m2b4f48` (8) | +1.48 · 0.07 % · 1 | +1.55 · 0.66 % · 2 | +2.39 · 5.8 % · 21 |
| `m3b4f46` (6) | +0.37 · 0.99 % · 1 | +2.42 · 11.9 % · 44 | +2.46 · 13.5 % · 48 |
| `m4b4f46` (6) | +1.40 · 7.1 % · 15 | +1.78 · 10.3 % · 36 | – |
| `m4b4f48` (8) | +0.93 · 3.6 % · 8 | +1.20 · 6.2 % · 28 | – |
| `m4b4f816` (8) | +2.97 · 1.05 % · 3 | +3.24 · 2.85 % · 10 | – |
| `m4b8f46` (12) | +2.85 · 9.2 % · 31 | +3.61 · 12.1 % · 69 | – |

- **Loss before FEC depends on the MCS, not on the power alone** [PROVEN: link data]. At the same RSSI 68.5 it is ~5 % at MCS1–3 and ~15 % at MCS4. At RSSI 64 it is ~7–8 % at MCS1–2 and ~20 % at MCS3/4. At RSSI 54 it is 9 % at MCS1 and ~20 % at MCS2/3. MCS4 is not usable at this distance, and MCS3 only at 17 dBm.
- **Low bitrate is the fastest here too.** `m2b2` is 1.15 ms ahead of `m2b4` at 17 dBm, as slot 2 found at 640×480 (bitrate 2000 = −4.5 ms vs 8000).
- **FEC 4/8 costs almost nothing at low bitrate and removes the residual loss.** At 17 dBm `m2b2f48` loses 0 packets (4/6: 0.32 %) for +0.33 ms. At 8 dBm it halves the loss (7.3 % → 3.8 %).
- **A longer block covers bursts, but costs about 2 ms.** At equal airtime (`m4b4`) 8/16 loses 1.05 % against 3.6 % for 4/8, for +2.0 ms of block fill [PROVEN: data].
- **Latency deltas at 8 dBm are measured on the frames that survived.** Frames that complete through FEC repairs arrive late, so there Δ mostly reflects loss.
- **Picture quality is not assessed.** At 167 fps, 2 Mbit/s is ~12 kbit per frame. Whether that looks acceptable has to be judged by the user in the headset [SPECULATION until then].

**Operating envelope and policy table for the adaptive link (W1 phase 2).** This covers 640×480 @ 167 fps, this geometry and FEC k = 4 unless stated. The band edges are what the receiver can see: RSSI on the app's 0–100 scale and loss before FEC at the current MCS.

| band (receiver view) | alink `score` | seen at | use | expected loss after FEC | Δ latency vs `m1b2f46` |
|---|---|---|---|---|---|
| RSSI ≥ ~68, loss before FEC ≤ ~6 % at MCS2 | ≥ ~1680 | 17 dBm | `m2b2f48` (more picture: `m2b3f46`, `m2b4f46`) | 0 % (0.29 / 0.47 %) | −0.1 ms (+0.1 / +0.7) |
| RSSI ~64, loss before FEC ~8 % at MCS2 | ~1640 | 12 dBm | `m2b2f48` (measured in p12b: 0.24 % vs 0.60 % for `m2b2f46` in the same trace) | 0.24 % | +0.2 ms |
| RSSI ~54, loss before FEC ~20 % at MCS2 | ~1540 | 8 dBm | `m1b2f46` (MCS1) | 0.75 % | 0 |
| worse | < ~1540 | < 8 dBm | nothing at 480p keeps loss < 1 % [INFERRED: phase 1 at 5 dBm ≈ 8 dBm] | – | – |

- **`score` vs the RSSI column.** The adaptive-link message sends `score = map(quality, −1024…1024 → 1000…2000)` in fields 2, 3 and 6 ([WfbngLink.cpp:534,571-579](../../app/wfbngrtl8812/src/main/cpp/WfbngLink.cpp#L534)). The RSSI column here is the app's `avg_rssi` = `map(quality, −1024…1024 → 0…100)` ([WfbngLink.cpp:469](../../app/wfbngrtl8812/src/main/cpp/WfbngLink.cpp#L469)). Both come from the same `quality` = `map(raw RSSI 0…80 → −1024…1024)` ([SignalQualityCalculator.cpp:89](../../app/wfbngrtl8812/src/main/cpp/SignalQualityCalculator.cpp#L89)), so **score = 1000 + 10 × RSSI column** (= 1000 + 12.5 × raw) [PROVEN: code]. Earlier values of ~1850/1800/1675 took the RSSI column for the raw value.
- **Loss before FEC is not in the message.** It carries only FEC repairs/s (field 4) and lost/s (field 5). For now the air unit estimates it from its own `tx_packets` against what the ground reports. Sending the Quest's measured pre-FEC loss from the app is a later improvement.

- Switch **down** one row when loss before FEC at the current MCS passes ~10 % (FEC 4/6 still held 0.3–0.7 % below that and broke at 15–20 %) [INFERRED: from the rows above].
- Switch **up** only when the next row's MCS would see ≤ 6 %. RSSI rises ~4–5 points per row here. Hysteresis and time constants still have to be tested in closed loop in W1 phase 2 [SPECULATION until then].
- **Pending:** the user's picture-quality check at 2–4 Mbit/s.

**Phase 3b: `m2b2f48` at 12 dBm, and adaptive link on/off (2026-09-27 18:04–18:20, 480p167, build `7b8baadb`).**
- **Data.** p12b [latency/loss](data/measurements-2026-09-27-quest2-w2-480-p12b.csv) · [link](data/link-2026-09-27-w2-480-p12b.csv) · [steps](data/steps-2026-09-27-w2-480-p12b.txt) · [thermal](data/thermal-2026-09-27-w2-480-p12b.csv); alink at 17 dBm [latency/loss](data/measurements-2026-09-27-quest2-w2-alink-p17.csv) · [link](data/link-2026-09-27-w2-alink-p17.csv) · [steps](data/steps-2026-09-27-w2-alink-p17.txt) · [thermal](data/thermal-2026-09-27-w2-alink-p17.csv); alink at 8 dBm [latency/loss](data/measurements-2026-09-27-quest2-w2-alink-p8.csv) · [link](data/link-2026-09-27-w2-alink-p8.csv) · [steps](data/steps-2026-09-27-w2-alink-p8.txt) · [thermal](data/thermal-2026-09-27-w2-alink-p8.csv).
- **`m2b2f48` at 12 dBm (p12b, 9 steps, anchor `m1b2f46`).** It lost 0.24 % after FEC at +0.16 ms; `m2b2f46` lost 0.60 % at +0.79 ms. That makes `m2b2f48` the 12 dBm row of the policy (measured now, no longer inferred).
- **Run-to-run spread.** In phase 2's p12 run, `m2b2f46` was −0.13 ms against the anchor; here it is +0.79 ms. Latency differences under ~1 ms between 2 Mbit/s states are not significant across separate traces.
- **Adaptive link on/off.** The pref is read at start-up, so [pref_ab.sh](../../scripts/quest/pref_ab.sh) restarted the app on every step: 30 s steps, 12 s guard, so ~6.6 s measured per step. The air unit held one state. Every step's effective pref was checked through the Quest's uplink injections ([quest_tx_log.sh](../../scripts/quest/quest_tx_log.sh)): ~51/s when on, 0.9/s when off, in every step [PROVEN].
  - **17 dBm, `m2b2f48`, ABBA × 2 (N = 4 each).**
    - With adaptive link on, the Quest received fewer video packets in every step: 536–554/s against 561–568/s off. The ranges do not overlap. FEC repaired 14.5 against 12.3 packets/s [PROVEN].
    - The air unit's mean TX over the hold was 602/s, so loss before FEC was ~9.5 % on against ~6.1 % off [INFERRED: the hold average, not per step].
    - After FEC: 0.06 % against 0 %. Capture → decoded moved +0.10 ms, inside the step-to-step spread (2.8–3.8 ms). **At 17 dBm the uplink costs radio packets but no visible video.**
  - **8 dBm, `m1b2f46`: weak evidence, and the run was disturbed.**
    - My wait loop stopped early on a `RuntimeError` line in the pref_ab log (a pref read-back mismatch, below) and asked the air unit to revert too early. The air unit was on the pre-run state (12 dBm, MCS2, 8 Mbit/s) from air epoch 1790522092.15 to 1790522117.83. It was back on `p8m1b2f46` until 1790522140.16, then on the pre-run state again.
    - Classified on the Quest clock (air + ~0.40 s): steps 0 (on), 1 (off), 2 (off), 3 (on) ran at 8 dBm. Step 3's window ends ~0.3 s into the revert; its rx of 460/s shows 8 dBm. Step 4 is excluded: the power came back inside its window. Steps 5 (off), 6 (off), 7 (on) ran on the pre-run state.
    - **At 8 dBm** (on 0 and 3 against off 1 and 2, ABBA): rx 435 / 461 against 453 / 452 per s. Loss after FEC 1.37 / 0.52 % against 0.25 / 0.68 %. Capture → decoded 3.68 / 3.51 against 2.68 / 2.33 ms, so on is about +1.1 ms. Same direction as at 17 dBm, but N = 2 [INFERRED: weak].
    - **On the pre-run state, 12 dBm, MCS2, 8 Mbit/s, 480p** (off 5 and 6 against on 7, N = 1 for on, not order-balanced): rx 1242 / 1229 against 1147 per s, loss after FEC 1.6 / 2.3 % against 5.5 %. Same direction [SPECULATION: N = 1, and a time trend cannot be ruled out].
  - **Pref read-back mismatch at step 3.** The app was not the cause: it was force-stopped at Quest 1790522073.942 and dead by .010 [PROVEN: logcat], before the write. The step still ran with adaptive link on (51.8/s uplink) although the previous step had written `false`, so the write did land. The harness's read-back came too soon, only ~0.2 s after `adb exec-in … cat >` [INFERRED]. Proposed fix for `quest_adb.write_prefs`: write to a temp file and `mv` it into place, then retry the read-back a few times. Reported to its owner.
- **Conclusion for the policy.** The uplink does not break the link at a good margin, but it takes radio time from the video, and at a weak margin that shows as loss and ~1 ms [INFERRED]. For W1 phase 2 the uplink rate should stay as low as the control loop allows. It is ~50 frames/s today, 10 messages/s with FEC 1/5 ([troubleshooting](troubleshooting.md#does-the-quests-uplink-hurt-the-video-slot-3d-2026-09-27)).
  - **Uplink airtime cut, in code (2026-09-27, not yet measured on the device).** Report rate, uplink FEC and uplink MCS are now prefs, set by [LinkOptions](../../app/src/main/java/com/openipc/pixelpilot/LinkOptions.java) (`LinkOptions.Uplink`, the single source of the defaults): `uplink_rate_hz` 4, `uplink_fec_k`/`uplink_fec_n` 1/3, `uplink_mcs` 0. That makes 4 × 3 = 12 frames/s instead of 10 × 5 = 50, −76 % [PROVEN: arithmetic, `LinkOptionsUplinkTest`]. A report that carries news goes out at once, whatever the rate: a new IDR request code or a changed `fec_change`. The loop checks for news every 20 ms (it was 100 ms), so keyframe requests reach the air unit sooner than before [PROVEN: [UplinkSchedule.h](../../app/wfbngrtl8812/src/main/cpp/UplinkSchedule.h) + host gtests `UplinkSchedule_test.cpp`, 19/19]. The rate applies at once. FEC and MCS apply at the next link start (TX thread arguments in `WfbngLink::run`). Port 160 also carries the tunnel's uplink, so the tunnel gets the same FEC. **Air-side dependency:** alink_air's `stale_ms` (fallback when no report arrives) is 1000 ms today. At 4/s one lost report leaves a 500 ms gap and two leave 750 ms, so `stale_ms` should be ≥ 1500, and the estimator should be re-validated on 4 Hz reports. Both are asked of the alink_air owner; this repo does not change the air unit. Device check: the adaptive range test or the final slot. MCS1 is not the default until the RTL → 8822EU decode at MCS1 is measured [SPECULATION until then].

**Phase 1: power ladder at 1080p90, MCS2, 8 Mbit/s, FEC 4/6 (2026-09-27 16:38, Quest on the balcony, air unit indoors).**
- **Method.** Anchor `p17m2b8`; 12 / 8 / 5 dBm, N = 2 each, 12 s steps. Power rises went up in ≤ 3 dB steps 200 ms apart, so no step jumped +11 dB. The W1 tunnel was up (its TX adds nothing measurable to `tx=`: 2381 vs 2378 packets per 2 s), and the adaptive-link uplink was live.
- **Step alignment.** Power does not change packets per frame, so the measured offset was used: Quest − air = 0.227 − (−0.040) = 0.267 s, ±~40 ms against the 2 s guard.
- **Air unit.** No reboot and no ERR; 54–55 °C throughout; reverted to p12 m2 8000 FEC 4/6.
- **Data.** [latency/loss](data/measurements-2026-09-27-quest2-power-ab.csv) ([ab_segments.py](../../scripts/quest-latch/ab_segments.py)) · [link](data/link-2026-09-27-power.csv) ([ab_link.py](../../scripts/quest-latch/ab_link.py)) · [air step log](data/steps-2026-09-27-power.txt) · [Quest thermal](data/thermal-2026-09-27-power.csv).

| TX power | RSSI (app scale 0–100) | air tx/s | Quest rx/s | loss before FEC | FEC repairs/s | loss after FEC | frames without a decoded mark | Δ capture → decoded |
|---|---|---|---|---|---|---|---|---|
| 17 dBm (anchor) | 68.7 | 1178 | 1096 | 7.0 % | 40 | 1.1 % (8.8/s) | 39 / 5477 | 0 |
| 12 dBm (air default) | 64.0 | 1179 | 1047 | 11.2 % | 62 | 3.5 % (27/s) | 64 / 1644 | +0.7 ms |
| 8 dBm | 54.6 | 1175 | 680 | 42 % | 75 | 32 % (252/s) | 1153 / 1683 | +6.3 ms |
| 5 dBm | 50.8 | 1176 | 630 | 46 % | 69 | 37 % (287/s) | 1365 / 1718 | +7.7 ms |

- **At this distance the link is marginal even at 17 dBm.** It loses 1.1 % after FEC and leaves ~0.7 % of frames without a decoded mark. On the bench in one room the same MCS2/8 Mbit/s lost 0.10 % ([slot 3](g2g-budget.md#mcs--bitrate-at-1080p90-measured-in-one-trace-2026-09-27-slot-3)). The air unit's boot default of 12 dBm loses 3.5 % here [PROVEN: data].
- **The cliff is between 12 and 8 dBm:** 8 and 5 dBm both lose a third of the packets after FEC. FEC 4/6 can repair 2 of every 6 packets, but at 7 % loss before FEC it still misses 1.1 %, so the loss comes in bursts rather than independently [INFERRED: repairs cannot cover losses that cluster in one block].
- **Latency is not what breaks first.** At 17 and 12 dBm capture → decoded moves by < 1 ms. The +6…8 ms at 8/5 dBm is measured on the frames that survived, whose last packets come late or through repairs.
- **The two loss measurements agree.** Loss after FEC counted by wfb-ng (`ab_link`: 8.8 / 27.3 / 252 / 287 per s) matches the RTP sequence gaps (`ab_segments`: 8.8 / 27.2 / 252 / 290 per s) [PROVEN].
- **The air unit's TX rate does not change with power** (1175–1179/s), so every difference is on the radio path.
- **Quest temperatures from this run are not usable.** The logger read `dumpsys thermalservice` "Cached temperatures", which stayed at 68.9 °C for the whole run. It now reads "Current temperatures from HAL", which vary (e.g. 55.0 → 54.7 °C). Thermal status stayed 0 and the battery at 96 %; both are live values. The CPU throttling thresholds from HAL are 90 / 95 / 115 °C (`cpu-1-7-usr`).
- **For phase 2** (matrix): the useful power levels are 17 and 12 dBm (lossy but alive) and 8 dBm (cliff). 5 dBm adds nothing over 8. Because even 17 dBm is not clean, the matrix needs the more robust points too: MCS1 and MCS0, stronger FEC (4/8, 8/16), lower bitrate. Higher power (20/23 dBm) waits for the supply check.

**Phase 1, first attempt (2026-09-27 16:30): aborted, the air unit rebooted on the first step.**
- The loop's first switch was the pre-run 12 dBm → 23 dBm. On the Quest trace ([ab_long](../../scripts/quest/ab_long.sh) `w2p1`, Quest − air ≈ +0.25 s), the stream ran at ~750 RTP packets/s with RSSI 64 until the second the loop started. In that second only 297 packets arrived, and none after that until the air unit had rebooted. There was no gradual degradation first, so the link died within ~0.5 s of the power set [PROVEN: trace, per-second RTP count].
- This was the second air-unit reboot at 23 dBm. A current spike at the +11 dB step browning out the bench supply (DPS-150) and a driver crash in `set txpower` both fit [INFERRED]. What would separate them: the supply's logged state, the kernel log after the reboot, or a stepped climb (12 → 14 → 17 → 20 dBm).
- 20 and 23 dBm are blocked until the supply is checked. Phase 1 continues with 17 dBm as the maximum (anchor `p17m2b8`; 17 / 12 / 8 / 5 dBm).
- PixelPilotXr came back by itself: same process, no crash, 0 fps for ~35 s while the air unit rebooted, then a new wfb session and 74–81 fps [PROVEN: logcat].
- The same trace shows the stale wfb counters: while nothing arrived, `ppxr_wfb_p_all` repeated 24 per poll. [ab_link.py](../../scripts/quest-latch/ab_link.py) zeroes such polls (no RTP since the previous poll). The source fix belongs in `WfbngLink.cpp`: when `should_clear_stats` is still set at a poll, the interval had no packets, so report 0. It is proposed to the owner of that file.
