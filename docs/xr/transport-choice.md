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
   - Connect the **Quest first** so it gets `192.168.0.10`, the air unit's fixed video destination. Connect the PC's Wi-Fi card afterwards, to keep ADB over that network.
   - Measure with the same tools and the headset fixed: [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py), [link_measure.sh](../../scripts/quest/link_measure.sh), decode.
   - Caveats: the internal antenna is inside the headset; Wi-Fi power save dropped light UDP streams before (see [troubleshooting.md](troubleshooting.md)); the Quest leaves the home network.
2. **Station mode in devourer**, which gives APFPV through the RTL. Feasible: the WPA2 crypto, software CCMP and hardware ACK exist on the AP side. Still to write: client probe/auth/assoc, the supplicant side of the 4-way handshake, and a DHCP client. That is days of work, with risk. Only worth it if option 1 shows APFPV clearly better.

Recommendation given: option 1 first. **Status: not started.** The user handed this to another session with the mandate to test **both** APFPV methods, internal Wi-Fi **and** RTL via devourer station mode, and compare them with wfb-ng (see [HANDOFF.md](HANDOFF.md)).
