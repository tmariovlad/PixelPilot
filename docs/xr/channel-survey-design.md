# Channel survey before a flight: design (2026-09-30, no code yet)

**Status: design for review.** From [BACKLOG.md](../../BACKLOG.md), first item: a calibration mode that says which 5 GHz
channel is free right now, shows the strong signals as a graph, and moves the link there.
- **Why measure instead of hard-coding:** on 2026-09-29, ch165 cut residual loss 3.5–6× vs ch157, with the neighbour
  "Staff" VHT80 on 149–161 ([channel A/B](link-envelope.md), [air log](data/air-chan-ab7-2026-09-29.txt)). R3′ on
  2026-09-28 found the opposite: 165 lost as much as 157, and a beacon-locked source was active on 165 that night
  (link-envelope R3′). The best channel depends on the neighbours at the time [PROVEN: both runs].
- **Scope:** UNII-1 36–48 and UNII-3 149–165. DFS 52–144 is excluded, because the air has no radar detection.

Keywords: channel survey, spectrum, site survey, busy time, CCA, NHM, noise histogram, neighbour AP, BSS load,
foreign frames, bad FCS, recommended channel, VMODE1 ch=, A6a chan, calibrare canal, canal liber, grafic spectru.

## 1. Sources

### 1a. The RTL8812AU through devourer (primary: sees our band and our link's frames)

What devourer exposes (submodule `devourer` @ `af0ae6d`):

| What | Where | Notes |
|---|---|---|
| Retune | `IRtlDevice::SetMonitorChannel` (`src/IRtlDevice.h:67`), `FastRetune(channel)` (`:78`, the lean intra-band hop) | Hop cost: a ~1.5 ms VCO settle floor [PROVEN: `docs/frequency-hopping.md:373-375`]. devourer's sweep reports the measured `retune_us` per dwell [PROVEN: `docs/rx-spectrum-sensing.md:164-166`]. |
| Frame-free energy | `GetRxEnergy(with_nhm)` (`src/IRtlDevice.h:530`, struct `src/RxSense.h:30-60`; 8812A reader `src/jaguar1/RtlJaguarDevice.cpp:274-316`) | Per call, deltas since the previous call: OFDM/CCK false-alarm and **CCA (channel-busy)** counts (BB 0xF48 / 0xA5C / 0xF08). DIG gain index `igi` (0xC50): higher = noisier. With `with_nhm`, the **NHM** 12-bucket in-band power histogram (~2 ms window). |
| NHM busy | `rx.nhm` semantics (`docs/rx-spectrum-sensing.md:100-117`) | `busy` = percent of samples above the lowest bucket, a **time share of energy, frame-free**: it also sees non-Wi-Fi interferers. `peak` = fullest bucket. |
| Absolute noise floor | `RxEnergy.abs_noise_floor_dbm` | **Not per channel on the 8812A:** the RX-idle CAL is taken at bring-up and not re-run after a hop [PROVEN: `RtlJaguarDevice.cpp:308-313`]. Not a survey signal. |
| Per-frame attributes | `RxAtrib` (`src/RxPacket.h:37-66`): `crc_err`, `icv_err`, `data_rate`, `bw`, `rssi[4]`, `snr[4]`, `evm[4]` | Frames with a bad FCS reach the app only with `keep_corrupted` on (`RxDiag`, [fec-block-probe §1](fec-block-probe.md)). |
| Sweep reference | `DEVOURER_RX_SWEEP` in devourer's rxdemo (`docs/rx-spectrum-sensing.md:151-170`) | The RX loop runs on a worker thread while another thread calls `FastRetune` between reads. Per bin it gives energy counters + a per-dwell frame aggregate (frames, RSSI, SNR, EVM). A per-SA filter exists (`DEVOURER_RX_AGG_SA`). This is the pattern to copy. |

**What the app adds per dwell** (in `WfbngLink`'s RX callback, which already classifies every frame:
`IsValidWfbFrame` / `MatchesChannelID`, `WfbngLink.cpp:236-306`):
- **Own vs foreign frames.** A frame is "own" when it is a valid wfb frame with our channel id; everything else is
  foreign.
- **Foreign airtime share:** Σ (frame length × 8 / PHY rate from `data_rate`/`bw`) over the dwell. This is the
  frame-based busy share that excludes our own link [INFERRED from the RxAtrib fields; the rate→µs table is new code].
- **Strongest foreign RSSI** (dBm = raw − 110, devourer `LinkHealth.cpp:8`).
- **Bad FCS per second** (keep_corrupted on).
- **Energy:** CCA / FA deltas and NHM `busy` / `peak`.

