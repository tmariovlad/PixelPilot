# Autonomous optimisation run (2026-09-27, afternoon/evening)

The user is away for a few hours. Their mandate, verbatim in intent: optimise Quest + OpenIPC, make the app solid, verify
and minimise latency, check link resilience (TX power down and up), and find the settings with **minimum latency (top
priority)**, minimum video corruption, maximum adaptive range and acceptable temperatures. Work in parallel through the
other sessions and agents. Coordinator: session `pixelpilot-xr-d2 [440800]`. Results go into the topic files; this page
is the plan and the tracker. See [HANDOFF.md](HANDOFF.md) for ownership and approvals.

## Guardrails (apply to every workstream)

- **No firmware flash, no writes to `/rom`, no release-app changes** (PixelPilot 0.21.0 untouched).
- Air-unit writes only through the OpenIPC coordinator `openipc-…-3a [a61381]`. Back up every persistent file first and
  write down the revert command. Do not restart the video `wfb_tx` (8822EU NO-CARRIER risk); change MCS/FEC hot.
  Reboot the air unit only to recover from a dead link or to validate persistence, and announce it first.
- One device test at a time. The coordinator hands out slots for the Quest and the air unit. Code work runs in parallel
  freely.
- Measurement rule ([CLAUDE.md](../../CLAUDE.md)): alternate states, N >= 2 per state, position fixed, bracket the
  extremes (min / max / middle) before concluding. Tag claims [PROVEN]/[INFERRED]/[SPECULATION].
- **Temperatures.** Log the air SoC temperature and the Quest thermal status/battery with every step. Air SoC sensor:
  `/sys/devices/virtual/mstar/msys/TEMP_R`. It is documented to cycle between 43 and 65 °C with the fan. It did not
  throttle at 65 °C with the fan off and the full overclock [PROVEN per the OpenIPC session:
  HB-57-ssc338q-expert…md:137-138]. **WARN at 70 °C; STOP the step at ≥ 75 °C or when it rises > 3 °C/min without
  levelling off.** Do not read `/proc/net/rtl88x2eu/*` while injecting. Stop on the Quest at thermal status ≥ 3 or
  battery < 30 %.
- **Physical setup is fixed while the user is away.** The Quest is on the balcony and the air unit is indoors. Range is
  emulated by lowering the air unit's TX power (and the Quest RTL's), not by moving anything.
- At the end: Quest Guardian/display restored, air unit on the chosen defaults (or the pre-run state if nothing is
  proven better), every session commits only its own files, no push.

## Workstreams

| # | Owner | What | Needs |
|---|---|---|---|
| W1 | 3a (air) + 2c6ae8 (app) | Two-way wfb tunnel on the air unit (phase 1), then an adaptive-link receiver driving bitrate/MCS/FEC (phase 2, plan reviewed first) | air slot, Quest slot |
| W2 | 22 (Quest) + 3a (air) | Resilience/latency matrix: air TX power bracket x MCS x bitrate (+ FEC) at the chosen mode; loss, corruption, capture→decoded, temps. Output: the operating envelope and the policy table for W1 phase 2 | air slot, Quest slot |
| W3 | 2c6ae8 | Latency: resolution/fps mode choice (1080p90 vs 720p high-fps vs 640x480@167) measured on the Quest; UDP 8001 socket leak | air slot, Quest slot |
| W4 | c8 via 3a (air code) | AU-10: waybeam emits VUI `max_num_reorder_frames=0` / bitstream_restriction so the Quest decoder does not hold frames; AU-04: air-side phase lock | code first, then air + Quest slot |
| W5 | 8d | App robustness/UX in XR (settings, errors, hot-plug, autostart), code + tests, verified in Quest slots | Quest slot |

Order of device slots: W1 phase 1 → W3 mode choice → W2 matrix (at the chosen mode) → W4 AU-10 A/B → W1 phase 2 with the
W2 policy → final defaults check. The coordinator may reorder when a slot is blocked.

## Tracker

Filled in by the coordinator as results come back. Details are in each owner's topic file and commits.

- **Air-unit reset at 23 dBm (2026-09-27 ~16:31).** The air unit reset itself on the first step, a jump from 12 to 23 dBm.
  It was a hardware reset: no panic, since the kernel has `panic=20`. It is the second reset with this pattern
  (26.09 ~21:23). The suspected cause is a brownout on the supply [INFERRED]. The DPS-150 is not connected to the PC,
  so the current could not be measured. **TX power above 17 dBm is blocked until the user confirms the air unit's
  supply.** 17 dBm reached in 12→15→17 steps held without a reset. The Quest app recovered by itself, with no crash
  and video back after ~35 s.
