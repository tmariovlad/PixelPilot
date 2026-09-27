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
| 2 | **Matrix** at 17 / 12 / 8 dBm (chosen from phase 1, see Results; 5 dBm adds nothing over 8) at the mode W3 picks | A = `m1b4f46` (the most robust point, same reference in every trace so deltas compare across levels); m2b4, m2b8, m2b8f48, m1b4f48, m3b8, m4b8 (MCS5 only if 3a confirms it) | ~5 min per level | 25 min |
| 3 | **FEC block length** per level on that level's best state: longer blocks cover bursts better but wait longer to fill (8/12 cost ≈ 0 ms at 640×480 in [slot 2](g2g-budget.md#air-unit-levers-measured-in-one-trace-2026-09-27-slot-2)) | A = 4/8; 8/12, 8/16 (and 4/6 for reference) | ~2.5 min per level | 15 min |
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
