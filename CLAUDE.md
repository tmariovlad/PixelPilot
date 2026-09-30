# pixelpilot-xr: PixelPilot fork with a native OpenXR mode for Meta Quest 2

This repo is a fork of [OpenIPC PixelPilot](https://github.com/OpenIPC/PixelPilot) (the Android ground-station
app for OpenIPC FPV: RTL8812AU over USB via devourer + wfb-ng, MediaCodec decode). Branch `xr-native` adds
`XrVideoActivity`, which shows the stream inside an OpenXR session: MediaCodec decodes straight into a
compositor-owned surface (`XR_KHR_android_surface_swapchain`) shown as a head-locked layer, with no app render
pass. It also adds the decoder/XR latency levers under **Video → Latency experiments** and the tools to measure
them on a Quest 2. The debug build installs as its own app, **PixelPilotXr** (`com.openipc.pixelpilot.xr`).
Remotes: `origin` = fork `tmariovlad/PixelPilot`, `upstream` = `OpenIPC/PixelPilot`. This repo is the single
home of all Quest work.

## Documentation tree

- [README.md](README.md): upstream PixelPilot readme, with a short "Quest native XR mode" section.
- [docs/xr-quest.md](docs/xr-quest.md): **entry guide** (build/install, use, lever table, smoke checklist,
  measuring, open questions, and the index of results below). Code comments and other projects link to this path.
  - [docs/xr/decoder-levers.md](docs/xr/decoder-levers.md): decoder levers measured on Quest 2 (first on-device
    results, key isolation, clean-stream recheck, codec/component/resolution).
  - [docs/xr/compositor-phase.md](docs/xr/compositor-phase.md): compositor latch timing measured + phase-lock proof of concept.
  - [docs/xr/phase-lock-protocol.md](docs/xr/phase-lock-protocol.md): the PPXR1 report and the reference controller (contract for an air-side phase lock).
  - [docs/xr/display-latency.md](docs/xr/display-latency.md): decode → photon on Quest 2 (refresh rate 72/90/120, compositor latch, thermal drop, levers ranked; research reports + refresh bracket).
  - [docs/xr/stats-backend.md](docs/xr/stats-backend.md): data behind the menu's Stats pages (per-segment latency via the waybeam RTP sidecar + clock sync, RX rate, RSSI dBm, loss).
  - [docs/xr/fec-block-probe.md](docs/xr/fec-block-probe.md): PPXR_FECBLK, one line per unrecoverable video FEC block (fragment bitmap, RSSI, span, outage gap, bad FCS) and fec_blocks.py; PPXR_RTPHOLE, each RTP hole split pre-FEC (air input) vs post-FEC (radio), and rtp_holes.py; PPXR_RELEASE + zflush.py for the -Z (flush the FEC block at each frame end) slot.
  - [docs/xr/health-logging.md](docs/xr/health-logging.md): the app's own health log (PPXR_EVENT per event: stalls/HOLD with cause, freezes, IDR failures, headset asleep, adapter unplugged, loss bursts; PPXR_HEALTH every 10 s; files/ppxr_health.log) and health_log.py.
  - [docs/xr/real-link.md](docs/xr/real-link.md): first real link (Quest 2 + RTL8812AU + OpenIPC air unit): setup, keys, link id, picture order.
  - [docs/xr/g2g-budget.md](docs/xr/g2g-budget.md): G2G budget per branch on the real link.
  - [docs/xr/station-mode.md](docs/xr/station-mode.md): APFPV through the RTL (devourer station mode): code, host build, go/no-go gate.
  - [docs/xr/troubleshooting.md](docs/xr/troubleshooting.md): build traps, Horizon OS quirks, adapter/link problems.
  - [docs/xr/transport-choice.md](docs/xr/transport-choice.md): why wfb-ng is the boot default, not APFPV; why APFPV through the RTL needs new code.
  - [docs/xr/presets-design.md](docs/xr/presets-design.md): design (for approval) of mode/quality presets switched from the headset, and the VMODE1 protocol to the air.
  - [docs/xr/channel-survey-design.md](docs/xr/channel-survey-design.md): design (for review, 2026-09-30) of the pre-flight channel survey: RTL sweep via devourer (CCA/NHM busy, foreign frames, bad FCS) + the Quest's Wi-Fi scan, score and graph in the menu, the VMODE1 `ch=` two-phase switch, validation A/B.
  - [docs/xr/menu-design.md](docs/xr/menu-design.md): design (for approval, 2026-09-29) of the full in-headset menu, right thumbstick only: every option (stream/decoder/XR levers, air mode/quality/radio/codec/channel), Stats pages with per-segment G2G latency, the VMODE1 extensions it needs.
  - **[docs/xr/HANDOFF.md](docs/xr/HANDOFF.md): current state of air unit / Quest / GS and the open items — start here in a new session.**
  - [docs/xr/slot-plan-2026-10-01.md](docs/xr/slot-plan-2026-10-01.md): runbook for the 2026-10-01 air day (HD 71 ms hunt, -Z × payload, L1 shutter, RC probe, super-frame cap, O118 S2 intra refresh if T1 is a go): owners, files with md5s, launch lines, Quest captures, pulls, analysis commands, stop rules, reverts; common power-on/clock/mirror/power-off steps.
  - [BACKLOG.md](BACKLOG.md): feature/issue backlog found during other work (e.g. the 5 GHz channel survey / spectrum calibration with a per-channel graph).
  - [docs/xr/data/](docs/xr/data/): raw measurement CSVs (linked from the topic files).