- **W1 phase 1 PASS.** The tunnel works both ways: Quest→10.5.0.10 24/30 pings (~10 ms), air→10.5.0.3 2/5. Video is
  unaffected. The loss is open (downlink FEC 1/2 vs 1/3, after W2). Found and fixed along the way:
  - the app ↔ `wfb_tun` framing and MTU mismatch (`e889f76`);
  - the UDP 8001 leak that killed the uplink after the first link restart (`f117c70`, verified on the Quest);
  - stale wfb counters on a dead link (`dc58403`, device check in the W5 slot).
  Persistence is deployed on the air unit (`linkmode-air.sh` md5 b8b60b83, backup `.bak-2026-09-27-pre-tunnel`,
  `/overlay` 196K free). Boot validation is pending.
- **W2 phase 1 done.** 13 steps from 5 to 17 dBm with m2b8, no reset, 54–55 °C. Results: [link-envelope.md](link-envelope.md).
- **W3 mode choice.** 640x480@167 wins. Corrected budget: 30.4–35.7 ms at 8 Mbit/s, vs 37.5–42.8 for 720p120 and
  46.5–51.8 for 1080p90 ([g2g-budget.md](g2g-budget.md)).
- **AU-04 phase lock closed.** At 480p it would need ~119.7 fps, and even an ideal lock is +1.2 ms at 8 Mbit/s and ≈ 0
  at 2 Mbit/s. The actuator is also blocked, because AE rewrites VMAX ([compositor-phase.md](compositor-phase.md)).
  239 fps is not reachable on the IMX415. AU-10 (VUI) gives no latency on our Quest, only compatibility.
- **W2 phase 2 at 480p167** ([link-envelope.md](link-envelope.md)).
  - Low bitrate is fastest. MCS4 fails at this distance (~15 % pre-FEC).
  - FEC 4/8 at 2 Mbit/s costs about +0.3 ms and drops the loss to ~0.
  - Policy table: m2b2f48 → m2b2f46 → m1b2f46. Stepping down from m2f48 goes straight to m1.
  - The adaptive-link uplink (~51 frames/s) costs video airtime. It was cut to 12 frames/s in code (`d8b6498`).
- **Final before/after** ([g2g-budget.md](g2g-budget.md), `5d40d99`). REC = 480p167 / 2000 / FEC 4/8.
  - REC: **27.4–32.7 ms**. BASE (1080p90 / 8000 / 4/6): 46.6–51.9 ms. That is **−19.2 ms (−37 %)**, with the
    ranges disjoint.
  - Loss 0.10 % vs 2.06 %; undecoded 0 vs 1.2 %.
  - The 20–25 ms target is not reached. The REC floor is fixed by the panel (10.2 ms) and air→Quest (1.9 ms).
  - Air-side bursts where the encode is bimodal (+2 ms on ~24 % of frames) are an open −1…−2 ms lever.
  - Picture quality at 2 Mbit/s is not assessed yet.
