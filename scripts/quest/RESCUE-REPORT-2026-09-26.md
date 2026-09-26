# Rescue of the Quest 2 test scripts (2026-09-26)

Source: the session scratchpad `C:/Users/vlad_/AppData/Local/Temp/claude/c--xampp-htdocs-ev300d/b7f339c6-.../scratchpad/`
(deleted when that session ends). Target: `scripts/quest/` on branch `xr-native`. Nothing was committed, and no
adb or network command was run. Usage and workflows: [README.md](README.md).

## Files (31 to commit, plus this report)

| File | Purpose | Change vs scratchpad |
|---|---|---|
| `quest_env.py` | **new**, the single source of truth: ADB, QUEST, PC_IP, package and activities, ports 5600/5610, WFB_CHANNEL, GS_KEY, air AP, dirs; `stream_path()`, `out_path()`, path converters; `--sh` prints exports | new |
| `quest_env.sh` | **new**, bash side: `eval "$(python3 quest_env.py --sh)"` plus `qadb`, `quest_start_xr`, `quest_prox_close`, `quest_guardian_pause`, `quest_restore` | new |
| `quest_adb.py` | **new**: `adb()`, `pref_xml()`, `write_prefs()`, `set_prefs()`, `prox_close()`, `start_xr()` (moved out of quest_lever_test) | split out |
| `quest_lever_test.py` | one lever run over a Wi-Fi replay (library) | constants and adb helpers from env/quest_adb, re-exported (`t.adb`, `t.set_prefs`, `t.PKG` still work); stream via `stream_path()` |
| `quest_lever_repeat.py` | key-isolation matrix, N shuffled rounds | default CSV → `out/quest_keys.csv` |
| `quest_codec_matrix.py` | codec × resolution × component | CSV → `out/quest_codecs.csv` |
| `quest_recheck.py` | no keys / LL / OR / LL+OR recheck | usage docstring only |
| `mkcsv.py` | one-off: recheck logs → measurements CSV | dirs default to `out/` |
| `rtp_record.py` | record RTP (runs in WSL) | usage comment only; no env import on purpose |
| `rtp_play.py` | replay with original pacing, `KEEPAWAKE=1` filler | resolves a bare name in `streams/` |
| `rtp_gen_matrix.sh` | one matrix stream (WSL ffmpeg) | sources env; bare output name → `streams/` |
| `rtp_gen_slices.sh` | h265 720p N-slice stream (was `rtp_gen.sh`) | same, renamed |
| `gen_all.sh` | generate streams; groups `h264`, `h265`, `slices` | **merges `gen_all.sh` + `gen_h264.sh`** and adds the slice streams quest_lever_repeat needs |
| `trace_run.sh` | replay run + 9 s Perfetto trace | env/qadb; bare output name → `out/`; uses `../quest-latch/compositor.pbtx` (identical to the scratch copy) |
| `pace_run.sh` | phase-lock run (`../quest-latch/rtp_pace.py`) + trace | env/qadb; outputs → `out/`; passes `--port`/`--report-port` explicitly (same values as rtp_pace defaults); `PACE_STREAM` override |
| `hygiene.sh` | **new**: `pause` / `restore` (Guardian + proximity) | new, wraps the quest_env.sh helpers |
| `set_link_prefs.py` | real-link prefs: gs.key Base64 + channel + bool levers | uses `quest_adb.write_prefs`/`PREFS_HEADER` (no duplicated XML header) |
| `link_check.sh` | real link: wfb quality + decoder lines | env/qadb |
| `real_run.sh` | real link: one lever config, decode report | key/channel from `$GS_KEY`/`$WFB_CHANNEL` (was `raw-legacy-gs.key` 157 in the script dir) |
| `chan_sweep.py` | find the air unit's channel (2D activity) | package/activity from env |
| `wait_air.sh` | PC Wi-Fi → air AP, wait for 192.168.0.1 | `AIR_SSID`/`AIR_IP`/`WLAN_IF` from env |
| `openipc-wlan.xml` | Windows WLAN profile, SSID OpenIPC, PSK 12345678 (OpenIPC default) | as is |
| `keycheck.py` | check a drone.key/gs.key pair | docstring |
| `keyscan.py` | search disk for a matching gs.key | roots from argv (old list is the default); removed dead `... and False` clause |
| `pwkey.py` | derive the pair from a `wfb_keygen` password | docstring |
| `bq_stats.py`, `gaps.py`, `trace_query.py` (was `tp_q.py`) | Perfetto analysis | docstrings; unused `statistics` import dropped in gaps.py |
| `blu.py` | Quest 2 backlight flash timing from dtsi numbers | docstring with the example `3664 14 7 1 120` (BOE 120 Hz dtsi values) |
| `build_wb_f8742fe.sh` | waybeam f8742fe rebuild | header note: **belongs to the OpenIPC low-latency project** |
| `test_quest_env.py` | **new** offline test of quest_env | new |
| `README.md` | prerequisites, config table, hygiene, three workflows, script index | new |

