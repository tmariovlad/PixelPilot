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
| **Air unit `.132`** (SSC338Q, waybeam `13b85893`) | **Boots on wfb-ng**: `/etc/linkmode.boot` = `wfb`, link id 7669206, FEC 4/6, MCS2, STBC 1, LDPC 1, OpenIPC default key. 12 dBm (default; runtime `iw` changes are lost on reboot). Ethernet cable connected (reachable at `192.168.100.132`, root/12345). Moved into the **same room** as the Quest for the air-unit slots on 2026-09-27 (it was in another room before, where the link through walls is poor). **Video since 2026-09-27: 1920x1080@90** (sensor mode 2, h264 CBR 8000, persistent; set by session pixelpilot-xr-22, reported live, not re-verified here). Previous 640x480@167 is backed up at `/etc/waybeam.json.bak-640x480-20260927`; the latency numbers in [g2g-budget.md](g2g-budget.md) are for 640x480@167. | [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27) |
| **Quest 2** (`192.168.100.114:5555`, Wi-Fi ADB) | PixelPilotXr (`com.openipc.pixelpilot.xr`) installed; build defaults channel 157 + OpenIPC gs.key; **autostarts XR** on Library launch / adapter attach. Guardian restored (`guardian_pause 0`). RTL8812AU on USB-C. The user's release PixelPilot 0.21.0 is untouched. | [xr-quest.md](../xr-quest.md), [troubleshooting.md](troubleshooting.md) |
| **HIL GS `.208`** (OPi5) | **Not aligned:** offline during the change. It still has the HIL gs.key and runs `wfb_rx` without `-i`, so it cannot receive the air unit until it gets the OpenIPC gs.key and `-i 7669206`. The `/linkmode` skill's `linkmode-gs.sh` already has `LINK_ID`; it needs a deploy. | [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27) |
| **PC Wi-Fi card "Wi-Fi 2"** | May still be associated to the air unit's AP when the air unit is in APFPV, where it takes `192.168.0.10`. Disconnect it before the GS or the Quest needs `.10`. | [troubleshooting.md](troubleshooting.md) |

## Open items, most valuable first