- **App (W5 + fixes).** Every fix below is in code with tests, and verified on the Quest where noted:
  - the NO SIGNAL / WRONG KEY / SETUP headline and the readable panel (verified, no latency cost);
  - flight telemetry (verified with synthetic MAVLink) and the home-position fix;
  - native exceptions no longer cross JNI;
  - link self-healing and USB attach (needs a physical replug to verify);
  - XR input (A/X = panel mode, B/Y = hide);
  - decoder recovery (X23; checked in the final slot: the SPS-change rebuild (c) was slower on a live switch and was removed in `501094a`; [result](research/2026-09-27-xr-ux-audit.md#final-slot-on-the-headset-2026-09-27)).
- **Canonical Quest build.** 7b8baadb (`e889479`; file `scripts/quest/out/apks/w5b-e889479.apk`, gitignored). The final build from HEAD is checked in the last slot.
- **REC defaults persisted** (480p167 / 2000 / FEC 4/8 / MCS2 / 12 dBm). They were validated after a reboot: video at
  166.5 fps and the tunnel back from `/opt/linkmode`.
- **`alink_air` deployed.** It was validated after a reboot and now runs the 2-row policy m2f48 ↔ m1f46 (score
  1600/1590, `hold_down` 2000 ms, `stale` 1500 ms). The adaptive range test was A-B-A in one trace
  ([link-envelope.md](link-envelope.md), `3d4b8f7`). **At 8 dBm, adaptation cut the post-FEC loss by 2.5–4× and the
  latency by ~0.4 ms against a fixed m2b2f48.** There were zero oscillations. The step down came 2.6–2.7 s after the
  power drop and the step up 4.6–4.9 s after it rose. IDR on/off showed no measurable difference. The uplink is now
  about 14 frames/s instead of ~51.
- **"BAD n=29" datagrams resolved.** They were a TP-Link Kasa discovery broadcast from the LAN (192.168.100.55)
  arriving on the air unit's `eth0`, not truncated reports ([troubleshooting.md](troubleshooting.md), `96b404d`).
  `alink_air` gets a source filter (10.5.0.0/24 only), which is also a safety fix: before it, any LAN host could spoof
  reports.
- **Open air-side lever O112.** The encode time is bimodal (+1.2…2.3 ms on bursts of frames), probably because the
  encoder thread and the ISP thread share a CPU. The read-only investigation is approved. Pinning the threads (P4)
  needs the user.

- **O112 read-only probe.** Superframe re-encode is ruled out.
  - [IspDriverThread]/IspMidThreadWq (RR 99) share CPU0 with waybeam main (FIFO 50), which fits H1 but is only a
    snapshot.
  - None of the 4 waybeam instances at 480p REC was slow (0–0.2 % frames > 2.5 ms). Only ~2 of 10 instances today were
    slow, so H1 could not be tested live.
  - A light 5 Hz sampler (5.4 % of a core) is ready for a future session. The artefacts are in the OpenIPC repo:
    `repos/tasks/o112-encode-bimodal-2026-09-27/`.
- **End state of `alink_air`.** It is on m1f46 by design: `reason=stale` once the Quest stopped sending reports,
  because the headset sleeps after the hygiene restore. It returns to m2f48 by itself when the app runs again.

## Outcome and what is left for the user

The summary with numbers is
[g2g-budget.md § Recommendations and numbers](g2g-budget.md#recommendations-and-numbers-summary-2026-09-27).

- **Latency:** 46.6–51.9 → **27.4–32.7 ms** G2G (−19.2 ms), from a per-segment budget, not an optical measurement.
- **Corruption:** 2.06 % → 0.10 % loss, and undecoded frames went from 1.2 % to 0.
- **Range:** `alink_air` cuts the loss 2.5–4× at the weakest level tested, against fixed settings.
- **Temperatures:** air 44–50 °C throughout; the Quest had no thermal throttling.
- **Final Quest build:** b2249f15 (`501094a`), with every app fix except X23 (c). It was verified with no latency
  regression. The Quest is restored: Guardian on, display on auto.
- **The tunnel** runs both ways and is persistent. Tunnel FEC stays at 1/2.

For the user:
1. **Look at the picture** at 640x480 / 2000 kbit/s in the headset. If it is too soft, use the revert below or raise
   the bitrate. Each +1000 kbit/s costs about +0.6 ms at 480p [INFERRED: slot 2 8000→4000→2000 = −2.7/−1.8 ms; W2 m2b2→m2b4 = +1.15 ms] ([link-envelope.md](link-envelope.md), [g2g-budget.md](g2g-budget.md)).
2. **Air-unit supply.** Say what powers `.132` now and connect the DPS-150 for metering before anyone uses more than
   17 dBm.
3. **Physical checks that were blocked:** link self-healing and X15 (plugging the adapter in during XR), both needing an
   RTL replug; controller buttons A/X/B/Y; the slot-3 visual check. **Done 2026-09-28** (except the slot-3 visual check):
   A/B work, the link heals itself 3/3, and X15 is confirmed 3/3, with the pilot left in 2D on the 2nd replug
   ([hands-on checks](research/2026-09-27-xr-ux-audit.md#hands-on-checks-with-the-user-2026-09-28)).
4. **Decision on O112 P4** (pinning the ISP/encoder threads on the air unit, estimated −1…−2 ms). The read-only part
   runs first.
5. **Optional:** a photodiode G2G on the Quest to check the absolute number (±2.6 ms).

## Air-unit state and reverts (as left by this run)

The persistent defaults on `.132` were validated with a reboot each time. The backups sit next to each file on the air
unit.

| Change | Files | Revert (run on the air unit, `ssh root@192.168.100.132`) |
|---|---|---|
| Two-way tunnel (`wfb_rx`/`wfb_tun`, tunnel `wfb_tx -C 9001`) | `/opt/linkmode/linkmode-air.sh`, `wfb_rx`, `wfb_tun`, `wfb_tx_cmd` | `cp /opt/linkmode/linkmode-air.sh.bak-2026-09-27-pre-tunnel /opt/linkmode/linkmode-air.sh && reboot` |
| REC defaults (480p167, 2000 kbit/s, FEC 4/8) | `/etc/waybeam.json`, `linkmode-air.sh` | `cp /etc/waybeam.json.bak-pre-rec-20260927 /etc/waybeam.json && cp /opt/linkmode/linkmode-air.sh.bak-2026-09-27-pre-rec /opt/linkmode/linkmode-air.sh && reboot` |
| `alink_air` (adaptive MCS/FEC) | `/opt/linkmode/alink_air`, `alink_air.conf`, `linkmode-air.sh` | `killall alink_air; rm /opt/linkmode/alink_air /opt/linkmode/alink_air.conf && cp /opt/linkmode/linkmode-air.sh.bak-2026-09-27-pre-alink /opt/linkmode/linkmode-air.sh && reboot` |
| Everything, back to this morning (1080p90 / 8000 / FEC 4/6, no tunnel, no alink) | as above | `cp /etc/waybeam.json.bak-1080p90-20260927 /etc/waybeam.json && cp /opt/linkmode/linkmode-air.sh.bak-2026-09-27-pre-tunnel /opt/linkmode/linkmode-air.sh && reboot` |

The PC also keeps copies of what was deleted from the air unit to free `/overlay`: `libsodium.so.23*` (not used by
anything running) and `wfb_tx.v25.bak`. They are in the OpenIPC repo under
`repos/tasks/hil-build/air-kernel-backups/linkmode/`, with md5 sums.

## Evening session after the user returned (2026-09-27) and resume point

- **Picture quality.** Real bitstream frames and Quest screenshots were captured at 480p with 2/4/8 Mbit/s and at
  1080p. Files showing people stay local and uncommitted (`scripts/quest/out/quality_private/`). On a static scene
  the bitrates look alike. With motion, 2 Mbit/s is visibly soft and blocky. See [link-envelope.md](link-envelope.md).
- **Field of view.** 480p167 is a centre crop (33×44 % of the sensor). W3c + e720s give the latency against the view
  ([g2g-budget.md](g2g-budget.md)):

  | Mode | View | G2G |
  |---|---|---|
  | 480p167 | 33×44 % | 26.7–32.0 ms |
  | 720p120 → 848×480 | 66 % | 31.3–37.6 ms |
  | 720p120 native | 66 % | 33.0–38.3 ms |
  | 1080p90 → 848×480 | full | 35.3–41.6 ms |

  RES_4 1472×816@150 is not viable (VENC 0.48 fps). **The user's mode choice is pending.**
- **O112 P4 (thread pinning) proven.** Slow encode frames occur only while IspDriverThread runs on CPU0. PIN (ISP on
  CPU1) gave 0 % slow frames in 5/5 runs, with p95 S_air −155 µs. It is active at **runtime** only and is lost on an
  air reboot. Persisting it is approved; it will be deployed together with the chosen mode.
- **Reorder-hold fix** (`952a655`, pref `rtp_tight_reorder`, default ON). Frames after a loss went from 3.0 to
  1.6 ms (−1.4 ms each) at 8 dBm [PROVEN].
- **Quest "parse"** already contains the radio spread; it is not an extra hop.
- **`write_prefs` bug** (ff19253 → fixed in 3cb6ea1). The prefs were not written from 18:16 to 22:34. No result that
  was used depends on it (audited by 22 and 8d).
- **Presets** (user request). The app side is implemented (`eb116f5`, `98b3423`; [presets-design.md](presets-design.md))
  and is being tested against a fake air unit. The air side design is approved (OpenIPC `f596c61`: `/etc/waybeam.json`
  becomes a symlink to `/tmp`, plus `vmoded`). Its implementation and deploy are pending. The user decided: a single
  confirm even when armed, and quality presets 2/4 Mbit/s (6 capped to 4 in v1).
- **Open for the user:**
  - the mode choice;
  - powering on the GS `.208` (AU-02/AU-13, ~2 ms on the monitor path only);
  - the physical checks (RTL replug, controller buttons).
  - Note: PC C: had only 7.7 GB free.
- **Resume point.** After the PC restart, finish the preset flow test (8d, fake air), then the air preset
  implementation and deploy (c8/3a). After that, persist the mode + PIN with a reboot validation.
