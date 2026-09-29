# Quest 2 test and measurement scripts

Scripts behind the Quest 2 measurements in [docs/xr-quest.md](../../docs/xr-quest.md) (and the topic pages under
[docs/xr/](../../docs/xr/)): decoder-lever tests over a Wi-Fi RTP replay, compositor / phase-lock runs, and the
real link (RTL8812AU on the Quest's USB-C + an OpenIPC air unit on wfb-ng). The compositor analysis tools live
next door in [../quest-latch/](../quest-latch/) (`latch_analyze.py`, `calibrate_latch.py`, `transport_analyze.py`,
`rtp_pace.py`, `compositor.pbtx`).

## Configuration: one place

[quest_env.py](quest_env.py) holds every machine-specific value; bash scripts source [quest_env.sh](quest_env.sh),
which runs `python3 quest_env.py --sh`, so both read the same values. Override with environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `ADB` | `C:\Users\vlad_\AppData\Local\Android\Sdk\platform-tools\adb.exe` | adb executable (Windows or `/c/...` path) |
| `QUEST` | `192.168.100.114:5555` | headset adb serial (Wi-Fi ADB); its IP is where streams are sent |
| `PC_IP` | `192.168.100.213` | this PC on the home LAN (phase reports come back here) |
| `WFB_CHANNEL` | `157` | air unit's wfb-ng channel (real link) |
| `GS_KEY` | `scripts/quest/keys/gs.key` | gs.key that pairs with the air unit's drone.key |
| `AIR_IP` / `AIR_SSID` / `WLAN_IF` | `192.168.0.1` / `OpenIPC` / `Wi-Fi 2` | the air unit's AP as seen from the PC |
| `QUEST_STREAMS` / `QUEST_OUT` | `streams/` / `out/` | recorded streams / run outputs |

Fixed: package `com.openipc.pixelpilot.xr`, XR activity `com.openipc.pixelpilot.XrVideoActivity`, 2D activity
`com.openipc.pixelpilot.VideoActivity`, video port 5600, phase-report port 5610. Print them: `python3 quest_env.py`.

`streams/`, `out/`, `keys/`, `*.rtp`, `*.key` and `__pycache__/` are gitignored.

## Prerequisites

- **Headset:** Quest 2 in developer mode with Wi-Fi ADB (`adb tcpip 5555` over USB once, then
  `adb connect <quest-ip>:5555`). A **debuggable** PixelPilotXr build installed (the scripts use `run-as` to write
  `shared_prefs/general.xml`), started once so a `gs.key` pref exists (`set_prefs()` keeps it and drops everything else).
- **PC (Git Bash):** `python3` (3.10). Traces: `pip install perfetto`. Key tools: `pip install cryptography pynacl`.
- **Stream generation (WSL):** `python3` and `ffmpeg` built with `libx264` and `libx265`
  (check: `ffmpeg -hide_banner -encoders | grep -E 'libx26[45]'`). Which distro has it was not recorded; the host
  gtests use Ubuntu-22.04.
- Bash scripts that pass paths to Windows programs set `MSYS_NO_PATHCONV=1`; `quest_env.sh` therefore exports
  paths as `C:/x` (valid for Git Bash, python3 and adb.exe alike). Pass stream names, or Windows-style paths.

## Session hygiene (headset on a desk)

```bash
bash hygiene.sh pause     # setprop debug.oculus.guardian_pause 1 + am broadcast -a com.oculus.vrpowermanager.prox_close
bash hygiene.sh restore   # setprop debug.oculus.guardian_pause 0 + am broadcast -a com.oculus.vrpowermanager.automation_disable
```

Without `prox_close` the XR session is not FOCUSED off-face; without the Guardian pause a boundary prompt can
steal focus [INFERRED]. The runners send `prox_close` themselves; run `restore` when done.

## Workflow 1: decoder levers over a Wi-Fi RTP replay

```bash
# 1. generate the streams once (from Git Bash; the path is the WSL view of this folder)
MSYS_NO_PATHCONV=1 wsl.exe -d <distro> bash /mnt/c/xampp/htdocs/pixelpilot-xr/scripts/quest/gen_all.sh
#    or one group: ... gen_all.sh h264 | h265 | slices

# 2. run (each run: force-stop, prefs, launch XR, replay with keep-awake filler, parse logcat)
cd /c/xampp/htdocs/pixelpilot-xr/scripts/quest
python3 quest_lever_repeat.py 3                    # key-isolation matrix on h265_1slice.rtp -> out/quest_keys.csv
python3 quest_codec_matrix.py 3                    # codec x resolution x component       -> out/quest_codecs.csv
python3 quest_recheck.py 3 h264_720.rtp  | tee out/quest_recheck_h264.log
python3 quest_recheck.py 3 h265_1080.rtp | tee out/quest_recheck_h265_1080.log
python3 mkcsv.py                                   # the two recheck logs -> out/measurements-...-lever-recheck.csv

# 3. one run with a Perfetto trace (prefs as a Python dict)
bash trace_run.sh h264_720.rtp po_on.pftrace "{'dec_picture_order': True}"
python3 bq_stats.py out/po_on.pftrace              # decoder -> compositor buffer queue
python3 ../quest-latch/latch_analyze.py out/po_on.pftrace
```

Each line printed by `quest_lever_test.run()` shows the decoder component and the AMediaFormat keys that were
actually applied (`LL`, `PO`, `OR`, `prio`, ...), so a lever that did not take effect is visible.

## Workflow 2: compositor phase and phase lock

The PC plays the air unit: [../quest-latch/rtp_pace.py](../quest-latch/rtp_pace.py) sends `streams/h264_720.rtp`
frame by frame and, with `--lock`, steers its frame period from the headset's `PPXR1` phase reports.

```bash
bash hygiene.sh pause
bash pace_run.sh cal0  3407                            # open loop; 3407 = DEFAULT_LATCH_TO_DISPLAY_US
python3 ../quest-latch/calibrate_latch.py out/pace_cal0.pftrace   # re-derive latch -> display
bash pace_run.sh open1 3407                            # open loop
bash pace_run.sh lock1 3407 --lock --target-us 1200    # phase lock, 1.2 ms margin
python3 ../quest-latch/latch_analyze.py out/pace_open1.pftrace
python3 ../quest-latch/latch_analyze.py out/pace_lock1.pftrace
bash hygiene.sh restore
```

Alternate open/lock runs (N >= 2 each). Outputs: `out/pace_<tag>.{csv,log,pftrace}`. Other stream:
`PACE_STREAM=h265_720.rtp bash pace_run.sh ...`. If no phase reports arrive, check that the Windows firewall lets UDP 5610 in.

## Workflow 3: real link (RTL8812AU on the Quest + OpenIPC air unit)

Background and pitfalls (APFPV vs wfb, link id 7669206, keys): the real-link section of
[docs/xr-quest.md](../../docs/xr-quest.md).

```bash
# PC <-> air unit AP (to reach the air unit's shell, e.g. to switch it to wfb)
netsh wlan add profile filename="C:\xampp\htdocs\pixelpilot-xr\scripts\quest\openipc-wlan.xml"   # SSID OpenIPC, PSK 12345678
bash wait_air.sh                                       # (re)connect and wait for 192.168.0.1

# keys: the app's gs.key must pair with the air unit's /etc/drone.key
python3 keycheck.py <drone.key hex> keys/gs.key        # hex: xxd -p -c 64 /etc/drone.key on the air unit
python3 keyscan.py <drone.key hex> [root ...]          # find a matching gs.key on disk
python3 pwkey.py <password> <salt> keys/gs.key drone.key   # if the pair came from `wfb_keygen <password>`

# channel (only if unknown): 2D activity, reads link quality per channel
python3 chan_sweep.py 157 149 153

# run
bash link_check.sh 15                                  # is wfb arriving, did the decoder start
bash real_run.sh po_on  dec_picture_order=true         # prefs = gs.key + channel + levers, decode report
bash real_run.sh po_off dec_picture_order=false
```

For a trace on the real link, capture while the app runs:
`qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/t.pftrace' < ../quest-latch/compositor.pbtx`
(after `. quest_env.sh; export MSYS_NO_PATHCONV=1`), pull it, then `python3 ../quest-latch/transport_analyze.py`,
`python3 gaps.py` and `python3 bq_stats.py` on it.

**In-trace A/B of an air-unit lever (no photodiode).** Two separate traces cannot be compared: capture → arrival is
only known up to a constant that drifts with the air/headset clocks (~+96 ppm). So one long trace covers the whole
run while a timed loop on the air unit switches the lever (A B A C A …) and logs `<epoch> <label>` per step:

```bash
bash ab_long.sh bitrate 120            # lean trace (quest-latch/transport_long.pbtx) + Quest-minus-PC clock offset
python3 ../quest-latch/ab_segments.py out/ab_bitrate.pftrace steps.txt --air-offset-s <(quest-pc) - (air-pc)>
# link side, same windows: pre-FEC loss (air tx= on every step line), FEC repairs, RSSI, air/Quest temperatures
bash quest_thermal_log.sh 240 out/thermal_bitrate.csv &                       # start with the trace
python3 ../quest-latch/ab_link.py out/ab_bitrate.pftrace steps.txt --air-offset-s <offset ab_segments used> --thermal out/thermal_bitrate.csv
```

`ab_segments.py` fits the drift on the baseline steps only and prints, per step and per state, fps, packets/frame,
spread and capture → frame complete / → decoded in ms against that line, with the delta vs the baseline, plus RTP loss
(lost/s and % of the packets in the guarded window) and `undecoded`: frames with no `ppxr_frame_ready` mark within
20 ms of their last packet. That is not "never decoded": a late decode counts too (in a decoder stall every frame
does), and a missing frame can take the next frame's mark, so real drops can be undercounted. `--fit-offset` refines the air/Quest
step offset from the packets/frame steps (bitrate); for FEC use the app's `wfb-ng SESSION` logcat lines. `--csv` writes the
per-step rows (raw data for `docs/xr/data/`). Offline check: `python3 ../quest-latch/test_ab_segments.py`. Only for levers
applied live (no RTP restart).

## Script index

| Script | Purpose |
|---|---|
| `quest_env.py` / `quest_env.sh` | configuration (single source of truth) + bash helpers `qadb`, `quest_start_xr`, `quest_prox_close`, `quest_guardian_pause`, `quest_restore` |
| `quest_adb.py` | adb wrapper, shared-prefs rewrite (`set_prefs`, `write_prefs`), `prox_close`, `start_xr` |
| `slot_watch.py` + `air_probe.sh` | slot monitoring: `watch` (the air over eth0 every 5 s: reboot, wfb drops, IDR/s, fps, temperature, radio changes, 0x550 via bcn log), `between` (the Quest, only between measurements), `report` (the slot's alert timeline + app/air health logs); [docs/xr/slot-watch.md](../../docs/xr/slot-watch.md). Test: `test_slot_watch.py` |
| `quest_lever_test.py` | one lever run over a Wi-Fi replay; library for the three below |
| `quest_lever_repeat.py` | decoder-key isolation matrix, N shuffled rounds |
| `quest_codec_matrix.py` | decode time per codec x resolution x decoder component |
| `quest_recheck.py` | no keys / LL / OR / LL+OR on one clean stream |
| `mkcsv.py` | one-off: recheck logs -> measurements CSV |
| `rtp_record.py` / `rtp_play.py` | record RTP as `[f64 t][u16 len][bytes]` / replay with original pacing (`KEEPAWAKE=1` adds a Wi-Fi keep-awake filler) |
| `gen_all.sh`, `rtp_gen_matrix.sh`, `rtp_gen_slices.sh` | test-stream generation (WSL, ffmpeg testsrc2 -> RTP -> `streams/`) |
| `trace_run.sh` | one replay run with a 9 s Perfetto trace |
| `pace_run.sh` | phase-lock run: rtp_pace + trace |
| `hygiene.sh` | Guardian pause / restore |
| `set_link_prefs.py` | prefs for the real link: gs.key (Base64) + channel + bool levers |
| `link_check.sh` | real link: wfb quality + decoder lines |
| `real_run.sh` | real link: one lever config, decode report |
| `chan_sweep.py` | find the air unit's wfb channel |
| `wait_air.sh`, `openipc-wlan.xml` | PC Wi-Fi to the air unit's AP |
| `keycheck.py`, `keyscan.py`, `pwkey.py` | wfb-ng key pairing: check, search, derive from a keygen password |
| `bq_stats.py`, `gaps.py`, `trace_query.py` | Perfetto analysis: buffer queue, packet gaps, ad-hoc SQL |
| `ab_run.sh` | one transport A/B sample on the running app (link_measure + 9 s trace + transport_analyze + gaps), same for wfb-ng and APFPV; `out/ab_<label>.{log,pftrace}` |
| `link_probe.sh` | wfb link-health sample for diagnosing a degraded link (display awake only for the sample, Quest Wi-Fi SSID/freq/RSSI + link_measure); appends to `out/link_probe.log` |
| `air_tunnel.py` | ADB to the Quest while it is a client of the air unit's APFPV AP: SSH forward over the air unit's eth0 (`adb connect 127.0.0.1:5595`) |
| `../quest-latch/switch_gap.py` | picture gap after a live air-unit mode switch, from one `ab_long.sh` trace: frozen / stream (air) / decoder (app) ms and decode ms after; offline test `test_switch_gap.py` |
| `ab_long.sh` | capture for an in-trace A/B: long lean trace + Quest-minus-PC clock offset (analysis: `../quest-latch/ab_segments.py`) |
| `pref_ab.sh` | `<label> <pref> <step_s> <value> …`: in-trace A/B of an app pref read at start-up (relaunch per step, optional build per step); values typed (true/false, digits, string); `EXTRA_PREFS='{json}'` held in every step; `CAPTURE=detached` for a capture with nothing streaming over adb; `START_AT=<PC epoch>` runs the steps on a clock schedule another device can share (e.g. a channel A/B with the air unit) |
| `wifi_ab.sh` | `check` / `start <label> [step_s] [pairs]` / `pull <label>`: T2' — the Quest's own Wi-Fi on/off A/B run by a setsid'd script ON the Quest (adb drops while Wi-Fi is off), step epochs on the Quest, Wi-Fi re-enabled after each off step plus an independent watchdog; detached capture |
| `stream_ab.sh` | `<label> <step_s> stream\|quiet …`: U1 of `docs/xr/uplink-t4-analysis.md`: one detached capture, the app never relaunched; `stream` steps run `quest_tx_log.sh` (a streaming adb logcat over Wi-Fi), `quiet` steps nothing; steps on the Quest clock |
| `ab_detached.sh` | `start <label> [s]` / `pull <label>`: the same lean trace, but perfetto runs detached on the Quest (`--background`) and the uplink `TX DESC` lines go to a logcat file on the Quest, so the capture survives adb dropping (Quest changing Wi-Fi network); `pull` writes `out/qtx_<label>.txt` in `quest_tx_log.sh` format |
| `decode_watch.sh` | watch the running decoder for N s (decode ms, fps, decoder reconfigurations), e.g. after an air-unit restart |
| `stop_crash_check.sh` | does the XR app survive repeated session stops (`relaunch` over the running instance / display `sleepwake`)? pid, SIGABRT, video re-attached per iteration |
| `../quest-latch/hold_steps.py` | turn the air unit's hold log (`ab_loop.sh pwr/mark/set`, adaptive-link runs) into a step log (`<PHASE>_p<dBm>`, `IDR_ON/OFF`, END) for ab_segments/ab_link |
| `../quest-latch/ab_timeline.py` | per-second timeline of one trace (RTP packets, decoded frames, wfb rx/lost, RSSI) on the Quest clock: link drops at a switch, adaptive-link settling time |
| `quality_shots.sh` | picture-quality stills without the headset: `adb screencap`, cropped to the left eye's video layer + stats overlay (link loss, fps, Mbit/s), with the Quest epoch per still |
| `air_frame.py` | air-side counterpart of `quality_shots.sh`: stills (JPG, ≤ 1600 px) from a waybeam recording (MPEG-TS) of the exact bitstream the encoder sent; the docstring has the recording recipe (a separate 64 MiB tmpfs, because waybeam refuses a directory with < 50 MiB free, `star6e_recorder.h:14` @ f8742fe) |
| `quest_tx_log.sh` | stream the Quest RTL's uplink injections (devourer `TX DESC`, one Quest epoch per frame) during a trace; `ab_link.py --quest-tx` turns it into TX/s per step (≈ 0 = adaptive link really off) |
| `quest_thermal_log.sh` | sample the Quest's thermal status, CPU/SoC/battery temperatures and battery level every few seconds during a trace (read-only) |
| `../quest-latch/ab_link.py` | link side of an in-trace A/B: air TX rate, pre-FEC loss, FEC repairs, loss after FEC, RSSI (best chain, plus RSSI / SNR per Quest receive chain in newer builds), air and Quest temperatures per step/state (needs the app's `ppxr_wfb_*` counters from `WfbStatsTrace`) |
| `cpu_threads.py`, `cpu_ab_run.sh` | CPU per app thread over a window (`/proc/<pid>/task/*/stat`); one state of an app-build A/B (install APK, XR, CPU + decode + link) |
| `blu.py` | Quest 2 backlight flash timing from the kernel panel dtsi numbers (`python3 blu.py 3664 14 7 1 120`) |
| `build_wb_f8742fe.sh` | **OpenIPC project, not this repo:** rebuild waybeam f8742fe for the air unit (WSL) |
| `test_quest_env.py` | offline checks of `quest_env.py` |
| `mavlink_fake.py` | synthetic MAVLink v1 telemetry (HEARTBEAT armed, SYS_STATUS, GPS_RAW_INT, GLOBAL_POSITION_INT) to the Quest's UDP 14550, to check the XR telemetry line when the air unit sends none; offline test `test_mavlink_fake.py` |
| `vmode_fake.py` | a stand-in for the air unit's VMODE1 preset receiver (list / apply / commit / save_default, 1 Hz state beacon, revert timer; `--switch-s`, `--fail <mode>`, `--busy`), to run the headset's preset menu without the air side; point the app at it with the pref `vmode_air` = `<PC IP>:9998` ([design](../../docs/xr/presets-design.md)); offline test `test_vmode_fake.py` |
| `physical_step.sh` | monitor for hands-on checks with the user (buttons, menu, RTL replug): `start <label>` pauses the Guardian and starts a logcat of the app tags + activity/USB events, `<step>` takes a screenshot and prints the log since the last step, `stop` restores the Guardian |
| `set_bw.py` | switch the app's wfb width (pref `bandwidth` 20/40) and optionally the channel (`wifi-channel`), keeping every other pref; backs up the original prefs once and `restore` writes them back; restarts XR, so the link restarts (used for O82b) |
| `menu_check.py` | scripted check of the full in-headset menu (docs/xr/menu-design.md) through the debug broadcast: opens it, Stats page, a live lever (tight reorder, same pid) and a relaunch lever (timestamps, new pid) toggled and back, close; screenshots to `out/quality_private/menu_<label>/`; prefs restored exactly; `--keep-awake` when nobody wears the headset |
| `preset_flow.py` | scripted preset run on the headset against `vmode_fake.py` (menu driven by the debug broadcast `com.openipc.pixelpilot.xr.DEBUG_INPUT`): screenshots per stage, commit or `--fail` revert, prefs restored |
| `test_quest_adb.py` | offline checks of `quest_adb.write_prefs` (read-back after every prefs write; adb faked) |

## Provenance

These scripts were rescued from a session scratchpad on 2026-09-26; what was kept, changed or skipped and why: [RESCUE-REPORT-2026-09-26.md](RESCUE-REPORT-2026-09-26.md).

> After a real-link test the air unit must be reverted with `linkmode-air.sh apfpv`. A power cycle alone leaves waybeam sending to `127.0.0.1`; see [docs/xr/real-link.md](../../docs/xr/real-link.md#restoring-the-air-unit-after-a-test-2026-09-27).
