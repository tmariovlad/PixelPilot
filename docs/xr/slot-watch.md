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
# during the slot (never touches the Quest); Ctrl-C or --duration ends it; exit 1 if any ALERT was raised.
# With air_health.sh running on the air (-40's §6: scp + `sh /tmp/air_health.sh start`), --air-source health reads
# its ring instead of probing; the default auto does so when the ring is live.
python3 slot_watch.py watch --expect channel=157 --expect txpower=17 --alerts out/slot_watch/<slot>/alerts.log
# between measurements only (adb over Wi-Fi); exit 1 if any ALERT
python3 slot_watch.py between --expect guardian_pause=1 --expect prox=CLOSE --alerts out/slot_watch/<slot>/alerts.log
# after the slot: alerts + the app's PPXR_EVENT/PPXR_HEALTH + the air's air_health, one timeline on PC time
python3 slot_watch.py report --alerts out/slot_watch/<slot>/alerts.log      # writes alerts-report.md next to it
```

`--expect` names the planned value. A planned key that differs is an ALERT. An unplanned change between two polls
(MCS, FEC, channel, TX power, bitrate, configured fps) is a WARN with `was=` / `now=`, because alink and vmoded
change some of them on purpose.

`--expect-until EPOCH|+SECONDS` stops enforcing `--expect` at that moment, so the planned revert at the end of a run
(e.g. back to race at 12 dBm) is a WARN, not an ALERT. Pass the run's end, or stop `watch` at the script's END with
`--duration`.

Thresholds are flags (`--idr-max`, `--idr-window`, `--fps-min`, `--temp-warn`, `--temp-alert`, `--storage-min-mb`,
`--battery-min`). `--status-every 12` adds an `INFO air AIR_STATUS` line every minute so the watcher is visibly alive.
Just before `WATCH_END`, `INFO watch AIR_CLOCK pc_minus_air_s=… err_s=…` gives the slot's PC − air offset (the clock
bound below, `-` if no poll answered). Use that value when joining air and Quest data by the second.

## The air (`watch`)

Every `--interval` (5 s) one read-only `ssh air sh -s` runs a script sent on stdin, so nothing is quoted through a
chain of shells. No waybeam `set`, no register access. `--air-source` picks what that script reads:

- **`health`: air_health.sh's ring log** (openipc-…-40, OpenIPC `444d017`, `repos/tasks/air-health-2026-09-29/`).
  - [air_tail.sh](../../scripts/quest/air_tail.sh) prints the air's `date`, `/proc/uptime` and `boot_id`, then the
    last 15 lines of `/tmp/air_health.log.1` and of `/tmp/air_health.log`.
  - The watcher keeps only the lines it has not seen (by boot, uptime and the exact line), so air_health is the one
    sampler on the air. Two samplers would run the same `wfb_tx_cmd` / `iw` / `wget` calls on CPU0, and two
    `read_reg` users race.
  - The lines are parsed by -40's [parse_air_health.py](../../../openipc-low-latency-and-others-video/repos/tasks/air-health-2026-09-29/parse_air_health.py)
    (`parse_line`, `AH_KEYS`, `EV_KEYS`, `summarize`: the one parser of the format), found through `AIR_HEALTH_DIR`
    in `quest_env.py`. Since OpenIPC `2eb1567` / `5650729` the parser keeps `boot` as text (before, an all-digit
    prefix such as `00123456` became a number, found here), and a `boot=NA` or empty boot is None.
  - Each line is placed on PC time by its own uptime: mid-call − (the poll's uptime − the line's uptime), to about
    10 ms, with no clock offset needed.
  - The first poll is only a baseline: its last AH line, and no replay of older events.
  - The only extra read on the air is waybeam's configured bitrate/fps from `config.json` every 30 s, which
    air_health leaves out.
- **`probe`**: [air_probe.sh](../../scripts/quest/air_probe.sh), the fallback while air_health is not running. The
  radio, `iw` and `config.json` reads come every `--slow-every` polls (30 s), to spare CPU0 next to the encoder.
- **`auto`** (the default) takes `health` when the ring has a line of the current boot that is at most 10 s old, and
  `probe` otherwise. It decides once, at the start. `WATCH_START` says which it took (`air_source=`).

Both sources feed the same rules ([AirWatch](../../scripts/quest/slot_watch.py)); `sample_from_ah` maps an AH line
onto the probe's keys.

| Code | Level | Condition (default) | probe reads | air_health keys |
|---|---|---|---|---|
| `AIR_REBOOT` | ALERT | `boot_id` changed, or uptime went back | `/proc/sys/kernel/random/boot_id`, `/proc/uptime` | the poll's `boot_id` (seen even while the logger is down); `boot`, `up` |
| `AIR_UNREACHABLE` | ALERT | 2 polls in a row failed (ssh timeout 3 s + 10 s) | — | — |
| `WFB_DROP` | ALERT | input drops > 0 | wfb_tx `p_drop` in the `/tmp/wfbtx.log` PKT lines since the last poll (field 6, wfb-ng `tx.cpp:826`) | `wfb_drop` + `udp_ddrops` (the socket's drops) on `sa=0` lines only, with `idr_dh` and the per-second `wfb_ps` in the alert: RXQ_DROP's condition |
| `IDR_RATE` | WARN | (honoured + dropped) key-frame requests > 2/s over the last 30 s; clears below 1.5/s (hysteresis) | `GET /api/v1/idr/stats` | `idr_h` + `idr_d` totals |
| `AIR_FPS_LOW` | ALERT | waybeam fps < 97.5 % of the configured fps (90 → 87.75; 167 → 162.8) | last `[verbose] … fps … kbps` line of `/tmp/waybeam.log`; `config.json` `fps` | `fps`; `config.json` from air_tail.sh |
| `AIR_TEMP` | WARN ≥ 60 °C, ALERT ≥ 70 °C | the `TEMP_SKIP` / `TEMP_STOP` of `bitrate_grid.sh` | `/sys/devices/virtual/mstar/msys/TEMP_R` | `temp` |
| `AIR_CHANNEL`, `AIR_TXPOWER`, `AIR_MCS`, `AIR_FEC`, `AIR_BITRATE`, `AIR_CFG_FPS` | ALERT vs `--expect`, WARN on an unplanned change | — | `iw dev wlan0 info`; `wfb_tx_cmd 9000 get_radio` / `get_fec`; `config.json` | `ch`, `txpwr`, `mcs`, `fec_k`/`fec_n`; `config.json` |
| `AIR_BCN_550` | ALERT | the last bcn_off readback is not `0x10` (fix (a) off) | last line of `/tmp/linkmode-bcn.log`, written by `linkmode-air.sh` on every switch | `bcn` (the same log line) |
| `AIR_HEALTH_STALE` | ALERT | health source: no line of this boot newer than 10 s (`reason=lag`), a ring from an earlier boot (`reason=boot`: not restarted after a reboot), or no ring (`reason=nolog`) | — | `up`, `boot` |
| `AIR_HEALTH_GAP` | WARN | health source: `seq` jumped, so lines were missed (a poll > 30 s late, or air_health paused below its `/tmp` floor, `TMP_LOW`) | — | `seq` |
| air_health's events | the air's level | `AH_START`, `AH_STOP`, `WB_PID`, `WFBTX_PID`, `ALINK`, `VMODED`, `REG550`, `REG550_OK`, `TMP_LOW`, `TMP_OK`, passed on as `air_health <CODE>` with their details | — | `EV … code=` |

air_health's `THERMAL`, `CHAN`, `TXPWR` and `RXQ_DROP` are not passed on, because `AIR_TEMP`, `AIR_CHANNEL` /
`AIR_TXPOWER` and `WFB_DROP` report the same thing. `ROTATE` is not passed on either.

**0x550 is not read from the register by the watcher.** A read writes the address into `read_reg` first, which races
linkmode's own `bcn_off` and any second sampler (openipc-…-40, 2026-09-29). The watcher reads bcn_off's log line.
air_health is the one sampler of the register (`reg550` every 30 s, skipped while linkmode runs). Its `REG550` /
`REG550_OK` events reach the alerts through the health source.

**Clock offset.** `AIR_STATUS` carries `clock_offset_s` (PC time − air time) and `clock_err_s` (its half-width).
- The air's `date +%s` has whole seconds only, and the ssh call takes 0.3–1.5 s. The first version subtracted `date`
  from the PC time after the call returned, which gave a 1.14 → 2.15 → 1.27 s sawtooth in the live run, while the
  real offset was constant.
- Now ([AirClock](../../scripts/quest/slot_watch.py)):
  - The probe prints `date` and `/proc/uptime` (10 ms) together, and floor(uptime + B) = date. Every poll bounds
    B = air epoch − uptime to 1 s; intersected over the polls, it narrows to ~10 ms, with no busy wait on the air.
  - The air's sample happens between the PC's start and end of the ssh call, which bounds the offset NTP-style.
    Intersected over the polls, the bound narrows to the fastest calls.
  - A reboot, or an empty intersection (a clock step), starts over.
- Offline, simulated calls with 0.05–1.5 s latency converge within 0.1 s of the true offset and stay flat
  (`test_the_clock_offset_converges_instead_of_a_sawtooth`).
- **Live (2026-09-29, three runs of c3f996f, one air boot)** [PROVEN: `scripts/quest/out/slot_watch/{rmem,rmemrig,rmem1m}/alerts.log`, gitignored; the `AIR_STATUS` lines]:
  - Converged values: rmem 0.052 ± 0.184 s, rmemrig 0.047–0.048 ± 0.162 s, rmem1m 0.077–0.086 ± 0.163 s. The bounds overlap, and the offset stays flat within ± 0.04 s across 03:58–04:33.
  - The uptime ran without a break, 8416 → 12121 s, so there was no reboot.
  - The "PC − air = 0.749 s" used in that night's data headers and audits lies outside every bound.
  - The run's own `epoch − uptime` constant (1790633249.73, used for the rmemrig air-drop seconds) gives PC(after the call) − air(at the sample) = 0.32–0.37 s. The sample comes before the call returns, so this bounds PC − air ≤ 0.32 s, which also rules out 0.749 [INFERRED].
  - Where 0.749 came from: the coordinator's `clk_off.py` took half the round trip of a whole paramiko exec call as the offset. That call's two directions are not symmetric [PROVEN: pixelpilot-xr-66, 2026-09-29, who corrected its six air logs and asked the analysts to redo the 1 s joins].
  - The sidecar's SYNC can't settle it on its own: its air times t2/t3 are CLOCK_MONOTONIC ([stats-backend.md](stats-backend.md), "Clocks"), so its offset becomes a wall-clock one only through the air's `epoch − uptime`.
  - The air runs `ntpd -n` (pid 801) [PROVEN: pixelpilot-xr-66's read on the air, 2026-09-29], so its wall clock is NTP-disciplined like the PC's, and an offset of ~0.05–0.09 s is what to expect.

## The Quest (`between`)

adb over Wi-Fi while the link measures costs the RTL packets (the U1 run, [troubleshooting](troubleshooting.md)), so
`watch` never uses adb. `between` is one adb shell call, run only between measurements:

| Code | Level | Condition | Read |
|---|---|---|---|
| `QUEST_ASLEEP` | ALERT | `mWakefulness` ≠ Awake | `dumpsys power` |
| `QUEST_XR_NOT_RUNNING` | ALERT | no pid for `com.openipc.pixelpilot.xr` | `pidof` |
| `QUEST_NO_ADAPTER` | ALERT | no `0bda:8812` among the attached USB devices | `dumpsys usb`, its `host_manager` block only: `settings_manager` holds the XR app's USB device filters, which list `0bda:8812` whether or not it is plugged in (IDs are decimal there: `vendor_id=3034 product_id=34834`; `/sys/bus/usb` is not readable from the adb shell) |
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
- The air's `air_health` ring (openipc-…-40, final schema in its `00-DESIGN-air-health.md` §2): `/tmp/air_health.log.1` and `/tmp/air_health.log`, an `AH` line every 2 s plus `EV … code=` event lines, read with one `cat` over ssh after the slot.
  - Parsed by -40's `parse_air_health.py` (see [the air](#the-air-watch)).
  - Each line is placed on PC time by its uptime against an anchor: the air's `/proc/uptime`, read in a second, short call, at that call's middle. That call is separate because copying a few MB takes long enough to blur a time taken with it. /tmp is a tmpfs, so every line in the ring belongs to the current boot.
  - The events that `watch` passed on (`air_health <CODE>`) are dropped from the alerts side when the ring is there, so none is listed twice.
  - The report adds -40's `summarize` table over the lines in the slot window (stats, window sums, gaps, `reg550` / `bcn` values seen, events per code), without its event list, which the timeline already has.

The report (`alerts-report.md`) has a count per source/code/level and the timeline. Periodic lines (`HEALTH`, the
air's `AH` lines, `AIR_STATUS`) are left out unless `--periodic`. An `AH` row keeps a short key list
(`REPORT_AH_KEYS`: temp, cpu0, fps, kbps, mcs, FEC, channel, power, `sa`, drops, `idr_dh`, `bcn`, `reg550`).

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

- [test_slot_watch.py](../../scripts/quest/test_slot_watch.py): 31 offline checks before the air_health source (53 with it, AIR_CLOCK, the USB scope and the exit-0 scripts) (including 36's real-format lines from `test_health_log.py`, file and logcat). They cover the probe parser, every
  air rule including edge-triggering and recovery, the Quest parsers and rules, the alert line round trip, the
  timeline window/offsets, the clock bound, the IDR window, and `--expect-until`. Run `python3 test_slot_watch.py`.
  - Seven mutants were killed: drop `>` → `>=`, the uptime rule removed, the IDR threshold disabled, the edge trigger removed, the IDR hysteresis removed, the offset bound replaced by the old post-call estimate, and `--expect-until` ignored.
- The parser fixtures are **real captures**, taken in a window opened by the coordinator (2026-09-29 ~03:10, no measurement running) [PROVEN]:
  - Air (one `ssh air sh -s` of `air_probe.sh`, rc 0; HD 16 Mbit/s, m7, FEC 4/8, alink off): `90 fps | 16243 kbps`, idr/stats `{"honored":432,"dropped":26}`, `mcs_index=7`, `k=4 n=8`, `channel 157 … txpower 17.00 dBm`, `bcn_off 0x550 0x18 -> 0x10`, temp 46.
  - Quest (in-slot state): `mWakefulness=Awake`, `Virtual proximity state: CLOSE`, `State: HEADSET_MOUNTED`, `guardian_pause` 1, `vendor_id=3034 product_id=34834`, `df` and battery.
- Dry run with an unreachable host: `WATCH_START`, then `ALERT AIR_UNREACHABLE misses=2` after the second poll, then `WATCH_END`, exit 1; `report --no-quest --no-air` wrote the table.
- **Live run, HD MCS4 redo (2026-09-29 03:27–03:37, pixelpilot-xr-66; 120 polls, `--expect channel=157 --expect txpower=17`)** [PROVEN: `scripts/quest/out/slot_watch/hdredo/alerts.log`, gitignored; its `alerts-report.md`, 31 rows]. It caught:
  - `AIR_TXPOWER` 12 vs 17 before the setup;
  - a real `WFB_DROP drop=106` during the setup (an ordering mistake in the run, cleared 5 s later);
  - every planned MCS / FEC / bitrate change, as a WARN;
  - `IDR_RATE` > 2/s repeatedly on `m4b16f46` (real, with the weaker FEC).
- It also exposed three flaws, fixed afterwards (the second `IDR_RATE` state and the clock rows above):
  - the clock sawtooth;
  - the planned revert raised a false ALERT (now `--expect-until`);
  - `IDR_RATE` flapped WARN ↔ OK 12 times in 10 min with a 5 s delta (now a 30 s window with hysteresis).
- **air_health source (2026-09-29, offline)** [PROVEN: `python3 test_slot_watch.py` → 50 `ok`, exit 0]. 19 checks, built on AH lines made from -40's `AH_KEYS` (its test checks that list against the script's emit line). They cover:
  - the AH → sample mapping, and window sums counted only on `sa=0` lines;
  - the boot id kept as text, including `""` and `NA`;
  - the baseline and deduplication, and line times from uptime;
  - covered events not repeated;
  - stale (`lag` / `boot` / `nolog`) and its clearing;
  - one `AIR_REBOOT` when the logger restarts after a reboot;
  - no false reboot from lines written between the poll's uptime read and its tail;
  - the `seq` gap, and an IDR storm seen from the totals;
  - the clock from the poll head;
  - the tail parser, and the LF-only script;
  - `auto`;
  - the report's anchor, the event deduplication and the air summary.
  - 12 mutants were killed, each checked to apply to exactly one place. One mutant (the uptime reset on a reboot) first survived: the test's old boot had a smaller uptime than the new one. The test now uses a 500 s old boot, and that mutant dies.
  - `report --no-quest --no-air` on the hdredo alerts still writes its 31 rows.
- **`between` live (2026-09-29 04:34, window from pixelpilot-xr-66 between rmem1m and (B), ~1 s)** [PROVEN: `scripts/quest/out/slot_watch/between-preB/alerts.log` and `dumpsys-usb.txt`, gitignored]:
  - `QUEST_OK`, rc 0: Awake, XR app pid 32499, `guardian_pause=1`, prox CLOSE, HEADSET_MOUNTED, 156839 MB free, battery 100.
  - It exposed a flaw, since fixed: the USB check listed 49 IDs, because the XR app's device filters under `settings_manager` were counted as attached devices. `QUEST_NO_ADAPTER` could never have fired.
  - The on-device part now sends the whole `dumpsys usb` (one call, ~1000 lines), and `parse_usb_ids` reads only `host_manager`. On the real capture that gives `['0bda:8812']`.
  - The test, built on the capture's structure, was red before the fix: plugged / unplugged / no `host_manager` block.
- **First live run on the air_health ring: slot (B), 2026-09-29 04:35–04:40** (pixelpilot-xr-66, `--air-source auto`) [PROVEN: `scripts/quest/out/slot_watch/B/`, gitignored: `alerts.log`, `alerts-report.md`, the pulled ring `air_health-ring.log`]:
  - `auto` took the ring (`air_source=health`).
  - Every one of the 203 ring lines passes -40's `parse_air_health.py --check` (184 AH + 19 EV).
  - The report has 27 rows: 161 ring lines fall in the slot; one boot, a 2.0 s period, no gaps; `reg550` and `bcn` stay `0x10`.
  - `AIR_CLOCK pc_minus_air_s=-0.004 err_s=0.331`, which agrees with the three probe runs above.
  - The alerts:
    - `AIR_FPS_LOW` 86 at waybeam's start, cleared after 10 s;
    - after `expect_until`, the planned revert: MCS/TX power `WARN`, waybeam and wfb_tx restarts passed on as `air_health WB_PID` / `WFBTX_PID`;
    - `WFB_DROP` 4 and 10 at those restarts, where RXQ_DROP shows the UDP socket drops.
  - It exposed a flaw, since fixed: the report's pull ran `cat` of both ring files. Before the first rotation `.log.1` does not exist, so `cat` exited 1 and the pull returned 0 lines. `air_tail.sh` had the same exposure with a missing log. Both scripts now end with `exit 0`, and a test runs them under a local `sh` with no ring files (red before).
  - It also exposed an air_health bug: `rmem_def=1 rmem_max=1` on all 184 lines. -40 fixed it in OpenIPC `e0e4c76`, and air_health.sh is now md5 `ef736a43`.
    - Cause: an integer sysctl returns EOF at any offset > 0, and busybox `read` reads one byte at a time, so only the first digit came through.
    - The fix reads both files with one `cat`. The regression test T15 runs against a real /proc/sys.
    - The parser is unchanged, and the watcher does not use these fields. Treat the `rmem_*` values in the (B) ring as invalid.
- **Not yet run live:** `report` with the app's real health lines (APK 579305ee; the (B) report ran with `--no-quest`, because the next run was measuring and adb over Wi-Fi is not allowed then).
