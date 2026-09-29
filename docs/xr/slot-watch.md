# Slot monitoring: slot_watch.py (air during a slot, Quest between measurements, end-of-slot timeline)

Keywords: monitoring, watcher, alerts, slot watch, air health, reboot detection, wfb drop, IDR rate, fps low,
temperature, Quest asleep, adapter gone, DPS-150 checklist, timeline, monitorizare, alerte, supraveghere slot.

The user asked for monitoring, so that problems no longer have to be reported by the user (2026-09-29, via
pixelpilot-xr-66). [slot_watch.py](../../scripts/quest/slot_watch.py) runs on the PC. The coordinator starts it for a
slot and follows its stdout with Monitor: **one line per alert**, the same line appended to an alerts file.

```
<local ISO time> <LEVEL> <source> <CODE> k=v ...        LEVEL = ALERT | WARN | INFO
2026-09-29T03:14:37.644 ALERT air AIR_UNREACHABLE misses=2
```

Conditions are edge-triggered: one line when a condition starts (or its level rises), and one `INFO <CODE>_OK` when
it ends, so a condition that lasts does not repeat every 5 s.

## Use

```bash
cd scripts/quest
# during the slot (never touches the Quest); Ctrl-C or --duration ends it; exit 1 if any ALERT was raised
python3 slot_watch.py watch --expect channel=157 --expect txpower=17 --alerts out/slot_watch/<slot>/alerts.log
# between measurements only (adb over Wi-Fi); exit 1 if any ALERT
python3 slot_watch.py between --expect guardian_pause=1 --expect prox=CLOSE --alerts out/slot_watch/<slot>/alerts.log
# after the slot: alerts + the app's PPXR_EVENT/PPXR_HEALTH + the air's air_health, one timeline on PC time
python3 slot_watch.py report --alerts out/slot_watch/<slot>/alerts.log      # writes alerts-report.md next to it
```

`--expect` names the planned value. A planned key that differs is an ALERT. An unplanned change between two polls
(MCS, FEC, channel, TX power, bitrate, configured fps) is a WARN with `was=` / `now=`, because alink and vmoded
change some of them on purpose. Thresholds are flags (`--idr-max`, `--fps-min`, `--temp-warn`, `--temp-alert`,
`--storage-min-mb`, `--battery-min`); `--status-every 12` adds an `INFO air AIR_STATUS` line every minute so the
watcher is visibly alive.

## The air (`watch`)

Every `--interval` (5 s) one read-only `ssh air sh -s` runs [air_probe.sh](../../scripts/quest/air_probe.sh), which is
sent on stdin, so nothing is quoted through a chain of shells. The radio, `iw` and `config.json` reads come only every
`--slow-every` polls (30 s), to spare CPU0 next to the encoder. No waybeam `set`, no register access.

| Code | Level | Condition (default) | Source on the air |
|---|---|---|---|
| `AIR_REBOOT` | ALERT | `boot_id` changed, or uptime went back | `/proc/sys/kernel/random/boot_id`, `/proc/uptime` |
| `AIR_UNREACHABLE` | ALERT | 2 polls in a row failed (ssh timeout 3 s + 10 s) | — |
| `WFB_DROP` | ALERT | wfb_tx `p_drop` > 0 in the lines added since the last poll | `/tmp/wfbtx.log` PKT lines, field 6 (wfb-ng `tx.cpp:826`, as `bitrate_grid.sh`) |
| `IDR_RATE` | WARN | (honoured + dropped) key-frame requests > 2/s | `GET /api/v1/idr/stats` |
| `AIR_FPS_LOW` | ALERT | waybeam fps < 97.5 % of the configured fps (90 → 87.75; 167 → 162.8) | last `[verbose] … fps … kbps` line of `/tmp/waybeam.log`; `config.json` `fps` |
| `AIR_TEMP` | WARN ≥ 60 °C, ALERT ≥ 70 °C | the `TEMP_SKIP` / `TEMP_STOP` of `bitrate_grid.sh` | `/sys/devices/virtual/mstar/msys/TEMP_R` |
| `AIR_CHANNEL`, `AIR_TXPOWER`, `AIR_MCS`, `AIR_FEC`, `AIR_BITRATE`, `AIR_CFG_FPS` | ALERT vs `--expect`, WARN on an unplanned change | — | `iw dev wlan0 info`; `wfb_tx_cmd 9000 get_radio` / `get_fec`; `config.json` |
| `AIR_BCN_550` | ALERT | the last bcn_off readback is not `0x10` (fix (a) off) | last line of `/tmp/linkmode-bcn.log`, written by `linkmode-air.sh` on every switch |

**0x550 is not read from the register.** A read writes the address into `read_reg` first, which races linkmode's own
`bcn_off` and any second sampler (openipc-…-40, 2026-09-29). The watcher reads bcn_off's log line instead.
air_health will be the one sampler of the register between switches.

