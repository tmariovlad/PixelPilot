# Transport choice: wfb-ng vs APFPV for the Quest (2026-09-27)

This records the discussion with the user on 2026-09-27: which transport should be the common boot default for the air unit and the ground, why wfb-ng was chosen, and why "APFPV with the RTL" is not possible today. The applied defaults are in [real-link.md § Boot defaults](real-link.md#boot-defaults-works-on-the-first-try-after-a-reboot-2026-09-27).

## The request

"The same optimal default on the air unit and the base, working on the first try after a reboot." The user then asked which transport is optimal for signal and latency ("care e optim în special pentru semnal și latență?").

## Decision: wfb-ng as the common default

| Criterion | wfb-ng | APFPV | Source |
|---|---|---|---|
| Quest + RTL8812AU | **works**: PixelPilot uses devourer in monitor/inject mode | **not possible today** (see below) | [PROVEN: devourer source] |
| Weak link | loses packets, FEC recovers some, picture degrades but stays | Wi-Fi association can drop, and the picture disappears for seconds until it reassociates; hidden retransmissions add latency spikes | [INFERRED: OpenIPC `repos/tasks/research/g2g-chain-detail/09-transport-apfpv-wfb.md` §1, §4] |
| Several grounds at once | yes (broadcast): Quest and GS together | no: video goes to one IP (`192.168.0.10`) | [PROVEN: `/etc/waybeam.json` `outgoing.server`] |
| Jitter | tunable with FEC K: inter-frame max ~59 ms at K8, ~11 ms at K4 | not exposed (rate adaptation inside aalink) | [PROVEN: OpenIPC `09-…md:35`] |
| Setup pitfalls | key pair + link id must match on both ends (see [real-link.md](real-link.md)) | none of those | [PROVEN: 2026-09-26/27] |
| G2G latency | **not measured head-to-head** after tuning; early numbers ~35–38 ms | the **20.3 ms** HIL record was on APFPV; early ~31 ms | [PROVEN: OpenIPC `docs/KNOWLEDGE.md:21`; the early comparison is flagged as suspect there] |

- Chosen: wfb-ng, because on this setup only wfb-ng reaches the Quest through the RTL, and it degrades gracefully.
- Open: latency. APFPV may be faster on the bench. APFPV stays available on demand: `linkmode-air.sh apfpv`, or `echo apfpv > /etc/linkmode.boot` to boot into it.

## "Connect with APFPV through the RTL": not possible without new code

- For APFPV the ground is a **Wi-Fi client**. It must associate with the air unit's AP, run the WPA2 4-way handshake as supplicant, decrypt CCMP data, get an IP by DHCP, and ACK unicast frames.
- On the Quest the RTL8812AU is driven by **devourer**, a userspace driver.
  - devourer implements the **AP side** of WPA2, and only as a test: `app/wfbngrtl8812/src/main/cpp/devourer/tests/ap_wpa2.cpp` — "devourer as a WPA2-PSK AP": authenticator, software CCMP, a DHCP server.
  - It has **no station/client mode** [PROVEN: the devourer source tree, `tests/` and `examples/`].
  - PixelPilot uses it only in monitor/inject mode.
- The HIL GS `.208` can do APFPV because its RTL8812AU runs the Linux kernel driver, which is a normal client.

## Options offered

1. **APFPV on the Quest through its internal Wi-Fi.** Works today, no new code.
   - Put the air unit in APFPV temporarily (`linkmode-air.sh apfpv`; the boot default stays wfb).
   - The user connects the Quest to SSID `OpenIPC` (PSK `12345678`) in Settings. Horizon ignores `adb shell cmd wifi connect-network`.
   - Connect the **Quest first** so it gets `192.168.0.10`, the air unit's fixed video destination. ~~Connect the PC's Wi-Fi card afterwards, to keep ADB over that network.~~ Not possible: the AP has `max_num_sta=1`. Keep ADB through an SSH forward over the air unit's eth0 instead ([air_tunnel.py](../../scripts/quest/air_tunnel.py); correction 2026-09-27).
   - Measure with the same tools and the headset fixed: [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py), [link_measure.sh](../../scripts/quest/link_measure.sh), decode.
   - Caveats: the internal antenna is inside the headset; Wi-Fi power save dropped light UDP streams before (see [troubleshooting.md](troubleshooting.md)); the Quest leaves the home network.
2. **Station mode in devourer**, which gives APFPV through the RTL. Feasible: the WPA2 crypto, software CCMP and hardware ACK exist on the AP side. Still to write: client probe/auth/assoc, the supplicant side of the 4-way handshake, and a DHCP client. That is days of work, with risk. Only worth it if option 1 shows APFPV clearly better.

Recommendation given: option 1 first. **Status (2026-09-27):** option 1 measured, see below; option 2 scoped, not built. The user handed this to another session with the mandate to test **both** APFPV methods, internal Wi-Fi **and** RTL via devourer station mode, and compare them with wfb-ng (see [HANDOFF.md](HANDOFF.md)).

## Measured: APFPV (Quest internal Wi-Fi) vs wfb-ng (RTL8812AU), 2026-09-27

> **CORRECTION (2026-09-27, the same night): this comparison is confounded and its conclusion is withdrawn.** The APFPV runs
> were at **~1000 kbit/s**, the wfb runs at **8000 kbit/s**.
> - **The mechanism** [PROVEN: `/opt/linkmode/linkmode-air.sh:117-126` and `:214-217` on `.132`]. On a switch to wfb the script saves
>   the current bitrate to `/opt/linkmode/.orig_bitrate`, if that file is absent and the rate differs from 8000, then caps waybeam at
>   `WFB_BITRATE=8000`. On a switch to APFPV it restores the saved value and deletes the file. A stale `1000` from the old
>   640x480 config was in the file before the slot, so every APFPV step set 1000, and the next wfb step saved 1000 again. After the
>   slot the file still held `1000`, written at 22:31 air time, i.e. at step 6 [PROVEN: `ls -la`, `cat` on `.132`]. The OpenIPC session
>   reset it to 8000 afterwards.
> - **The data agree** [INFERRED: 1.30–1.34 datagrams per frame on APFPV vs 8.5 on wfb (CSV); the air unit sent ~118 packets/s on
>   APFPV, i.e. ≤ ~1.3 Mbit/s at ≤ 1500 B per packet].
> - **Redone at 8000 kbit/s:** [slot 4A below](#re-measured-at-8000-kbits-on-both-arms-slot-4a-2026-09-27).
> - What survives: the method (alternating, same position, [ab_run.sh](../../scripts/quest/ab_run.sh)), the wfb numbers at 8000
>   kbit/s, and the ADB and `connect-network` findings. The APFPV loss, jitter and frame-spread numbers below are for 1 Mbit/s
>   and say nothing about APFPV at 8 Mbit/s. **Redo the APFPV runs at 8000 kbit/s** (check waybeam's bitrate on every step).

**Setup** (slot 1 on the air unit, coordinated with the OpenIPC session, which ran every switch on `.132`):
- Air unit and headset **in the same room, fixed for the whole slot**. The headset lay on a desk, Guardian paused, `prox_close`. The RTL stayed on the Quest's USB-C in every run.
- Air unit video: **1920x1080 @ 90 fps, H.264 CBR 8000 kbit/s** (sensor mode 2), waybeam `13b85893`, 12 dBm.
- **wfb-ng runs:** `wfb_tx -i 7669206 -p 0 -u 5600 -B 20 -M 2 -S 1 -L 1 -k 4 -n 6 -C 9000` on ch157, 20 MHz. PixelPilotXr receives through devourer on the RTL, adaptive link on (the default; note 2026-09-27: XR ignored the link prefs until commit `41984f1`, and on wfb the Quest then injects ~50 uplink frames/s when `tun0` is up, per another session's audit. Not measured in these runs, so a possible confound on the wfb arm), and the Quest's internal Wi-Fi stays on the home network (Zeul36, 5180 MHz).
- **APFPV runs:** `linkmode-air.sh apfpv` (hostapd WPA2-CCMP, ch157, VHT80, `max_num_sta=1`). The Quest's internal Wi-Fi was moved onto `OpenIPC` with `adb shell cmd wifi connect-network OpenIPC wpa2 12345678` (works for a saved network; see [troubleshooting.md](troubleshooting.md#horizon-os-quirks-quest-2)). The Quest got `192.168.0.10`, RSSI −42/−43 dBm, link 866 Mbit/s; the air unit saw it at −54 dBm. ADB went through an SSH forward over the air unit's eth0 ([air_tunnel.py](../../scripts/quest/air_tunnel.py)), because the AP takes one client only.
- **Order:** wfb1, apfpv1, wfb2, apfpv2, wfb3, apfpv3, wfb4 (alternating, N = 4 wfb / 3 APFPV).
- **Each run:** [ab_run.sh](../../scripts/quest/ab_run.sh), i.e. 10 s of logcat (decoded fps) and then a 9 s Perfetto trace analysed by [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py). The RTP counters are taken in `VideoPlayer::onNewRTPData`, after either transport, so the tool is the same for both.
- **Air-unit side** (sysfs only, read by the OpenIPC session): APFPV `tx_dropped` delta 0 in 6 windows of 2 s; wfb ~1170–1200 pkt/s injected, 0 dropped.
- Raw data: [data/2026-09-27-apfpv-vs-wfb-slot1.csv](data/2026-09-27-apfpv-vs-wfb-slot1.csv); traces and logs in `scripts/quest/out/ab_*` (gitignored).

**Results** [PROVEN: the CSV above; every value is per run]:

| Metric | wfb-ng via RTL (N=4) | APFPV via internal Wi-Fi (N=3) |
|---|---|---|
| Frames per second in the trace | 90.5–90.6 | 90.5 |
| RTP packets lost before the app, per ~8.5 s | 7, 3, 0, 5 | 0, 0, 0 |
| Datagrams per frame | 8.5–8.6 | 1.30–1.34 |
| One frame's spread on the air (first → last packet), mean | 7.76–7.77 ms | 0.07–0.10 ms |
| Transport excess at frame complete, p50 | 3.54–6.17 ms | 0.34–0.64 ms |
| Same, p95 | 8.14–13.49 ms | 2.34–3.01 ms |
| Same, max | 26.8–31.4 ms | 11.7–22.5 ms |
| Frame complete → decoded frame ready, p50 | 2.45–2.81 ms | 2.94–3.02 ms |

- **Jitter:** every APFPV run is below every wfb run on p50 and p95. The ranges do not overlap.
- **Loss:** APFPV delivered every RTP packet. wfb lost 0–7 packets per run after FEC 4/6. The picture showed no visible effect: every run decoded the full 90 fps.
- **Frame spread:** at MCS2 / 20 MHz a 1080p frame (~11 KB, 8.5 packets plus 2 FEC parity per 4) takes ~7.8 ms of airtime. At VHT80 with an 866 Mbit/s link it arrives as one burst [INFERRED: spread per run, same encoder].
- **Latency [INFERRED]:**
  - The wfb frame is complete ~7.7 ms after its first packet; the APFPV frame ~0.1 ms after. So APFPV delivers a complete frame about **7 ms earlier**.
  - Absolute capture → arrival cannot be compared between the two: the RTP timestamp base is random at every waybeam start ([HANDOFF.md](HANDOFF.md#coordination-with-the-openipc-project-user-decision-2026-09-27)), and a transport switch restarts waybeam. The absolute number needs the photodiode (HANDOFF item 7).
- **Decode** is the same on both paths, ~2.5–3.0 ms; the ~0.4 ms gap is within run-to-run noise.
- **Hidden retransmissions** on APFPV cannot be counted from the air unit. The 8812eu driver reports no tx retries in `iw station dump`. Its `/proc/.../tx_stat` exists but was not read, to avoid the `/proc` reads suspected in the earlier reboot. Whatever retries there were fit inside the jitter numbers above.

**What this means for the boot default** [WITHDRAWN 2026-09-27: APFPV was at 1000 kbit/s, see the correction above; kept as written]:
- At this range (same room), APFPV through the Quest's own Wi-Fi is better on every measured axis.
- It has no FEC and no MCS2 serialization. Its weak-link behaviour (association loss, hidden retries) was **not** tested here; through walls, see [real-link.md](real-link.md#tx-power-and-radio-settings-through-walls-2026-09-27).
- wfb-ng at MCS2 pays ~7.8 ms of airtime per 1080p frame. A higher MCS on wfb is the obvious next lever: HANDOFF item 3, hot MCS via `set_radio`.
- The boot default is unchanged (wfb). A fair decision needs the wfb MCS bracket, and a range test of both transports at the same positions.


## Re-measured at 8000 kbit/s on both arms (slot 4A, 2026-09-27)

Runs from 12:47 to 12:57.

**What changed from slot 1:** the bitrate is verified on every step. The OpenIPC session deployed the `.orig_bitrate` fix ("O109", `linkmode-air.sh` md5 `5f0802cd`). After each switch it read `"bitrate":8000` from waybeam's `config.json` before the measurement [PROVEN: its step reports; my own read at epoch 1790502460]. On the Quest, datagrams per frame are checked per run: 8.47–8.77 on both arms. On APFPV the air unit sent ~775–790 pkt/s, 0 dropped.

**Same setup as slot 1**, except:
- the app build is `33f098a2` (installed 12:46:39, with the VpnToUdpThread fix of another session);
- adaptive link is at the native default (on). XR did not apply the link prefs until commit `41984f1`.
- On wfb the Quest injects ~50 uplink frames/s on the video channel when `tun0` is up, according to another session's audit; APFPV has no such traffic. **Not measured in these runs** (no devourer TX counter was read), so it stays a possible confound on the wfb arm [SPECULATION: ~50 short MCS0 frames/s ≈ a few % of airtime].

**Valid runs** (alternating, same app instance, headset and air unit fixed) [PROVEN: [data/2026-09-27-apfpv-vs-wfb-slot4a.csv](data/2026-09-27-apfpv-vs-wfb-slot4a.csv)]:

| Run | Datagrams/frame | RTP lost | Frame spread on air, mean | Excess p50 / p95 / max | Decode p50 |
|---|---|---|---|---|---|
| s4_wfb1 | 8.77 | 7 | 7.92 ms | 2.04 / 8.98 / 25.7 ms | 2.31 ms |
| s4_apfpv1 | 8.51 | 0 | 0.12 ms | 0.22 / 1.35 / 10.0 ms | 2.26 ms |
| s4_wfb2 | 8.47 | 1 | 7.66 ms | 6.05 / 12.83 / 31.4 ms | 2.30 ms |
| s4_apfpv2 | 8.51 | 0 | 0.14 ms | 0.31 / 2.20 / 8.5 ms | 2.38 ms |

- **N = 2 per arm, not the planned 3 wfb.** The last wfb step was lost to an app problem (below).
- At the same 8000 kbit/s, APFPV again shows 0 RTP loss vs 1–7, a frame on the air in ~0.13 ms vs ~7.8 ms, and a lower jitter p95 (1.35–2.20 vs 8.98–12.83 ms) [PROVEN, N = 2 each]. The ranges do not overlap.
- Decode is equal (~2.3 ms).
- [INFERRED: frame spread] APFPV delivers the complete 1080p frame ~7.5 ms earlier. Absolute latency is still not measured (random RTP base per waybeam start; needs the photodiode).

**Runs excluded from the comparison:**
- **The app died at 12:53:12** (`am_proc_died` pid 8192, no crash entry; the build was unchanged). This was between s4_apfpv2 and s4_wfb3, while the Quest moved back to the home network. It came back through the 2D activity.
- **The restarted instance measured differently** (s4_wfb3, s4_wfb3b): bursty RX (44–45 % of packets < 100 µs apart), no link-quality or uplink lines, excess p95 ~28 ms, and 72 / 9 lost.
- **After a clean force-stop and XR relaunch** (s4_wfb3c, s4_wfb3d), the link quality stayed at ~270–280, against ~945 before, with 110 / 26 lost. The air unit reported 0 dropped. The cause is unknown [SPECULATION: the adapter came back in a different state, or something moved; both unchecked]. See [troubleshooting.md](troubleshooting.md).
- All eight runs are in the CSV, each with its status.

**Conclusion** [INFERRED, same-room only, N = 2 per arm]:
- At 1080p90 / 8000 kbit/s in one room, APFPV through the Quest's own Wi-Fi beats wfb-ng through the RTL at MCS2 on loss, jitter and frame delivery.
- Most of the gap is wfb's MCS2 / 20 MHz airtime (~7.8 ms per frame).
- Not tested: range and through-wall behaviour, where APFPV's association and hidden retries matter, and wfb at a higher MCS. Another session measured MCS4 / 12 Mbit at −1.2 ms in slot 3 (see [g2g-budget.md](g2g-budget.md)).
- The boot default stays wfb until those two are measured.

**Option 2 (APFPV through the RTL):** progress in [station-mode.md](station-mode.md); scoped in [research/2026-09-27-devourer-station-scope.md](research/2026-09-27-devourer-station-scope.md), ~6–8 days of work. The first step is a half-day go/no-go gate: the 8812AU's hardware ACK is documented as degraded as a responder (97 % delivery at ~7 retries, devourer `docs/scheduled-mac.md:182-185`). A slot for that gate (air on APFPV, RTL on the PC) is queued with the coordinator.
