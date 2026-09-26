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
- **`adb shell cmd wifi connect-network …` on Horizon OS joins a network only if it is already saved.**
  - For a new network it returns without joining [PROVEN: seen on the device, 2026-09-26]: join it once from the headset's own settings.
  - Once saved, `cmd wifi connect-network OpenIPC wpa2 12345678` moved the Quest onto the air unit's AP 3 times out of 3, with no one touching the headset [PROVEN: 2026-09-27, `mWifiInfo SSID: "OpenIPC" … IP: /192.168.0.10`].
  - When the AP goes away the Quest falls back to a saved home network by itself (Zeul36 on 2026-09-27, not the Zeul37 it had before). `cmd wifi list-networks` shows what is saved.
  - Correction 2026-09-27: this line used to say the command is always ignored.
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

## More traps hit on 2026-09-26/27

- **Scripted edits change line endings.** Some files in this repo are CRLF and some LF. A Python rewrite with default newline handling converts a file and turns the whole diff noisy. Read and write with `newline=""` and keep whichever ending the file had.
- **NDK APIs newer than minSdk 26** (e.g. `ATrace_setCounter`, API 29) fail to compile with "is unavailable: introduced in Android 29". Fix used in `app/xr` and `app/videonative` CMake:
  - `target_compile_definitions(... __ANDROID_UNAVAILABLE_SYMBOLS_ARE_WEAK__)`
  - `-Werror=unguarded-availability`
  - wrap every call in `if (__builtin_available(android 29, *))`.
  - Inside that guard, never `return` early past code that must still run.
- **`adb install` from Git Bash needs a Windows path:** `adb install -r "$(cygpath -w app/build/outputs/apk/debug/app-debug.apk)"`. With an MSYS path, adb fails to stat the file.
- **Upstream crash, fixed in this fork:** `WfbngLink` read the key from a hardcoded path and crashed when it was absent. It now uses `Context.getFilesDir()/gs.key`, filled by `GsKeyStore.copyToFiles`.
- **Copying files to the air unit:** it has no sftp-server, so use `pscp -scp`. In batch mode pscp also needs `-hostkey "SHA256:…"`. Read the fingerprint on the air unit with `dropbearkey -y -f /etc/dropbear/dropbear_*_host_key`. Plain HTTP from the PC does not work while the PC's Wi-Fi is on the air unit's AP, because Windows treats that network as public and blocks inbound connections.
- **`linkmode-air.sh wfb` reverts itself to APFPV** when `wfb_tx` injects nothing for 12 s (`AIR_STATE=ERROR:wfb_tx-not-injecting-after-poll-reverted-apfpv`). That usually means waybeam is producing 0 fps; check `/var/lib/misc/waybeam-boot.log` and `/tmp/waybeam-switch.log`.
- **The PC can hold `192.168.0.10` on the air unit's AP.** That address is the air unit's fixed video destination. While the PC's Wi-Fi card is connected there, the HIL GS `.208` cannot take `.10`. Disconnect first: `netsh wlan disconnect interface="Wi-Fi 2"`.
- **Heavy packet loss with a strong SNR = distance or walls, not the app** (2026-09-27).
  - With the air unit in another room: ~83–89 % of wfb packets were lost (1295 received, 6550 missing in 8.6 s), although the received packets showed SNR 31.6 dB. The air unit injected all ~1313 pkt/s with 0 drops.
  - The Quest RTL was also transmitting ~100 pkt/s, most likely keyframe/IDR requests caused by the loss [INFERRED].
  - A first on/off test of `adaptive_link_enabled` seemed to fix it. It was a confound: the headset was moved back near the air unit at the same time.
  - Repeated alternately (on/off/on/off, same position): 835/835/836/835 frames per 10 s, quality 472/576/522/509, Quest TX 0 in every run [PROVEN]. Adaptive link is **not** the cause.
  - Check the physical link first. Compare the air unit's `wlan0 tx_packets` with what the Quest receives (`transport_analyze.py` sequence gaps).
- **XR mode gets no video after starting from the 2D screen** ("USB adapter in use — refusing to open", then `CreateRtlDevice error`). This was the adapter handoff race, fixed in `WfbngLink.cpp` on 2026-09-27; see [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27).

- **ADB to the Quest while it is on the air unit's APFPV AP.** hostapd there has `max_num_sta=1`, so the PC's Wi-Fi cannot join as a second client, and the air unit has no `iptables` for NAT. Use an SSH forward over the air unit's eth0 (dropbear allows local forwards): `python3 scripts/quest/air_tunnel.py`, then `adb connect 127.0.0.1:5595` [PROVEN: 2026-09-27]. A `plink -L` tunnel is blocked by the nested-SSH hook on this PC. Local port 5556 is already taken by the P10 car-modem ADB tunnel.
- **`transport_analyze.py` reported 65541 lost packets for one reordered RTP packet** (7575, 7577, 7576) [PROVEN: `ab_wfb4.pftrace`, 2026-09-27]. It counted the step back as a 16-bit wrap. Fixed: the loss count now unwraps with a signed step and reports reorders separately ([rtp_seq.py](../../scripts/quest-latch/rtp_seq.py), test [test_rtp_seq.py](../../scripts/quest-latch/test_rtp_seq.py)). `ab_segments.py` had the same code and now uses the same function.
- **Decoder stuck at ~78 ms after the air unit changed resolution, cause unknown** (2026-09-27). Once, after waybeam restarted from 1080p90 to 640×480 while PixelPilotXr ran, `Decoding:` averaged 78.7 ms (≈ 16 held frames, like the missing picture-order key in [real-link.md](real-link.md)), `WaitInputBuffer` rose to 6.5 ms, the app lost ~65 RTP packets/s and arrivals lagged up to 0.9 s behind capture [PROVEN: logcat + trace `ab_check640`]. Restarting the app cleared it (1.5 ms). Five controlled switches in both directions did **not** reproduce it, on the installed build or on a build that rebuilds the decoder on every SPS change, so that fix is unproven and was not kept ([patch](patches/decoder-reconfigure-on-sps-change.patch); details in [g2g-budget.md](g2g-budget.md#air-unit-levers-measured-in-one-trace-2026-09-27-slot-2)). Check for it after any air-unit restart: `bash scripts/quest/decode_watch.sh 20` (tens of ms = stuck; restart the app).
- **`VpnToUdpThread` burns a whole core** (2026-09-27): `top -H` on the Quest shows it at 100 % CPU in every app instance, healthy ones included. Upstream loop in `WfbNgVpnService.java` (the `vpnToUdpThread` `run()`): when `vpnInput.read()` returns 0 it `continue`s with no wait, i.e. a busy loop. It did not cause the decoder stall above (present in the healthy runs too), but it costs power and heat on the headset [PROVEN: `top -H -p <pid>`; code]. Not fixed yet.