Every poll also records `clock_offset_s` = PC time − air time (the air's `date +%s`), shown in `AIR_STATUS`.

## The Quest (`between`)

adb over Wi-Fi while the link measures costs the RTL packets (the U1 run, [troubleshooting](troubleshooting.md)), so
`watch` never uses adb. `between` is one adb shell call, run only between measurements:

| Code | Level | Condition | Read |
|---|---|---|---|
| `QUEST_ASLEEP` | ALERT | `mWakefulness` ≠ Awake | `dumpsys power` |
| `QUEST_XR_NOT_RUNNING` | ALERT | no pid for `com.openipc.pixelpilot.xr` | `pidof` |
| `QUEST_NO_ADAPTER` | ALERT | no `0bda:8812` among the USB host devices | `dumpsys usb` (IDs are decimal there: `vendor_id=3034 product_id=34834`; `/sys/bus/usb` is not readable from the adb shell) |
| `QUEST_GUARDIAN` | WARN | `debug.oculus.guardian_pause` ≠ `--expect guardian_pause` | `getprop` |
| `QUEST_PROX` | WARN | `Virtual proximity state` ≠ `--expect prox` (`CLOSE` after `prox_close`) | `dumpsys vrpowermanager` |
| `QUEST_STORAGE` | WARN | < 2048 MB free on `/data` | `df -k /data` |
| `QUEST_BATTERY` | WARN | < 30 % (the stop rule in [link-envelope.md](link-envelope.md#air-loop-contract-for-openipc--3a)) | `dumpsys battery` |

A pass without problems prints `INFO quest QUEST_OK` with every value read.

## End-of-slot report (`report`)

`report` merges the slot's alerts with two logs. It pulls them after the slot, when adb is allowed again:

- The app's `PPXR_EVENT` / `PPXR_HEALTH` lines (pixelpilot-xr-36, build db2142a / APK 579305ee, codes in [health-logging.md](health-logging.md)). They are parsed by 36's [health_log.py](../../scripts/quest-latch/health_log.py) (`parse`, the one parser of the format; it also reads a detached logcat capture), and the report adds its `summarize` table (stalls per minute, causes, freeze %, IDR failure reasons).
  - Format: `t_mono_ms=… t_wall_ms=… code=… level=INFO|WARN|ALERT k=v …`.
  - Read from `files/ppxr_health.log(.1)` with `adb exec-out run-as com.openipc.pixelpilot.xr cat`, because at the end of a long slot `logcat -d` can have lost them.
  - `t_wall_ms` is the Quest's clock, corrected by the Quest − PC offset measured at the pull.
- The air's `air_health` log (openipc-…-40; not deployed yet): `/tmp/air_health.log(.1)`, 2 s lines plus `EV` event lines, epoch `t=`. It is corrected by the air − PC offset.
  - The line schema is provisional until -40 sends the final one. The parser takes `t=` / `epoch=` / `ts=` and `code=`.

The report (`alerts-report.md`) has a count per source/code/level and the timeline. Periodic lines (`HEALTH`, the
air's 2 s lines, `AIR_STATUS`) are left out unless `--periodic`.

**When air_health is deployed** it becomes the single air sampler (-40's request: two samplers would run the same
`wfb_tx_cmd` / `iw` / `wget` calls on CPU0). Then `watch` should read the new lines of `/tmp/air_health.log` instead of
running its own probe. That switch is open until the schema is final.

## DPS-150 checklist (the coordinator, with the dps150 MCP)

Only one process can hold the DPS-150's port (COM5), so slot_watch never opens it. The coordinator checks:

1. Before `output_off`: `sync` on the air ([air-unit power rule](HANDOFF.md)).
2. After `output_off`: `read_state` must show **0 A** (output really off). A running `watch` shows `AIR_UNREACHABLE`
   ~10 s later; that is expected.
3. After `output_on`: the air must come back with a **fresh boot**, i.e. `AIR_UNREACHABLE_OK` followed by `AIR_REBOOT`
   (new `boot_id`, small uptime) in the watcher.
4. After a power-on, vmoded does not start by itself (it is started by hand), and `/tmp/linkmode-bcn.log` must show
   `-> 0x10` again (`AIR_BCN_550` stays quiet).

## Verification (2026-09-29)

- [test_slot_watch.py](../../scripts/quest/test_slot_watch.py): 25 offline checks (including 36's real-format lines from `test_health_log.py`, file and logcat). They cover the probe parser, every
  air rule including edge-triggering and recovery, the Quest parsers and rules, the alert line round trip and the
  timeline window/offsets. Run `python3 test_slot_watch.py`.
  - Four mutants were killed: drop `>` → `>=`, the uptime rule removed, the IDR threshold disabled, the edge trigger removed.
- The parser fixtures are **real captures**, taken in a window opened by the coordinator (2026-09-29 ~03:10, no measurement running) [PROVEN]:
  - Air (one `ssh air sh -s` of `air_probe.sh`, rc 0; HD 16 Mbit/s, m7, FEC 4/8, alink off): `90 fps | 16243 kbps`, idr/stats `{"honored":432,"dropped":26}`, `mcs_index=7`, `k=4 n=8`, `channel 157 … txpower 17.00 dBm`, `bcn_off 0x550 0x18 -> 0x10`, temp 46.
  - Quest (in-slot state): `mWakefulness=Awake`, `Virtual proximity state: CLOSE`, `State: HEADSET_MOUNTED`, `guardian_pause` 1, `vendor_id=3034 product_id=34834`, `df` and battery.
- Dry run with an unreachable host: `WATCH_START`, then `ALERT AIR_UNREACHABLE misses=2` after the second poll, then `WATCH_END`, exit 1; `report --no-quest --no-air` wrote the table.
- **Not yet run live:** a full `watch` against the air, and the one-call `between` script on the headset. Both are for the next slot window.
