# Health logging in the app: PPXR_EVENT, PPXR_HEALTH, PPXR_STATS (2026-09-29)

Why: on 2026-09-28/29 the user had to tell us what happened in the headset ("video stalled" often, the headset asleep,
loss while walking). The app now writes those facts itself. **Status: built and JVM/host-tested; not yet run on the
headset.**

Keywords: health log, PPXR_EVENT, PPXR_HEALTH, video stalled, HOLD, freeze_until_idr, IDR failed, headset asleep,
session inactive, adapter unplugged, loss burst, fps drop, slot_watch, jurnal de sănătate, blocaj video.

## 1. Where the lines go

| Tag | When | Sinks |
|---|---|---|
| `PPXR_EVENT` | one line per notable event, always on | logcat INFO + `files/ppxr_health.log` |
| `PPXR_HEALTH` | every 10 s, always on | same |
| `PPXR_STATS` | every 2 s while a Stats page is on screen, or always with the `general` pref `stats_log` (slots) | same ([stats-backend.md](stats-backend.md) §6) |

- `files/ppxr_health.log` rotates to `.1` at 1 MB. It survives a logcat ring that has rolled over (devourer logs
  several lines per uplink frame). Read it after a slot:
  `adb -s <quest> exec-out run-as com.openipc.pixelpilot.xr cat files/ppxr_health.log.1 files/ppxr_health.log`.
  [slot_watch.py](../../scripts/quest/slot_watch.py) `report` does this ([slot-watch.md](slot-watch.md)).
- [ab_detached.sh](../../scripts/quest/ab_detached.sh) captures all three tags in its detached logcat. Never stream
  logcat over adb-over-Wi-Fi during a measurement ([uplink-t4-analysis.md](uplink-t4-analysis.md)).

## 2. Line format

`t_mono_ms=<Quest CLOCK_MONOTONIC ms, the clock of the Perfetto traces> t_wall_ms=<epoch ms> code=<UPPER_SNAKE>
level=<INFO|WARN|ALERT> k=v ...`, no spaces inside values, `-` = unknown. The format was agreed with the slot monitor
(pixelpilot-xr-dc). The code is `app/src/main/java/com/openipc/pixelpilot/stats/HealthMonitor.java`, which holds all
thresholds as constants.

**One parser, two users.** [slot_watch.py](../../scripts/quest/slot_watch.py) (23008e7) parses these lines with
`health_log.parse` and adds `health_log.summarize` to its report; its tests import the lines of
`test_health_log.py`. A format change therefore needs `python3 scripts/quest-latch/test_health_log.py` **and**
`python3 scripts/quest/test_slot_watch.py` (25 offline checks) green.

## 3. Event codes

| Code | Level | Fields | Source |
|---|---|---|---|
| `SIGNAL_LOST` | ALERT, or WARN when the pilot has nothing to do (`HOLD`) | `to=<SignalState kind>` `cause=freeze\|decoder\|no_packets\|no_adapter\|wrong_key\|waiting\|stall` `[from=]` | a transition of the state the pilot sees (SignalState, UI tick 250 ms). cause=freeze: FreezeUntilIdr dropped slices in it; decoder: a rebuild/codec switch ≤ 2 s before |
| `SIGNAL_OK` | INFO | `was=` `dur_ms=` `cause=` | back to OK |
| `SWITCH_GAP` / `SWITCH_END` | INFO / INFO | `[from=]` / `dur_ms` `[to=<kind>]` (to= only when the switch ended without video) | SignalState `SWITCHING`: the expected picture gap of a preset switch started from the menu, from the air's accept until video returns (bounded by the air's revert deadline + 10 s, `PresetStatus.expectsGap`). Never a SIGNAL_LOST or a stall; a switch that ends without video starts a normal SIGNAL_LOST (2026-09-29, branch switch-gap) |
| `FREEZE_START` / `FREEZE_END` | WARN / INFO | `dur_ms` `slices` | FreezeUntilIdr's counter grows / stops for ≥ 500 ms |
| `DECODER_REBUILD` | WARN | `n` (cumulative) | DecoderRecovery |
| `CODEC_SWITCH` | INFO | `n` | CodecSwitch (H.264 ↔ H.265) |
| `IDR` / `IDR_FAILED` | INFO / WARN | `ok` `failed` + `refused` `connect_timeout` `reply_timeout` `http_status` `error` (non-zero only); from `e48fef9` also `attempts` (SYNs started) `late` (requests won by attempt ≥ 2) `connected` `connect_ms` (mean over the connected ones) | IdrRequester counters, aggregated ≤ 1 line/s. Per request, logcat tag `IdrRequester`: `PPXR_IDRREQ result= attempts= attempt= connect_ms=` ([connect race](link-envelope.md#frame-fate-2026-09-29-where-the-missing-frames-at-1080p90-go-and-the-lever-that-keeps-them)) |
| `SESSION_INACTIVE` / `SESSION_ACTIVE` | ALERT / INFO | `off_ms` | XR session not visible/focused (headset asleep, OS menu) |
| `ADAPTER_GONE` / `ADAPTER_BACK` | ALERT / INFO | `gone_ms` | the wfb link's adapter running or not |
| `LINK_STATUS` | INFO | `msg` (spaces → `_`) | WfbLinkManager texts, e.g. `link_lost_-_restarting_(1)`; repeats dropped |
| `FPS_LOW` / `FPS_OK` | WARN / INFO | `fps` `median` / `dur_ms` | decoded fps < 70 % of its 10 s median for ≥ 2 s |
| `LOSS_BURST` / `LOSS_END` | WARN / INFO | `holes` / `dur_ms` `peak` | post-FEC holes/s (2 s window) > 20 |

`PPXR_HEALTH` (`code=HEALTH level=INFO`): `win_s fps frozen_pct stalls_min holes idr_ok idr_fail rssiA rssiB snrA
snrB dec_ms kind`. frozen_pct = the share of 250 ms ticks in which slices were frozen; stalls_min = SIGNAL_LOST from
OK per minute (a menu preset switch's gap is not one).

## 4. Reading a capture

`python3 scripts/quest-latch/health_log.py files_ppxr_health.log [--tsv timeline.tsv]`
([health_log.py](../../scripts/quest-latch/health_log.py), test `test_health_log.py`). It prints the duration, the
SIGNAL_LOST count and per minute, causes, time lost, the kinds entered, freeze %, headset-off time, adapter
recoveries, IDR failure reasons, the IDR handshake (`idr_attempts`, `idr_won_late`, `idr_connect_ms_mean`), the
menu preset-switch gaps (`switch_gaps`, `switch_ms`, `switch_ended_without_video`), and the
mean fps / frozen % of the HEALTH lines. It reads the file format and the
logcat format alike.

## 5. Tests

JVM: `HealthMonitorTest` (16: every code, levels, causes, the HEALTH window; a mutation check, where two thresholds
were changed, made two tests fail), `HealthFileSinkTest` (3), `StatsCollectorTest` (snapshot listener). Host:
`DecoderRecovery_test` (counters). Python: `test_health_log.py` (4), `test_stats_log.py` (4).

## 6. Headset check (to do)

With the build installed: unplug and replug the RTL (ADAPTER_GONE/BACK with gone_ms), take the headset off and on
(SESSION_INACTIVE/ACTIVE with off_ms), walk out of range (LOSS_BURST, SIGNAL_LOST to=NO_PACKETS or HOLD), then
`slot_watch.py report` / `health_log.py` on the pulled file.