### 1b. The Quest's internal Wi-Fi scan (secondary: names the neighbours)

`cmd wifi start-scan` then `cmd wifi list-scan-results` give SSID, BSSID, primary frequency, channel width / centre and
RSSI per BSS [SPECULATION on Horizon OS: not probed yet. Probe: `adb shell cmd wifi start-scan; sleep 5; adb shell cmd
wifi list-scan-results`]. It shows **which 20 MHz channels an 80/160 MHz BSS covers**, which the RTL cannot tell from
energy alone.
- **BSS load** (channel utilization, 0–255) is in the beacon IE, but `list-scan-results` may not print it
  [SPECULATION]. `WifiManager.getScanResults()` exposes the raw IEs.
- **From the app:** it needs `ACCESS_FINE_LOCATION` + `CHANGE_WIFI_STATE`; the manifest has only
  `ACCESS_WIFI_STATE` today [PROVEN: `app/src/main/AndroidManifest.xml:12`]. Android also throttles `startScan` for
  foreground apps (4 per 2 min) [SPECULATION for Horizon OS].
- **Caveat:** an active scan transmits probe requests from the internal radio. Next to the RTL that disturbs the link,
  as streamed logcat over Wi-Fi did (T4, [uplink analysis](uplink-t4-analysis.md)). So the Quest scan runs **before**
  the RTL sweep, never during a link run [INFERRED].

The PC is not a source: its card scans only 36–100 (BACKLOG).

## 2. Duration, and the link

- **One adapter:** the RTL is also the video receiver, so a sweep means **no video** for its duration. The survey is a
  pre-flight mode, not a background task [PROVEN: one adapter in the app; `WfbngLink` owns it].
- **Dwell 1 s per channel.** That covers ~10 beacon intervals (102.4 ms) and 4 reads of 250 ms, each read the energy
  deltas plus one NHM (~2 ms).
- **Three interleaved passes** over the 9 channels (36 40 44 48 149 153 157 161 165), so a neighbour's burst does not
  land on one channel only: **~27 s + 27 hops × ~2 ms**. A "thorough" option: 3 s per dwell, ~80 s.
- **The air keeps transmitting on its channel** during the sweep:
  - Its frames are counted as own and left out of the foreign share.
  - CCA / NHM on the link channel include our own energy, and the adjacent channels include its leakage at ~1 m
    [INFERRED]. So the graph marks the link channel's energy bar "incl. our link", and the score uses the frame-based
    foreign share there.
  - VMODE1 has no "quiet" verb [PROVEN: [menu-design §7](menu-design.md) lists none]. A short air TX pause for the
    sweep would be a new verb, optional.
- **After the sweep** the app retunes back to the link channel and waits for video. The existing health log records
  the gap (PPXR_EVENT) [PROVEN: [health-logging](health-logging.md)].

## 3. Score, graph, script

**Per channel c:**
- `occ(c)` = max(RTL foreign airtime %, the highest BSS load % among Quest-scan BSSs whose span covers c).
- `sig(c)` = the strongest foreign RSSI on c (RTL frames, or a covering BSS from the Quest scan), dBm.
- `noise(c)` = NHM busy % on non-link channels (non-Wi-Fi energy).
- `fcs(c)` = bad FCS per second.
- **cost(c) = occ(c) + 0.5 × max(0, sig(c) + 90) + 0.5 × noise(c) + 2 × fcs(c)**. The weights are starting values,
  to be calibrated by §5 [SPECULATION until then].
- **Recommended** = argmin cost over the channels the air lists (VMODE1 `list`, `channels:`), with hysteresis: propose a
  move only if cost(best) < 0.8 × cost(current).

**Graph (in-headset menu, [menu-design](menu-design.md) "Link ▸ Channel survey"):**
- 9 bars over two groups, 36–48 | 149–165, with the DFS gap drawn empty.
- Bar height = occ %. Colour = sig: green < −80, amber −80…−65, red > −65 dBm.
- An outline marks the current channel, a star the recommended one, and "incl. our link" labels the link channel.
- Actions:
  - **Run survey (video off ~30 s)**;
  - **Switch to ch N**, the two-phase A+Q switch of §4, only for a channel the air lists.
- Right thumbstick only, like the rest of the menu.

**Log and script:**
- One line per dwell, tag `PPXR_SURVEY`: `pass= ch= dwell_ms= retune_us= own= foreign= foreign_air_pct= foreign_rssi_max=
  bad_fcs= cca_ofdm= fa_ofdm= igi= nhm_busy= nhm_peak=`. Captured detached like the other tags (`ab_detached.sh` -s
  list).
