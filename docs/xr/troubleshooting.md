# Troubleshooting (Quest XR fork)

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

Single source of truth: a trap that is already described in a measured section is **linked** here, not
copied. Only items that had no home in the repo before 2026-09-26 are written out in full on this page.

## Build and test environment (Windows host)

| Symptom | Cause | Fix | Tag |
|---|---|---|---|
| Gradle / AGP 8.5 build fails with the default `java` | The default JDK on the build PC is 25; Gradle 8.7 + AGP 8.5 need JDK 17 | `export JAVA_HOME='C:\Program Files\Java\jdk-17'` before `./gradlew` (see [Build and install](../xr-quest.md#build-and-install)) | [PROVEN: build, 2026-09-26] |
| `:app:mavlink` fails with "The filename, directory name, or volume label syntax is incorrect" | `local.properties` written with backslashes; `\` is an escape in `.properties` files | `sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk` (forward slashes) | [PROVEN: build, 2026-09-26] |
| Recursive submodule clone fails | One of devourer's `reference/*` vendor-kernel submodules pins an unpushed commit | Init the direct submodules only, non-recursive, as CI does: `git submodule update --init` | [PROVEN: [.github/workflows/build.yml](../../.github/workflows/build.yml) lines 21-26] |
| Gradle: "Could not move temporary workspace" | Windows cache race | Rerun the same Gradle command | [PROVEN: build, 2026-09-26] |
| WSL does not start: `Wsl/Service/CreateInstance/E_FAIL` | Drive C: full (0.4 GB free: large pagefile + the Ubuntu-22.04 VHD) | Free space on C: first (`df -h /c`); full diagnosis in the [WSL start failure report](research/wsl-start-failure-2026-09-26.md) | [PROVEN: incident 2026-09-26] |
| Host gtests: no `cmake` | Ubuntu-20.04 in WSL has no CMake ≥ 3.14 | Use WSL **Ubuntu-22.04** (g++ 11, cmake 3.22); command in [Build and install](../xr-quest.md#build-and-install) | [PROVEN: 2026-09-26] |
| Android test emulator: `c2.goldfish.hevc.decoder` fails with err 14 | swiftshader GPU mode | Start the emulator with `-gpu host` (x86_64 google_apis API 34 runs the arm64 APK via translation; `-partition-size` max 2047). UDP into the emulator: `adb emu redir add udp:5600:5600`, which listens on Windows 127.0.0.1 only, so replay from Windows, not WSL. The AVD + image need ~6 GB of C:, delete after use | [PROVEN: 2026-09-26 build-env notes] |

## Horizon OS quirks (Quest 2)

- **"Controller required" dialog blocks the launch** when the controllers are off. Avoided by declaring
  hand-tracking support in the XR module's manifest (`oculus.software.handtracking`, not required); the Meta hand
  gesture still exits the app [PROVEN: [app/xr/src/main/AndroidManifest.xml](../../app/xr/src/main/AndroidManifest.xml) lines 16-22].
- **The Guardian (boundary) dialog interrupts test sessions**, and the display sleeps when the headset is not
  worn. For bench tests: `adb shell setprop debug.oculus.guardian_pause 1` plus
  `adb shell am broadcast -a com.oculus.vrpowermanager.prox_close`. Restore afterwards with
  `adb shell setprop debug.oculus.guardian_pause 0` and `adb shell am broadcast -a com.oculus.vrpowermanager.automation_disable`.
  The property is lost on reboot. Sources and caveats: [research report 03](research/2026-09-26-quest2/03-system-tweaks-cfw-status.md)
  (Guardian / proximity rows). Rule of thumb for this repo: see [CLAUDE.md](../../CLAUDE.md) (Quest test hygiene).
- **"Launch is blocked because: a Reprojected OS dialog is currently showing"**: a pending USB-permission dialog
  (`com.oculus.os.vrusb/UsbPermissionActivity`) blocks launching immersive apps. Answer or close the dialog in the
  headset, or `adb shell am force-stop com.oculus.os.vrusb` [PROVEN: seen on the device, 2026-09-26].
- **`adb shell cmd wifi connect-network …` is silently ignored on Horizon OS**: it returns without joining the
  network. Join Wi-Fi from the headset's own settings [PROVEN: seen on the device, 2026-09-26].
- **Display stuck at 90 Hz**: 120 Hz has to be enabled on Quest 2 under Settings → System → Display; see the
  [smoke checklist](../xr-quest.md#smoke-checklist-first-run-on-a-headset).
- **Picture corruption on a light Wi-Fi test stream**: Quest Wi-Fi power save drops or bunches a light UDP stream;
  keep the radio busy. See [first on-device results](decoder-levers.md#first-on-device-results-quest-2-2026-09-26-horizon-os-build-up1a231005007a1)
  (the `filler()` in [rtp_pace.py](../../scripts/quest-latch/rtp_pace.py) does this).
- **`xr_thread_hints` has no effect**: the runtime rejects every hint with `-1000003001`; see
  [first on-device results](decoder-levers.md#first-on-device-results-quest-2-2026-09-26-horizon-os-build-up1a231005007a1).
- **No `c2.android.*` software decoders** for apps on Horizon OS; see
  [codec, component and resolution](decoder-levers.md#codec-component-and-resolution-2026-09-26).
- **Image upside-down or mirrored**: toggle *XR: flip image vertically* (lever table in the [guide](../xr-quest.md#use)).

## The app, the adapter and the link

- **Release PixelPilot 0.21.0 crashes on launch** (`BackgroundServiceStartNotAllowedException`) if it is started
  while the headset sleeps: see [Build and install](../xr-quest.md#build-and-install). Wake the headset first.
- **Hot-plugging the RTL8812AU crashed the app twice** (devourer EEPROM read exception, then a libusb segfault in
  `~RtlJaguarDevice`); the third enumeration worked. Details and the fix still needed: "Known issue seen during this
  work" at the end of [Phase lock](compositor-phase.md#phase-lock-steering-the-source-onto-the-compositor-latch-proof-of-concept-2026-09-26).
- **Plugging the adapter may open the wrong app**: `USB_DEVICE_ATTACHED` can open the `.xr` app's 2D
  `VideoActivity` instead of the release PixelPilot, because both builds declare the same filter on
  `.VideoActivity` [PROVEN: [app/src/main/AndroidManifest.xml](../../app/src/main/AndroidManifest.xml) lines 52-72; the
  debug build only adds `applicationIdSuffix ".xr"`]. Start the XR mode from **Video → Launch XR (Quest)** in the app
  you want.
- **No video from a real OpenIPC air unit** (air unit in APFPV instead of wfb, `drone.key`/`gs.key` pair, link id 0
  vs 7669206): see [First real link](real-link.md#first-real-link-quest-2--rtl8812au--openipc-air-unit-2026-09-26),
  steps 1-3.
- **~96 ms decode on the real stream** (the decoder holds ~16 frames): `dec_picture_order` must be on; see
  [First real link](real-link.md#first-real-link-quest-2--rtl8812au--openipc-air-unit-2026-09-26).
- **Multi-slice H.264 shows as broken frames**: needs *whole access units* (`au_aggregation`) or a single-slice
  encoder; see [codec, component and resolution](decoder-levers.md#codec-component-and-resolution-2026-09-26).
- **The ESP32 + LDR G2G rig reads nothing through the lenses** (the backlight flashes ~1 ms per frame): use a
  photodiode or 480 fps slow motion; see [Measuring](../xr-quest.md#measuring-the-point-of-this-mode).

- **The air unit sends no video after a test, even after a power cycle.** waybeam's destination stays `127.0.0.1` from the wfb switch. Run `linkmode-air.sh apfpv`: see [real-link.md § Restoring the air unit after a test](real-link.md#restoring-the-air-unit-after-a-test-2026-09-27).
