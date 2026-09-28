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
  - [docs/xr/real-link.md](docs/xr/real-link.md): first real link (Quest 2 + RTL8812AU + OpenIPC air unit): setup, keys, link id, picture order.
  - [docs/xr/g2g-budget.md](docs/xr/g2g-budget.md): G2G budget per branch on the real link.
  - [docs/xr/station-mode.md](docs/xr/station-mode.md): APFPV through the RTL (devourer station mode): code, host build, go/no-go gate.
  - [docs/xr/troubleshooting.md](docs/xr/troubleshooting.md): build traps, Horizon OS quirks, adapter/link problems.
  - [docs/xr/transport-choice.md](docs/xr/transport-choice.md): why wfb-ng is the boot default, not APFPV; why APFPV through the RTL needs new code.
  - [docs/xr/presets-design.md](docs/xr/presets-design.md): design (for approval) of mode/quality presets switched from the headset, and the VMODE1 protocol to the air.
  - [docs/xr/menu-design.md](docs/xr/menu-design.md): design (for approval, 2026-09-29) of the full in-headset menu, right thumbstick only: every option (stream/decoder/XR levers, air mode/quality/radio/codec/channel), Stats pages with per-segment G2G latency, the VMODE1 extensions it needs.
  - **[docs/xr/HANDOFF.md](docs/xr/HANDOFF.md): current state of air unit / Quest / GS and the open items — start here in a new session.**
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
  [rtp_pace.py](scripts/quest-latch/rtp_pace.py), [test_rtp_pace.py](scripts/quest-latch/test_rtp_pace.py)).
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
