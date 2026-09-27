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
| 2 | **Matrix** at 4–5 power levels picked from phase 1 (max, two above the cliff, at the cliff, min) | A = m1b4 (the most robust point, same reference in every trace so deltas compare across levels); m2b4, m2b8, m3b8, m4b8, m4b12, m5b12 (MCS5 only if 3a confirms it) | ~5 min per level | 35 min |
| 3 | **FEC** per level on that level's best state | A = 4/6; 4/5, 8/12 | ~2.5 min per level | 15 min |
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

None yet.