1. **wfb-ng vs APFPV latency and robustness on the Quest.** Option 1 in [transport-choice.md](transport-choice.md): APFPV through the Quest's internal Wi-Fi vs wfb-ng through the RTL, same position, same tools. It decides whether the boot default should change. Option 2 (devourer station mode, i.e. APFPV through the RTL) only if option 1 shows APFPV clearly better.
   - **Option 1 redone at 8000 kbit/s (slot 4A, N = 2 per arm):** APFPV 0 vs 1–7 RTP losses, jitter p95 1.4–2.2 vs 9.0–12.8 ms, frame on air ~0.13 vs ~7.8 ms ([results](transport-choice.md#re-measured-at-8000-kbits-on-both-arms-slot-4a-2026-09-27)). Open before changing the boot default: range / through-wall for both, wfb at a higher MCS. The later wfb runs dropped (quality ~270 vs ~945) because the user moved the Quest to the balcony at ~12:53; the valid runs are from before the move.
   - **Slot 1 (superseded) was CONFOUNDED.** The APFPV steps restored a stale `1000` from `/opt/linkmode/.orig_bitrate`, so APFPV ran at ~1 Mbit/s and wfb at 8 Mbit/s ([correction](transport-choice.md#measured-apfpv-quest-internal-wi-fi-vs-wfb-ng-rtl8812au-2026-09-27)). As first written (2026-09-27, slot 1, same room, N = 4 wfb / 3 APFPV alternating): APFPV has 0 RTP loss vs 0–7 per run on wfb; jitter p95 2.3–3.0 ms vs 8.1–13.5 ms; a frame arrives in ~0.1 ms vs ~7.8 ms of MCS2 airtime. [Results](transport-choice.md#measured-apfpv-quest-internal-wi-fi-vs-wfb-ng-rtl8812au-2026-09-27). The boot default stays wfb until the wfb MCS bracket (item 3) and a range test of both are done.
   - **Option 2:** [station-mode.md](station-mode.md) (W0 gate harness built, run procedure written); scoped in [research/2026-09-27-devourer-station-scope.md](research/2026-09-27-devourer-station-scope.md), ~6–8 days. First a half-day go/no-go gate on the 8812AU hardware ACK: slot 4 with the coordinator, air on APFPV and the RTL on the PC.
2. **Align the HIL GS `.208`** with the new wfb defaults (key + link id), or put the air unit back on APFPV for HIL 20 ms work.
3. **Capacity / "more speed" test**, with the air unit and the headset in the same room. MCS 2→3→4… at a constant bitrate, then raise the bitrate, and measure loss (`scripts/quest/link_measure.sh`). The real video rate is ~9.2 Mbit/s, not the configured 1000; the radio is ~73 % busy at MCS2. See [real-link.md § TX power](real-link.md#tx-power-and-radio-settings-through-walls-2026-09-27).
4. **Through-wall range.** TX power (12→23 dBm) had no effect; MCS0 cannot carry the stream; STBC+LDPC are now the default. The physical checks are still open: antennas on the air unit and the RTL, and the RTL's orientation.
5. **Unexplained air-unit reboot** at ~21:23 on 2026-09-27, at 12 dBm. Candidates: reading `/proc/net/rtl88x2eu/wlan0/tx_power_idx` while injecting, a watchdog under load 7–14, or the supply. Avoid long `/proc` reads during injection until this is understood.
6. **Phase lock, air side.** The headset side is built and proven; the air unit needs to receive `PPXR1` and nudge VMAX. See [compositor-phase.md](compositor-phase.md).
7. **Photodiode G2G** on the Quest, to replace the inferred panel term in [g2g-budget.md](g2g-budget.md) (estimated ~31 ms).
8. **Hot-plug robustness:** replugging the RTL crashed the app twice (devourer EEPROM exception; libusb segfault in `~RtlJaguarDevice`). Not fixed; see [troubleshooting.md](troubleshooting.md).

## Coordination with the OpenIPC project (user decision, 2026-09-27)

- **Ownership.** pixelpilot-xr sessions own the app, the Quest and the RTL on the Quest. The OpenIPC project (`c:/xampp/htdocs/openipc-low-latency-and-others-video`) owns the air unit `.132` and the GS `.208`. Each session edits only its own repo.
- **Writes on `.132`/`.208`** (config, transport, reboot, TX power) are executed by the OpenIPC side after the user confirms there. Pixelpilot sessions send their requests through the pixelpilot coordinator session, signal before/after each step, and measure on the Quest. Short read-only reads on `.132` are fine; avoid long `/proc` reads during injection (item 5 above).
- **Approvals.** Since 2026-09-27 the user routes air/GS approvals through the pixelpilot coordinator session. The OpenIPC coordinator treats its START as user approval for the announced plan only; anything destructive or persistent outside the plan (flash, reboot, `/rom`, a new boot default) goes to the user separately.
- **Slot log (2026-09-27/28).** Each slot's result lives in its topic file; this is only the order and status.
  - 1: APFPV vs wfb at 1080p90. **Withdrawn**: APFPV ran at ~1000 kbit/s ([transport-choice.md](transport-choice.md)).
  - 2: bitrate/FEC latency A/B at 640x480@167. Done ([g2g-budget.md](g2g-budget.md)).
  - 3: MCS × bitrate A/B at 1080p90. Done ([g2g-budget.md](g2g-budget.md)). The visual check with the user wearing the headset is still open.
  - 3b: VpnToUdpThread CPU fix, verified on the Quest ([troubleshooting.md](troubleshooting.md)).
  - 4A: APFPV vs wfb redone at 8000 kbit/s on both. Done ([transport-choice.md](transport-choice.md)).
  - 3c: stopAudio SIGABRT fix, verified.
  - 3d: XR now applies the link options; adaptive-link uplink on/off showed no visible effect on the balcony link ([troubleshooting.md](troubleshooting.md)).
  - Still open: 4B (hardware-ACK go/no-go, RTL moved to the PC, needs the user) and the slot-3 visual check.
  - Since ~12:53 on 2026-09-28 the Quest is on the balcony (weaker link).
- **waybeam `13b85893` constraints**, read from source by the OpenIPC session, not tested live [INFERRED: waybeam_venc f8742fe]: `bitrate` applies live but is also written to `/etc/waybeam.json`, so every A/B needs an explicit revert (`venc_api.c:399`, `:1923-1930`). `sliceSend` is not in the HTTP API (JSON + restart only, and only with `sliceRows>0`). `sliceRows`/`lowDelay` need a restart (`venc_api.c:455-456`). **`lowDelay=true` on Star6E drops VENC to 0 fps and persists across reboot** (ADR-032, `star6e_pipeline.c:2300`); do not use it. FEC K changes hot via `wfb_setfec` (control port `-C 9000`); restarting `wfb_tx` on the 8822EU has caused NO-CARRIER that needed a reboot. MCS should likewise change hot through wfb-ng's `CMD_SET_RADIO` on the same control port (`wfb_tx_cmd <port> set_radio`, wfb-ng `tx.cpp:919-955`), sending every radio field so STBC/LDPC are not silently reset; not verified on the air unit yet. **The RTP timestamp base, sequence number and SSRC are random at every waybeam start** (`rtp_session.c:15,26-28`; the timestamp then follows the VENC PTS, `star6e_hevc_rtp.c:44-53`), so a latency A/B that restarts waybeam loses the capture→arrival constant between segments. `sliceRows` counts CTU rows (16-px MB rows on H.264, `venc_config.h:118`). **Slices are a closed lever:** measured live on `.132` on 2026-06-27 by the OpenIPC project (HB-50; OpenIPC repo `repos/tasks/hil-build/40-latency-measured-softonly.md` § A/B sliceRows). `sliceSend=true` raised encode time from 4 to 27–30 ms and dropped the rate to 45–60 fps, whatever the slice size; `sliceRows` alone (with `sliceSend=false`) had no effect.

## Session hygiene

- Test the Quest with Guardian paused (`setprop debug.oculus.guardian_pause 1` plus `am broadcast -a com.oculus.vrpowermanager.prox_close`), and restore afterwards (`guardian_pause 0` plus `automation_disable`).
- A pending USB-permission dialog blocks immersive launches: close it, or `am force-stop com.oculus.os.vrusb`.
- On a real link, measure both ends before concluding anything. Repeat any on/off test alternately with the setup physically unchanged (rule in [CLAUDE.md](../../CLAUDE.md)).