- `scripts/quest/channel_survey.py` (new, [SPECULATION until written]) joins the PPXR_SURVEY lines with a saved
  `cmd wifi list-scan-results` and prints the per-channel table, the score and a text bar chart (PNG optional).
  Offline tests on recorded lines.

## 4. How the recommended channel reaches the air

- **The air side exists: VMODE1 `apply ch=<n>`**, two-phase [PROVEN: OpenIPC `repos/tools/vmoded/src/sm_ext.c` (`ch=`
  validation `:382-384`, the `ch_to=` / `switch_in_ms` announce in the beacon `:212-221`, resume on restart
  `:134-136`), design and implementation notes in `repos/tasks/vmode-presets-2026-09-27/03-DESIGN-menu-extension.md`
  and `04-IMPL-menu-extension.md:171-178`].
  - The air acks `switch_at_ms = air epoch + 1500`, and both ends switch then.
  - The air retunes through `linkmode-air.sh chan <ch>`, the A6a patch: no waybeam or wfb_tx restart, and a verdict
    `AIR_STATE=wfb FREQ= CH= BCN=` [PROVEN: `deploy/a6/linkmode-air.sh.A6a:287-292`].
  - The app commits after 30 frames. Otherwise the air reverts after `revert_s`, and the app does the same on its own
    after `revert_s` + 2 s without video ([menu-design §7.4](menu-design.md)).
  - The deployed air logs `EXT on: … ch=165 chan_verb=1` [PROVEN: vmoded logs in the OpenIPC deploy dirs].
- **The Quest side is not built.** The app sets its channel from its preference (`VideoActivity.getChannel`,
  `WfbLinkManager.setChannel`, `VideoActivity.java:181, 1693`) and does not read `ch_to` / `switch_in_ms` yet
  [PROVEN: grep, no hit]. It is menu phase 2 ([menu-design §8](menu-design.md)).
- **Two risks to settle in that build:**
  - **DFS.** A6a's own list accepts 52–144 (`LINKMODE_CHANNELS` default, `:292`), so the non-DFS restriction must
    come from vmoded's limits (`lim_channel_ok`, `sm_ext.c:384`). `limits.conf` must list only 36–48 and 149–165
    [INFERRED; check the deployed limits.conf].
  - **Persistence.** A live retune wins only until the air reboots: `/tmp/linkmode.chan`, then `hostapd.conf`'s
    `channel=` [PROVEN: `A6a:148-151`]. The app's preference persists, so after an air reboot the two can disagree.
    Fix: the app follows the VMODE1 beacon's `ch=` when it has no video, or the switch also persists the channel on the
    air (`save_default`) [design choice for the OpenIPC side].

## 5. Validation plan (before the score drives anything)

1. **Replay the known case.** Run the survey at the 2026-09-29 geometry. It must rank 157 below 165 because of the
   covering VHT80 "Staff" BSS, as that night's A/B found (post-FEC 3.5–6× worse on 157).
2. **A/B on two channels picked by the survey:** the recommended one and the worst allowed one, or the current one.
   - ABAB × 2, 120 s steps, the same geometry and air state (MCS/FEC/bitrate fixed), a detached capture, keep_corrupted
     on.
   - Metrics per step:
     - `crc/s` (bad FCS per second, `RxDiag` / `ppxr_rx_*` counters);
     - `p_data` (accepted wfb data packets per second, and loss before FEC; `link_audit.py`);
     - post-FEC loss (RTP holes: `rtp_holes.py`, `fec_blocks.py`).
   - Run the survey just before and just after the A/B, to see whether the neighbours changed during it.
3. **Pass:** the survey's order equals the A/B's post-FEC order in both repetitions. Then repeat on another day or in
   another position, since the neighbours change (R3′ vs 09-29). Two agreeing days → the score may drive the menu's
   recommendation. A disagreement → recalibrate the weights, e.g. more weight on `fcs` if bad FCS predicts better than
   occupancy.
4. **Record:** results into [link-envelope](link-envelope.md) (channel section), data into `docs/xr/data/`, and this
   doc's weights updated with the evidence.

## 6. Open questions

- Does Horizon OS's `cmd wifi list-scan-results` print the channel width / centre and the BSS load? (§1b probe)
- Is the 8812A's NHM busy % stable enough in 4 reads per second? Or should dwells lengthen on noisy channels? (§5 run)
- Is a short air TX pause (a new VMODE1 verb) worth it, to measure the link channel's energy without our own
  transmitter? (§2)
