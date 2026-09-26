# Handoff: PixelPilotXr + Quest 2 + HIL air unit (state at 2026-09-27)

Read this together with the repo [CLAUDE.md](../../CLAUDE.md). Everything below is documented in detail in the linked files.

## Mandate for the receiving session (user, 2026-09-27)

**Test APFPV on the Quest by both methods and compare with wfb-ng through the RTL:**
1. **Internal Wi-Fi.** The Quest joins the air unit's AP (option 1 in [transport-choice.md](transport-choice.md)); no new code.
2. **Through the RTL8812AU.** This needs **station/client mode in devourer** (option 2): client probe/auth/assoc, supplicant side of the WPA2 4-way handshake, software CCMP decrypt, DHCP client, then hand the UDP video to PixelPilot. Building blocks exist on the AP side: `devourer/tests/ap_wpa2.cpp`, software CCMP, hardware ACK.

Measure every method at the same position with the same tools (loss, decode fps, transport excess / jitter, latency where possible), with the air unit's side measured over eth0. Use the result to decide the boot default (currently wfb-ng).

## State right now

| Where | State | Details |
|---|---|---|
| **Air unit `.132`** (SSC338Q, waybeam `13b85893`) | **Boots on wfb-ng**: `/etc/linkmode.boot` = `wfb`, link id 7669206, FEC 4/6, MCS2, STBC 1, LDPC 1, OpenIPC default key. 12 dBm (default; runtime `iw` changes are lost on reboot). Ethernet cable connected (reachable at `192.168.100.132`, root/12345). Currently in **another room**, so the link through walls is poor. | [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27) |
| **Quest 2** (`192.168.100.114:5555`, Wi-Fi ADB) | PixelPilotXr (`com.openipc.pixelpilot.xr`) installed; build defaults channel 157 + OpenIPC gs.key; **autostarts XR** on Library launch / adapter attach. Guardian restored (`guardian_pause 0`). RTL8812AU on USB-C. The user's release PixelPilot 0.21.0 is untouched. | [xr-quest.md](../xr-quest.md), [troubleshooting.md](troubleshooting.md) |
| **HIL GS `.208`** (OPi5) | **Not aligned:** offline during the change. It still has the HIL gs.key and runs `wfb_rx` without `-i`, so it cannot receive the air unit until it gets the OpenIPC gs.key and `-i 7669206`. The `/linkmode` skill's `linkmode-gs.sh` already has `LINK_ID`; it needs a deploy. | [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27) |
| **PC Wi-Fi card "Wi-Fi 2"** | May still be associated to the air unit's AP when the air unit is in APFPV, where it takes `192.168.0.10`. Disconnect it before the GS or the Quest needs `.10`. | [troubleshooting.md](troubleshooting.md) |

## Open items, most valuable first

1. **wfb-ng vs APFPV latency and robustness on the Quest.** Option 1 in [transport-choice.md](transport-choice.md): APFPV through the Quest's internal Wi-Fi vs wfb-ng through the RTL, same position, same tools. It decides whether the boot default should change. Option 2 (devourer station mode, i.e. APFPV through the RTL) only if option 1 shows APFPV clearly better.
2. **Align the HIL GS `.208`** with the new wfb defaults (key + link id), or put the air unit back on APFPV for HIL 20 ms work.
3. **Capacity / "more speed" test**, with the air unit and the headset in the same room. MCS 2→3→4… at a constant bitrate, then raise the bitrate, and measure loss (`scripts/quest/link_measure.sh`). The real video rate is ~9.2 Mbit/s, not the configured 1000; the radio is ~73 % busy at MCS2. See [real-link.md § TX power](real-link.md#tx-power-and-radio-settings-through-walls-2026-09-27).
4. **Through-wall range.** TX power (12→23 dBm) had no effect; MCS0 cannot carry the stream; STBC+LDPC are now the default. The physical checks are still open: antennas on the air unit and the RTL, and the RTL's orientation.
5. **Unexplained air-unit reboot** at ~21:23 on 2026-09-27, at 12 dBm. Candidates: reading `/proc/net/rtl88x2eu/wlan0/tx_power_idx` while injecting, a watchdog under load 7–14, or the supply. Avoid long `/proc` reads during injection until this is understood.
6. **Phase lock, air side.** The headset side is built and proven; the air unit needs to receive `PPXR1` and nudge VMAX. See [compositor-phase.md](compositor-phase.md).
7. **Photodiode G2G** on the Quest, to replace the inferred panel term in [g2g-budget.md](g2g-budget.md) (estimated ~31 ms).
8. **Hot-plug robustness:** replugging the RTL crashed the app twice (devourer EEPROM exception; libusb segfault in `~RtlJaguarDevice`). Not fixed; see [troubleshooting.md](troubleshooting.md).

## Session hygiene

- Test the Quest with Guardian paused (`setprop debug.oculus.guardian_pause 1` plus `am broadcast -a com.oculus.vrpowermanager.prox_close`), and restore afterwards (`guardian_pause 0` plus `automation_disable`).
- A pending USB-permission dialog blocks immersive launches: close it, or `am force-stop com.oculus.os.vrusb`.
- On a real link, measure both ends before concluding anything. Repeat any on/off test alternately with the setup physically unchanged (rule in [CLAUDE.md](../../CLAUDE.md)).