`.gitignore` (repo root) gained: `scripts/quest/streams/`, `scripts/quest/out/`, `scripts/quest/keys/`,
`scripts/quest/**/*.rtp`, `scripts/quest/**/*.key`, `__pycache__/`. The `/repos/` line in the same diff was
**not** added by this rescue (another agent's concurrent change).

## Config decisions

- **Python is the single source; bash derives from it.** `quest_env.sh` runs `python3 quest_env.py --sh`, so no
  default is written twice. Cost: one python start per bash script (~50 ms).
- **Paths are exported as `C:/x`** (`cygpath -m` style) on Windows: valid for Git Bash `cd`/redirection, for
  Windows python3, and for adb.exe under `MSYS_NO_PATHCONV=1`. `ADB_SH` (`/c/...`) is what bash executes.
  `quest_env.sh` finds its own .py via `cygpath -m`, so it works even when `MSYS_NO_PATHCONV=1` is already set.
  Under WSL (no cygpath) everything is `/mnt/c/...`; `native()` converts `C:\x` ↔ `/mnt/c/x` / `/c/x` for overrides.
- The Quest's IP (stream target) is derived from `QUEST` (`QUEST_HOST`), never stored twice.
- Streams: a bare name resolves to `streams/`, a path is used as given (`stream_path()`); outputs go to `out/`.
- The trace config is taken from `../quest-latch/compositor.pbtx` (byte-identical to the scratch copy) instead of a
  second copy.

## Verification

- `python3 -m py_compile` on all 19 `.py`: all pass.
- `bash -n` on all 11 `.sh` (incl. `quest_env.sh`): all pass.
- `python3 test_quest_env.py`: 3/3 pass (conversions, env overrides + restore, `stream_path`, `--sh` exports).
- Sourcing `quest_env.sh` in Git Bash with `MSYS_NO_PATHCONV=1` preset: exports OK, `qadb` defined, `$ADB_SH`
  exists, `$QUEST_LATCH/compositor.pbtx` and `rtp_pace.py` found, `QUEST=1.2.3.4:5555` override → `QUEST_HOST=1.2.3.4`.
- `git status --short -uall scripts/quest .gitignore`: only the files above (+ this report); `git check-ignore`
  confirms `streams/`, `out/`, `keys/`, `__pycache__/` are ignored.
- `grep -rnE "192\.168\.100\.(114|213)|adb\.exe|Temp/claude|scratchpad" scripts/quest`: hits only in
  `quest_env.py`, `quest_env.sh` comments, `README.md` (the config table) and this report.
- **Not verified (no headset/network/WSL runs allowed):** end-to-end runs of every script, and stream generation
  in WSL (which distro has ffmpeg + libx264/libx265 is unknown).

## Kept locally, not in git

- `scripts/quest/keys/` (gitignored): the scratchpad's wfb key files `raw-legacy-gs.key` (also copied as `gs.key`,
  the default `GS_KEY`, which real_run.sh used), `raw-legacy-drone.key`, `raw-wifibroadcast-ng-drone.key`,
  `openipc-legacy-drone.key`, `openipc-wifibroadcast-ng-drone.key`. Copied so the real-link workflow survives the
  scratchpad; secrets policy keeps them out of git.

## Skipped, and why

- `*.rtp`, `*.pftrace`, logs, CSVs, HTML/TXT/PDF pages, images, MP4s, kernel `.c`/`.dtsi`, SDK trees: junk or data
  (the measurements already live in `docs/xr/data/`).
- `latch_analyze.py`, `compositor.pbtx`: newer/identical copies already in `scripts/quest-latch/`.
- `gen_h264.sh`: merged into `gen_all.sh h264`.
- `rtp_gen_intra.sh` (all-intra H.265): no rescued script uses it; recreate with `-x265-params keyint=1` if needed.
- `emu_lever_test.py`: emulator + 2D upstream package; the emulator decoder says nothing about Quest latency.
- `orig_check.sh` (upstream release app on the real link), `after_switch.sh`, `tx5.sh`, `wait_ap.sh`: ad-hoc,
  hardcoded scratch paths, or subsumed by `link_check.sh` / `wait_air.sh`.
- `gtest.sh` (host gtests of `app/videonative` in WSL): useful but not Quest-specific; candidate for `scripts/`
  if the coordinator wants it (needs Ubuntu-22.04).
- `gen_edid.py`, `pclk.py`, `lat.py`, `md5chk.py`, `s.py`, `str.py`, `strip.py`: EV200D goggles / DVR firmware work,
  belonging to the ev300d project, not here (gen_edid.py may be worth rescuing into `c:/xampp/htdocs/ev300d/tools/`).
- `bfs.py`, `crop.py`, `dec.py`, `edit.py`, `ex.py`, `h2t.py`, `yt.py`, `*.ps1`, `latch_analyze`-era helpers:
  one-off session utilities.