- Design: [spec](docs/superpowers/specs/2026-09-26-quest-openxr-viewer-design.md) ·
  [implementation plan](docs/superpowers/plans/2026-09-26-quest-openxr-viewer.md).
- Research (moved in from the ev300d project): [Quest 2 research synthesis](docs/xr/research/2026-09-26-quest2/00-INDEX-SYNTHESIS.md) ·
  [WSL start failure incident](docs/xr/research/wsl-start-failure-2026-09-26.md) ·
  [research move report](docs/xr/research/MOVE-REPORT-2026-09-26.md).
- Scripts: [scripts/quest/README.md](scripts/quest/README.md) (Quest test scripts) ·
  [scripts/quest-latch/](scripts/quest-latch/) (Perfetto latch/transport analysis and the phase-lock stand-in:
  [compositor.pbtx](scripts/quest-latch/compositor.pbtx), [latch_analyze.py](scripts/quest-latch/latch_analyze.py),
  [transport_analyze.py](scripts/quest-latch/transport_analyze.py), [rtp_seq.py](scripts/quest-latch/rtp_seq.py), [switch_gap.py](scripts/quest-latch/switch_gap.py), [sidecar_log.py](scripts/quest-latch/sidecar_log.py) (waybeam per-frame encode timing from the air, no RTP needed), [calibrate_latch.py](scripts/quest-latch/calibrate_latch.py),
  [rtp_pace.py](scripts/quest-latch/rtp_pace.py), [test_rtp_pace.py](scripts/quest-latch/test_rtp_pace.py);
  loss and freeze analyzers: [frame_fate.py](scripts/quest-latch/frame_fate.py) (why frames are missing: hole / edge / never arrived),
  [freeze_gaps.py](scripts/quest-latch/freeze_gaps.py) (each VIDEO STALLED gap: link gap vs freeze vs decoder),
  [loss_bursts.py](scripts/quest-latch/loss_bursts.py) (post-FEC loss runs: length, ms, 102.4 ms beacon lock),
  [rtp_holes.py](scripts/quest-latch/rtp_holes.py) (each RTP hole: pre-FEC air input vs post-FEC radio, with a circular time-shift control; air log via [air_drops.py](scripts/quest-latch/air_drops.py)),
  [owd.py](scripts/quest-latch/owd.py) (relative one-way delay per frame, first packet vs completion: clean-link floor per 250 ms window, payload/frame-size effect, loss-locked profile; [stats-backend §7.1](docs/xr/stats-backend.md)),
  [zflush.py](scripts/quest-latch/zflush.py) (-Z: per frame FEC-recovered / held / waited for the next frame, completion delay per class, air FRAME_FLUSH per state),
  [hunt_timeline.py](scripts/quest-latch/hunt_timeline.py) (HD 71 ms hunt, post-run: each rig first-light step event with ±60 s of air_health EV/SNAP, snapshots, Quest PPXR_EVENT/STATS and watchdog lines on the PC clock),
  [air_log_mirror.sh](scripts/quest-latch/air_log_mirror.sh) (PC-side, every air slot: mirror the air's /tmp logs every 60 s, keep the last good copy, `.pre` on a reboot, HANG?/BACK events),
  [zslot.py](scripts/quest-latch/zslot.py) (one table per arm for a -Z × payload slot: lnk/tot/post-FEC ab_fit effects linear + quadratic, last/last95/spread, FEC-recovered share and wait, FRAME_FLUSH fillers/s; imports ab_fit / ab_segments / zflush),
  [drop_seconds.py](scripts/quest-latch/drop_seconds.py) (radio post-FEC loss and IDR requests/frames in the air's input-drop seconds vs the rest, and per step),
  [big_frames.py](scripts/quest-latch/big_frames.py) (latency of the largest frames, e.g. scene changes / IDR, apart from the rest)),
  [tsv_steps.py](scripts/quest-latch/tsv_steps.py) (rows of a probe TSV, e.g. rtp_holes / fec_blocks --tsv, per air step and class),
  [stats_steps.py](scripts/quest-latch/stats_steps.py) (median PPXR_STATS fields per step, e.g. RSSI dBm),
  [latency_bins.py](scripts/quest-latch/latency_bins.py) (latency over time within each step: a building queue),
  [first_light_steps.py](scripts/quest-latch/first_light_steps.py) (the rig-side detector: a sustained first-light step on latency-test's per-flash CSV, e.g. the HD 71 ms state),
  [first_light_follow.py](scripts/quest-latch/first_light_follow.py) (the same detector live on the rig's growing run files; fires a command, e.g. the air snapshot),
  [quest_airlog.py](scripts/quest-latch/quest_airlog.py) (an ab_run-style air log rebuilt from the Quest, for ab_fit.py when the air's log is lost)).
- Doc restructure log: [docs/xr/RESTRUCTURE-REPORT-2026-09-26.md](docs/xr/RESTRUCTURE-REPORT-2026-09-26.md).

New results go into the matching `docs/xr/` topic file (raw data into `docs/xr/data/`), with a one-line summary
in the "Results and deep dives" index of [docs/xr-quest.md](docs/xr-quest.md). Tag claims [PROVEN] / [INFERRED] /
[SPECULATION] with a reference, as the existing sections do.

## Rules for working here

- **Measure, then conclude, with the physical setup fixed.** Repeat an on/off test alternately (N >= 2 per state) and never draw a conclusion from one run: a one-shot adaptive-link A/B on 2026-09-27 was confounded by the headset being moved ([docs/xr/real-link.md](docs/xr/real-link.md#diagnosing-a-bad-link-2026-09-27)). On a real link, check both ends (air unit `tx_packets` vs Quest sequence gaps) before blaming the app.

**Build (Windows, Git Bash)**
- JDK 17 only: `export JAVA_HOME='C:\Program Files\Java\jdk-17'` (the default `java` is 25 and breaks Gradle 8.7 / AGP 8.5).
- `local.properties`: `sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk` with **forward slashes**.
- Submodules non-recursive, like CI: `git submodule update --init`.
- `./gradlew assembleDebug`, then `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
- More traps: [docs/xr/troubleshooting.md](docs/xr/troubleshooting.md).

**Tests**
- Host gtests (`AccessUnitAssembler`, `DecoderLevers`, `BufferedPacketQueue`) run in **WSL Ubuntu-22.04**
  (Ubuntu-20.04 has no suitable CMake), from the repo root:
  `cmake -S app/videonative/src/main/cpp/tests -B /tmp/ppxr-tests && cmake --build /tmp/ppxr-tests -j8 && (cd /tmp/ppxr-tests && ctest --output-on-failure)`.
- Host gtests for `TxFrame` (wfb TX lifecycle over real UDP sockets; needs libsodium) and the other wfb helpers (`SignalQualityCalculator` per-chain averages, `StatsWindow`, `LinkGuard`, …), same WSL:
  `cmake -S app/wfbngrtl8812/src/main/cpp/tests -B /tmp/wfbng-tests && cmake --build /tmp/wfbng-tests -j8 && (cd /tmp/wfbng-tests && ctest --output-on-failure)`.
  If github.com is unreachable from WSL, add `-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=/tmp/ppxr-tests/_deps/googletest-src`.
- JVM tests: `./gradlew :app:testDebugUnitTest :app:videonative:testDebugUnitTest :app:xr:testDebugUnitTest`.

**The headset**
- The debug build (`com.openipc.pixelpilot.xr`, "PixelPilotXr") installs **next to** the user's release
  PixelPilot 0.21.0 (`com.openipc.pixelpilot`). Never uninstall, replace or downgrade the release app.
- Quest test hygiene: during tests pause the Guardian and keep the display awake
  (`adb shell setprop debug.oculus.guardian_pause 1` + `adb shell am broadcast -a com.oculus.vrpowermanager.prox_close`);
  **restore afterwards** (`adb shell setprop debug.oculus.guardian_pause 0` +
  `adb shell am broadcast -a com.oculus.vrpowermanager.automation_disable`). Details in
  [troubleshooting](docs/xr/troubleshooting.md#horizon-os-quirks-quest-2).

**Git**
- Commit only the files you touched (`git add <files>`, never `git add -A`).
- Never push to, or open a PR against, upstream OpenIPC. `origin` (the fork) only, and only when asked.
- The **devourer submodule** comes from the fork `tmariovlad/devourer`, branch `pixelpilot-xr` (`.gitmodules`, since
  2026-09-28). Commit devourer changes there and push only to that fork (the `fork` remote; the local `origin` push URL
  is disabled on purpose). Never push to or open a PR against `openipc/devourer` unless the user asks.
- The **wfb-ng submodule** comes from the fork `tmariovlad/wfb-ng`, branch `pixelpilot-xr` (since 2026-09-30, the
  user's choice): upstream `svpcom/wfb-ng` plus our commits (the RX front-block drain, `66d4bdb`,
  [fec-block-probe.md §8](docs/xr/fec-block-probe.md)). xr-native pins `66d4bdb` (re-pinned 2026-09-30,
  after a toggle run refuted a suspected loss regression; the drain is a no-op with the stock air TX). Same rules as devourer: the `fork` remote only, the local
  `origin` push URL disabled, never push to or open a PR against `svpcom/wfb-ng` unless the user asks. An older
  checkout needs `git submodule sync` once ([troubleshooting](docs/xr/troubleshooting.md)).
