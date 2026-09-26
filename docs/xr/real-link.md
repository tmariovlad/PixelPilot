# Real link: Quest 2 + RTL8812AU + OpenIPC air unit

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

Setup (APFPV vs wfb, keys, link id) and the picture-order finding on the real OpenIPC stream. The branch-by-branch G2G budget measured on this link is in [g2g-budget.md](g2g-budget.md).

## Boot defaults: works on the first try after a reboot (2026-09-27)

The user asked for one optimal default on the air unit and on the ground, so that video appears after a reboot without manual steps.

**Why wfb-ng is the default transport:** (full discussion and the APFPV options: [transport-choice.md](transport-choice.md))
- It is broadcast with FEC and has no association or ACK retransmissions, so a weak link degrades instead of dropping out. APFPV loses its association on a bad link and hides its retransmissions [INFERRED: OpenIPC `repos/tasks/research/g2g-chain-detail/09-transport-apfpv-wfb.md` §1, §4].
- It is the only transport the Quest's RTL8812AU path can receive.
- Latency head-to-head (wfb tuned vs APFPV) is **not measured yet**. The 20.3 ms HIL record was on APFPV, and the early wfb numbers are flagged as suspect in that project. APFPV stays available on demand through `linkmode-air.sh apfpv`.

**Air unit (HIL `.132`), persistent** [PROVEN 2026-09-27: reboot came up on its own as `AIR_STATE=wfb`, `wfb_tx -i 7669206 -p 0 -u 5600 -K … -B 20 -M 2 -S 1 -L 1 -k 4 -n 6`, ~1354 pkt/s]:
- `/etc/linkmode.boot` contains `wfb`. An `/etc/rc.local` hook runs `sleep 30; /opt/linkmode/linkmode-air.sh $(cat /etc/linkmode.boot)` after `waybeam_launch`.
- `linkmode-air.sh` defaults, all overridable by `LINKMODE_*` env:
  - link id **7669206**;
  - FEC **4/6** (the OpenIPC project's jitter lever: inter-frame max ~59 ms at K8 vs ~11 ms at K4);
  - MCS 2;
  - **STBC 1, LDPC 1** (wfb-ng `master.cfg` defaults; the Quest RTL decodes them).
- `/opt/linkmode/drone.key` holds the OpenIPC firmware default key (md5 `24767056…`). The previous HIL key is in `drone.key.hil`.
- Revert: `cp /opt/linkmode/linkmode-air.sh.bak-pre-bootdefault /opt/linkmode/linkmode-air.sh; cp /opt/linkmode/drone.key.hil /opt/linkmode/drone.key; rm /etc/linkmode.boot`.
- The deploy copy lives in the `/linkmode` skill (`~/.claude/skills/linkmode/scripts/`) and is synced with the air unit (md5 `8ebc9c56`).

**Quest (PixelPilotXr), build defaults** [PROVEN 2026-09-27: after the prefs were wiped, a Library launch went straight to XR, imported the OpenIPC key, used channel 157 and decoded the air unit's stream]:
- `xr_autostart` defaults on for Meta headsets (`LatencyExperiments`). A fresh launch from the Library or on adapter attach opens XR directly. Leaving XR returns to the 2D screen for settings. The 2D menu toggle is "Start in XR".
- The XR build's default channel is **157** (`app/src/debug/res/values/link_defaults.xml`; main build 161) and its default `gs.key` is the **OpenIPC firmware default** (`app/src/debug/assets/gs.key`).

**HIL ground station `.208`, not done yet (it was offline):**
- It needs the OpenIPC default `gs.key` in `~/linkmode/gs.key`; back up the HIL one first.
- It needs `wfb_rx -i 7669206`. The skill's `linkmode-gs.sh` already has `LINK_ID`; deploy it when `.208` is reachable.

**Adapter handoff race, fixed** (`WfbngLink.cpp`):
- With autostart, the 2D activity starts the RTL, and XR asks for it ~1.5 s later. devourer refused with "USB adapter in use — refusing to open". Its per-adapter lock lived inside the device object, which stayed in `rtl_devices` after the RX loop ended, so it was never released. XR gave up with no retry [PROVEN: logcat 2026-09-27 00:42].
- Fix:
  1. `run()` now erases the device after `Stop()`, while the handle is still valid, which releases the lock.
  2. Before claiming the interface, the new owner waits for the lock (250 ms steps, max 10 s) and hands it to `CreateRtlDevice`, as devourer's contract allows (`WiFiDriver.cpp:92-100`).
- Verified: "adapter free after waiting 2500 ms", then the decoder configured on the live stream. The manual "Launch XR" path goes through the same code.

## Watch the air unit's video on the Quest (step by step)

This is for the HIL air unit (SSC338Q, `.132`), which boots into APFPV with a key paired to the HIL GS. Why each step is needed: see "First real link" below.

**1. Reach the air unit's shell** (SSH, `root` / `12345`). Use eth0 `192.168.100.132` if the cable is plugged in. Otherwise use the air unit's AP through the PC's Wi-Fi card:

```bash
netsh wlan add profile filename="C:\xampp\htdocs\pixelpilot-xr\scripts\quest\openipc-wlan.xml"   # once; SSID OpenIPC, PSK 12345678
bash scripts/quest/wait_air.sh                    # air unit = 192.168.0.1
```

**2. On the air unit: put the OpenIPC default key in RAM and start wfb-ng with PixelPilot's link id.** Nothing persistent changes, except waybeam's destination, which step 7 restores:

```sh
echo u7ftboOkaoqbihKg+Y7OK9yXhwW4IEcBsghfooyse0YOBcSKYZX7cJIcdHpm6DwC5kC9a761slFTepiidBaiYw== | base64 -d > /tmp/drone-openipc.key
chmod 600 /tmp/drone-openipc.key && mount --bind /tmp/drone-openipc.key /opt/linkmode/drone.key
sed 's#-p 0 -u 5600 -K "$LM/drone.key"#-i 7669206 -p 0 -u 5600 -K "$LM/drone.key"#' /opt/linkmode/linkmode-air.sh > /tmp/linkmode-air-pp.sh
chmod +x /tmp/linkmode-air-pp.sh && (nohup /tmp/linkmode-air-pp.sh wfb > /tmp/linkmode.log 2>&1 &)
```

- The key is the public OpenIPC default `drone.key` (`OpenIPC/firmware: general/package/legacy/wifibroadcast/files/drone.key`, md5 `24767056…`).
- The AP disappears after ~10 s, which is expected. The air unit then transmits wfb-ng on its AP channel (157).
- If the AP comes back after ~30 s, the switch failed and the script reverted automatically. Check that waybeam streams (`grep fps= /var/lib/misc/waybeam-boot.log`, `wlan0 tx_packets`).

**3. Plug the RTL8812AU into the Quest's USB-C.** If Horizon asks which app should use it, choose PixelPilotXr.

**4. Give PixelPilotXr the matching key and the channel.**
- **From the PC:** `python3 scripts/quest/set_link_prefs.py scripts/quest/keys/raw-legacy-gs.key 157`. The key is the OpenIPC default `gs.key` from the same firmware folder; `scripts/quest/keys/` is gitignored. Fetch it with `curl -sL https://raw.githubusercontent.com/OpenIPC/firmware/master/general/package/legacy/wifibroadcast/files/gs.key -o scripts/quest/keys/raw-legacy-gs.key`.
- **Or in the app:** in the 2D screen, open the menu and select that `gs.key`, then set channel 157.

**5. Put the headset on, open PixelPilotXr from the Library.** The 2D screen appears. Open its menu → **Video → Launch XR (Quest)**. From the PC, this does the same:

```bash
adb shell am start -a android.intent.action.MAIN -c org.khronos.openxr.intent.category.IMMERSIVE_HMD -n com.openipc.pixelpilot.xr/com.openipc.pixelpilot.XrVideoActivity
```

**6. Check.** The video appears on the head-locked panel. The stats panel shows a `link:` line with an RSSI. `bash scripts/quest/link_check.sh 15` should report `quality` values other than `-1024` and `Decoded Frames` counting up.

**7. Afterwards, restore the air unit:** `linkmode-air.sh apfpv`. See "Restoring the air unit after a test" below; a power cycle alone is not enough.

**Verified end to end on 2026-09-27** with the steps above [PROVEN]:
- the XR activity was in front;
- ~167 decoded frames/s, 835 per 10 s, in 4 runs;
- link quality 470–580;
- 0 decrypt errors after the session key arrived.

## Diagnosing a bad link (2026-09-27)

Measure both ends before changing anything. The air unit's side needs eth0 (`192.168.100.132`), because in wfb mode it has no AP.

**Air unit: is everything being transmitted?**

```sh
tr '\0' ' ' < /proc/$(pidof wfb_tx)/cmdline   # expect -i 7669206 -p 0 -B 20 -M 2 -k 8 -n 12
iw dev wlan0 info                              # type monitor, channel 157, 20 MHz, txpower
A=$(cat /sys/class/net/wlan0/statistics/tx_packets); sleep 2; B=$(cat /sys/class/net/wlan0/statistics/tx_packets); echo $((B-A))
cat /sys/class/net/wlan0/statistics/tx_dropped
grep fps= /tmp/waybeam-switch.log | tail -1   # waybeam alive
```

Baseline on 2026-09-27 [PROVEN]:
- ~2627 packets per 2 s, i.e. **~1313 pkt/s** (5 data packets/frame × 166 fps plus FEC 8/12 parity);
- `tx_dropped` delta 0;
- txpower 12 dBm;
- waybeam 166.47 fps.

**Quest: what arrives?**
- Link quality: `quality N` in the log every 100 ms, from −1024 (nothing) to +1024. Healthy: +470…+580.
- The adaptive-link uplink line `message <epoch>:<q>:<q>:<recovered/s>:<lost/s>:<q>:<snr>:0:-1:<fec>:<idr>`. These are the fields as `WfbngLink.cpp:518-529` actually formats them; the comment above that code calls field 6 `rssi`, but the value written there is the quality. Example of a bad link: `…:7:790:1455:31.59:…`, i.e. 7 packets recovered and **790 lost per second** at **SNR 31.6 dB**.
- Per packet: a Perfetto trace plus [transport_analyze.py](../../scripts/quest-latch/transport_analyze.py), which reports "sequence gaps" (packets lost after FEC).

**How to read it:**
- The air unit transmits everything and the Quest misses most of it, while the packets that do arrive have a strong SNR. That is a **path** problem (distance, walls, antenna orientation, a body in the way), not a software problem. On 2026-09-27 the air unit was in another room: 1295 packets received vs 6550 missing in 8.6 s.
- Under heavy loss the Quest RTL also transmitted ~100 pkt/s, most likely keyframe requests [INFERRED]. That is a symptom, not the cause.
- **Controlled re-check (2026-09-27, later):** air unit moved back to the other room, **adaptive link off** (Quest TX = 0 packets in 5 s). The air unit sent 1292 pkt/s with 0 dropped, yet the Quest lost ~559 pkt/s (uplink line `…:0:559:…:35.19:…`, SNR 35 dB), quality −193, ~4 decoded fps [PROVEN]. The same air unit and headset in one room: ~167 fps. The loss follows the position, with no transmission from the Quest involved. Unused levers for range: air txpower is 12 dBm (`iw dev wlan0 info`), and the MCS is `-M 2` with FEC 8/12 [SPECULATION: a higher txpower or a lower MCS would extend range; not tested].
- Repeat any on/off test alternately with **the setup physically unchanged**. A one-shot A/B of `adaptive_link_enabled` looked decisive until repeats showed no difference: 835/835/836/835 frames per 10 s. See [troubleshooting.md](troubleshooting.md).

## TX power and radio settings through walls (2026-09-27)

**Setup:** the air unit in another room, the headset fixed. For each setting the Quest was measured for 10 s with [link_measure.sh](../../scripts/quest/link_measure.sh), which reports decoded fps, quality, and lost/s + SNR from the uplink line. The air unit was measured over eth0.

**Changing TX power at runtime works and is not persistent:**
- Command: `iw dev wlan0 set txpower fixed <mBm>` on the RTL8822EU (driver `8812eu`, monitor mode).
- The driver applies it to the rates wfb uses: `/proc/net/rtl88x2eu/wlan0/tx_power_idx`, rows `MCS2 1T`. Path A goes from idx 49 at 12 dBm to idx 93 at 23 dBm; path B from 40 to 84 [PROVEN].
- A reboot restores 12 dBm. There is no `wlanpwr` in `fw_printenv`, so 12 dBm is the default.

**Temperatures** (SoC: `/sys/devices/virtual/mstar/msys/TEMP_R`; Wi-Fi chip per RF path: `/proc/net/rtl88x2eu/wlan0/thermal_state`): 44–46 °C SoC and 37–42 °C chip across 12–23 dBm. That is far below the stop limits used (80 °C SoC, 70 °C chip) [PROVEN].

| Air setting | Quest lost/s | decoded fps | quality | SNR |
|---|---|---|---|---|
| 12 dBm, MCS2 | 630 | 2 | −2 | 41.0 |
| 16 dBm, MCS2 | 586 | 1 | −89 | 37.5 |
| 20 dBm, MCS2 | 619 | 2 | 212 | 42.0 |
| 23 dBm, MCS2 | 654 | 1 | −2 | 41.8 |
| 12 dBm, MCS2 (restart) | 667 | 1 | −208 | 31.7 |
| 12 dBm, MCS0 | 591 | 0 | −192 | 31.8 |
| 12 dBm, MCS2 + STBC + LDPC | 657 | 6 | −90 | 36.3 |

- **+11 dB of TX power does not change the loss** through walls (bracket 12/16/20/23 dBm) [PROVEN]. The packets that do arrive are strong (SNR 31–42 dB). So this is not a simple link-budget shortfall at the air unit's transmitter. Physical checks are still open: antennas on the air unit and on the RTL, and the RTL's orientation on the headset.
- **MCS0 cannot carry this stream:** the air unit only got ~526 pkt/s out instead of ~1270.
- **STBC + LDPC:** 6 vs 1 fps in a single run, not proven.

**What the air unit really sends** (`/tmp/wfbtx.log` `PKT` counters) [PROVEN]:
- **~844 pkt/s of ~1357 B from waybeam, ≈ 9.2 Mbit/s of video.** `waybeam.json` says `bitrate: 1000`, which does not match.
- ~1270 pkt/s ≈ 14 Mbit/s injected with FEC 8/12. At MCS2, 20 MHz (19.5 Mbit/s PHY) the air unit's radio is **~73 % busy**. That is the starting point for any "more speed" test.

**Incident:** the air unit rebooted at ~21:23 during this test. Just before, TX power had been set to 23 dBm and back to 12 dBm while `/proc/.../tx_power_idx` was being read, and that read took > 30 s under load 7–14. The cause is unknown [SPECULATION: a power draw at 23 dBm on the bench supply, a watchdog under load, or a manual power cycle]. After the reboot the air unit was in APFPV with `outgoing.server=127.0.0.1` again (see "Restoring the air unit after a test").

## First real link: Quest 2 + RTL8812AU + OpenIPC air unit (2026-09-26)

**Setup:** the HIL air unit (SSC338Q + IMX415, waybeam, H.264 640×480 @ 166 fps, 1 Mbit/s) sends over wfb-ng on channel 157, 20 MHz, FEC 8/12. The RTL8812AU sits on the Quest's USB-C, running PixelPilotXr (devourer).

**What it took to get video** [PROVEN: logcat `quality 217`, H.264 decoder configured, ~165 frames/s decoded]:
1. **The air unit boots into APFPV** (a Wi-Fi AP, not wfb). It was switched with its own `linkmode-air.sh wfb`.
2. **Keys:** the air unit's `drone.key` pairs with the HIL GS's `gs.key`. PixelPilot's bundled `gs.key` is not the OpenIPC firmware default either. For the test, the OpenIPC default `drone.key` was bind-mounted in RAM on the air unit, and the matching OpenIPC default `gs.key` went into the app's `gs.key` pref.
3. **Link id:** the air unit's `wfb_tx` ran without `-i`, so with **link_id 0** (`wfb-ng/src/tx.cpp:1702`). PixelPilot only accepts **7669206** (`WfbngLink.hpp:138`), so every frame is dropped as foreign. Fix: run `wfb_tx -i 7669206`, via a `/tmp` copy of the script. The wfb-ng wire header is byte-identical between the two sides (`wifibroadcast.hpp`, 0-line diff).
4. The air unit was itself broken that day (fps 0, unrelated to this work): it was running a known-broken waybeam build left over from an earlier session and was restored. See the OpenIPC project's HB-51 notes.

**Decode latency on the real stream: the decoder held ~16 frames** [PROVEN: logcat `Decoding:` + Perfetto `media.decode_latency_us`, N = 3 per state, alternating]:

| `dec_picture_order` (`vendor.qti-ext-dec-picture-order.enable`) | decode, ms |
|---|---|
| off (previous default) | 98.7, 95.5 · 96.6, 95.9 · 112.7, 99.8 |
| **on (new Meta-headset default)** | **1.45, 1.36 · 1.33, 1.29 · 1.42, 1.36** |

- The Perfetto trace rules out the surface as the cause:
  - the decoder never blocks in `dequeueBuffer` (p95 0.37 ms);
  - the BufferQueue holds at most 1 buffer;
  - the surplus 166 → ~102 fps is dropped by the compositor, which confirms mailbox behaviour.
- **The latency is inside the codec:** 96 ms ≈ 16 frames × 6.0 ms at 166 fps. This is the H.264 DPB depth [INFERRED: the SPS does not signal `max_num_reorder_frames = 0`, so the decoder waits for possible reordering; the x264 test streams signalled it and decoded in ~1.5 ms].
- FPV encoders send no B-frames, so decode order equals display order. `dec_picture_order` now defaults **on** for Meta headsets.
- An upstream PixelPilot build without this key would carry the same ~96 ms on this stream [INFERRED; not measured].
- Air-side alternative: write VUI `bitstream_restriction` with `max_num_reorder_frames = 0` into the SPS.

**Compositor wait on the real stream** ([latch_analyze.py](../../scripts/quest-latch/latch_analyze.py) on a 9 s trace at 166 fps): frame ready → latch **mean 3.08 ms, p50 2.64, p95 6.89**; 1434 frames queued, 886 latched [PROVEN]. This matches the prediction for a 166 fps source (half of 6.0 ms). The phase lock is not in play here: the air-unit side is not built.

## Restoring the air unit after a test (2026-09-27)

A power cycle is **not** a full revert. It brings back APFPV (hostapd) and the HIL key, because the RAM bind mount and the `/tmp` script copy are gone. **waybeam's `outgoing.server` stays `udp://127.0.0.1:5600`**: `linkmode-air.sh wfb` sets it through waybeam's API, and that setting persists in `/etc/waybeam.json`.

After the reboot the air unit is an AP that sends its video to itself. The symptom is `wlan0 tx_packets` growing by only ~6 per 2 s, while waybeam reports ~166 fps [PROVEN 2026-09-27: `grep '"server"' /etc/waybeam.json` = `127.0.0.1` after the power cycle].

**Always finish with the documented revert:**
1. Connect over eth0 `.132`, or over the AP `192.168.0.1` through the PC's Wi-Fi (`scripts/quest/wait_air.sh`).
2. Run `/opt/linkmode/linkmode-air.sh apfpv` in the background, because the AP drops briefly.
3. Check that `AIR_STATE=apfpv`, that `/etc/waybeam.json` has `"server": "udp://192.168.0.10:5600"`, and that `wlan0 tx_packets` grows by ~340 per 2 s.

Verified on 2026-09-27: after the revert, 342 packets per 2 s went to `192.168.0.10:5600` [PROVEN].

