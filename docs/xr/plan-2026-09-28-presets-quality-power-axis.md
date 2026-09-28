# Test plans: preset picture quality, and the live check of alink's power axis (2026-09-28)

Quest XR docs: [guide](../xr-quest.md) · [link envelope](link-envelope.md) · [presets design](presets-design.md) · run plan [plan-2026-09-27-optimize.md](plan-2026-09-27-optimize.md)

Both plans are for the Quest side (session pixelpilot-xr-22). The air side runs in the OpenIPC project (-47 / 3a).
Nothing here has been run yet. They are written so they can start as soon as the air presets (O114) and the power axis
are deployed.

## 1. Picture quality and latency per preset

**Presets** ([presets-design.md](presets-design.md)): MODE Race / Balanced / Balanced-lite / Wide × QUALITY Q2 / Q4.
That is 8 combinations. MODE restarts waybeam; QUALITY is live.

**What already exists, and is not repeated:**
- the latency between modes, W3c + e720s, in [g2g-budget.md](g2g-budget.md);
- the field of view per mode, in [link-envelope.md](link-envelope.md) (W3c stills).

This plan adds what the presets change: the picture at Q2 against Q4 in every mode, and the cost of Q4 in latency in
every mode.

**Scene.** Picture quality only shows with motion; on a static scene 2/4/8 Mbit/s looked alike. Yesterday the motion
came from the TV, which showed people, so none of those stills could be committed.
- **Ask the user for motion without people.** For example a moving pattern or scenery video on the TV, or a slowly
  rotating object. Then the stills can go into the repo.
- Otherwise every still stays in the git-ignored `scripts/quest/out/quality_private/`, as yesterday. Each one is
  checked by eye before anything moves to `docs/xr/img/`.

**Steps, per MODE** (4 blocks, air applies the preset, the app is not restarted):
1. The air switches the MODE, which restarts waybeam, and sends `READY <mode>`.
2. The Quest checks the decoder: `decode_watch.sh 6` must show a few ms and the mode's fps. After a resolution change
   it once stuck at ~78 ms ([troubleshooting](troubleshooting.md)).
3. **Latency, in one trace per MODE.** Q2 and Q4 are live, so one ~3 min trace covers Q2 Q4 Q4 Q2 Q2 Q4 (30 s steps).
   The analysis is `ab_segments.py` + `ab_link.py` with the air's step log. Result: Δ capture → decoded, loss after
   FEC and frames without a decoded mark for Q4 against Q2, per mode.
   - This replaces the [INFERRED] +1.7 ms in the presets table with a measured value.
4. **Stills,** after the trace has ended, so a screencap never loads the compositor during a measurement:
   [quality_shots.sh](../../scripts/quest/quality_shots.sh), 2 stills at Q2 and 2 at Q4.
   - The air records the same moments (waybeam `record`), for frame-exact bitstream frames.
5. Next MODE.

**Time:** about 4 × (15 s switch + 20 s settle + 3 min trace + 2 × 10 s stills) ≈ 17 min on the devices, plus the analysis.

**Output:** a table MODE × QUALITY with Δ latency, loss and frames without a decoded mark, plus the committed stills.
It goes into [link-envelope.md](link-envelope.md), next to yesterday's picture-quality section, and into the preset
table in [presets-design.md](presets-design.md).

**Air-side needs (-47 / 3a):**
- a MODE switch without writing `/overlay` (the presets design makes `/etc/waybeam.json` a link to `/tmp`);
- a live Q2/Q4 bitrate path;
- a step log with one line per step, `<air epoch> <label> tx=<n> temp=<C>` (ab_loop's grid format), which
  `ab_segments.py` reads directly.

## 2. Live check of the adaptive power axis

**The problem.** W2 emulated distance by lowering the air unit's TX power. With the power axis the loop owns that knob,
so the emulation has to move somewhere else.

**The options** (ranked in -47's design, `alink-power-axis-2026-09-28/00-DESIGN-power-axis.md` §8.1 in the OpenIPC
project):
- **(a)** an in-loop `pwr_offset_db`;
- **(b)** SMA attenuators;
- **(c)** a real distance walk;
- **(d)** removing the antenna.

**Recommendation: (a) as the proof, (c) once as the field check.**
- **(a)** Every commanded power is applied as nominal + offset, with the offset ≤ 0; the loop reasons in nominal units.
  - It is the W2 method, so every result is directly comparable to the W2 tables at the same Quest geometry: the
    policy table and the range test.
  - It is repeatable, can be bracketed (0 / −6 / −12 / −18 dB), and needs no hardware and no user.
  - Its limit: the uplink reports are not attenuated. Air power does not affect report delivery, so the stale path is
    not exercised.
- **(b)** Attenuators test both directions. They are not in the inventory: 2× 10 dB + 2× 20 dB SMA, DC–6 GHz, ≥ 2 W.
  Leakage limits them to ~10–20 dB.
- **(c)** The real thing (fading, multipath, a body in the path), but it cannot be repeated or finely bracketed, and it
  needs the user. It is worth one validation walk after (a) has passed.
- **(d)** Uncalibrated, and it risks the power amplifier at 23 dBm. It is not recommended.

**The run for (a),** following -47 §8.2, with the Quest side made concrete:

**Arms and order:**
- P = the proposed ladder;
- F23 = always 23 dBm;
- F12 = today (12 dBm, power axis off; only at offsets 0 and −6).
- Offsets {0, −6, −12, −18}, 3 passes, shuffled.
- Arms in ABC / CBA order within an offset. Steps of 60 s plus a 2 s guard.

**Traces.** About 38 min of steps is too long for one trace: yesterday 20 min made 67 MB, and the ring buffer holds
128 MB. So there is one trace per pass, ~13 min and ~45 MB each. Each trace is aligned by the air's step log and the
air − PC offset measured before it.

**Step log from the air.** One line per step, written after the arm and offset are set:
`<air epoch> <ARM>_o<offset> tx=<n> temp=<C>`, for example `P_o-12`. Also the receiver's `DECIDE` / `CMD` lines, as in
the range test.

**Quest per step:**
- `ab_segments.py`: loss after FEC, frames without a decoded mark, capture → decoded;
- `ab_link.py`: loss before FEC, FEC repairs, RSSI, Quest thermal;
- `quest_tx_log.sh`: uplink rate.

**Air per step:** settled row and power, time on MCS1, power and MCS changes and reversals, DPS-150 current,
`TEMP_R`.

**Dynamic arm** (after pass 3): an offset square wave 0 ↔ −12, 15 s / 15 s × 6, plus a single −20 dB for 3 s.
[ab_timeline.py](../../scripts/quest-latch/ab_timeline.py) gives the loss burst per second. The receiver log gives the
attack latency (`DECIDE … pwr-attack` against the offset change).

**What "the power axis helps" means:**
- at −6 / −12 / −18, P loses clearly less than F12;
- P comes close to F23 while spending less power at 0 / −6;
- P has 0 reversals once settled.

These are the design's predictions, still to be confirmed or refuted.

**Safety:** max 23 dBm only after -47's bench checks (§8.3 readback, §8.5 saturation) and with the supply fix from
O110. Temperature stop as in W2.

**Time:** ~40 min of steps, ~10 min for the dynamic arm, ~15 min of setup: about 65 min on the devices.

## 3. Power bracket before persisting the boot TX power (coordinator's request, 2026-09-28)

**Question.** Does loss rise above 20 dBm, for example because the Quest's receiver saturates at the bench distance?
This has to be answered before the boot power is persisted.

**Setup.** Air fixed on `m2b2f48` (REC), receiver `alink_air` stopped, 480p167. Power set by the coordinator with `iw`
plus a readback. The 8822EU `thermal_state` is read at 12 dBm and after the 23 dBm steps.

**Steps.** 12 × 30 s, each level N = 3, shuffled so that no run is monotonic. 17 dBm is spread over the trace and is the
drift reference. Rises in ≤ 3 dB / 200 ms steps, as before.

`p12 p17 p23 p20 p17 p12 p20 p23 p12 p23 p17 p20`, then back to 12 dBm.

**Quest.**
- One trace of 480 s, with `quest_thermal_log.sh` and `quest_tx_log.sh` alongside.
- Analysis with `ab_segments.py` (baseline `p17`, 2 s guard) and `ab_link.py`, on the air's step log.
- Per level: RSSI, loss before and after FEC, frames without a decoded mark, capture → decoded.
- **Saturation shows as:** loss before FEC rising at 20 → 23 dBm while RSSI still rises or flattens near the top of the
  scale (raw RSSI is clamped at 80, i.e. 100 on the app's column).

## 4. How far the bitrate can go: bitrate × MCS bracket (user request "at least 25 Mbit", 2026-09-28)

**Goal.** The real cap per MCS at the current distance, which becomes the future alink rows (m3/m4/m5 with caps; today
m1f46 is capped at 2000 and m2f48 at 4000), and the latency cost of the frame size.

**Fixed.** 12 dBm (the user's e.i.r.p. decision; never above it). 20 MHz, 1 stream, long GI, STBC + LDPC. Receiver
`alink_air` off. Bitrate through waybeam's API, which after O114 writes to RAM, not flash. MCS through `set_radio` with
all fields.

**Mode: 1080p90 native (1920×1080, no VPE scaling).** A high bitrate only buys picture where there are many pixels per
second to spend it on.

| Mode | pixels/s | bits per pixel at 25 Mbit/s |
|---|---|---|
| 1080p90 | 187 M | 0.13 |
| 720p120 | 110 M | 0.23 |
| 480p167 | 51 M | 0.49 |

- At 480p167, 8 Mbit/s already looked close to its ceiling in the stills [INFERRED], so 25 Mbit/s would be wasted.
- 1080p90 is the only mode where 25 Mbit/s still improves the picture [INFERRED: H.264 needs ~0.1–0.2 bit/pixel for a
  clean picture; not measured here].
- The decoder handles it: 1.4–1.5 ms at 1080p90 [PROVEN: 2026-09-27 stills].
- Balanced (720p120 native) is the second choice if 1080p90's latency (+~13 ms vs Race, W3) rules it out for use anyway.

**Capacity, and which combinations are worth running.** On-air rate = bitrate × n/k. Injection carries ~60 % of the
PHY rate [INFERRED: slot 2 measured ~97 % airtime at 12 Mbit/s on air, MCS2], i.e. ~11.7 / 23.4 / 39 Mbit/s at MCS2 /
4 / 7.

| bitrate | MCS2 (~11.7) | MCS4 (~23.4) | MCS7 (~39) |
|---|---|---|---|
| 4 | f46 (6), f48 (8) | f46 (6) | f46 (6) |
| 8 | f46 (12, at the edge) | f46 (12), f48 (16) | f48 (16) |
| 16 | not run: 24 on air > 11.7 [INFERRED] | f46 (24, at the edge) | f46 (24), f48 (32) |
| 25 | not run: 37.5 > 11.7 [INFERRED] | not run: 37.5 > 23.4 [INFERRED] | **f45 (31)**, f46 (37.5, at the edge) |

That gives 12 points. 25 Mbit/s fits only at MCS7, and only with light FEC (4/5).

**The link, honestly.**
- At 12 dBm here the Quest sees RSSI ~69, which is what the balcony saw at 17 dBm. There, MCS4 already lost ~15 % before
  FEC and 3.6–7 % after it (W2 phase 2).
- MCS7 needs clearly more SNR than MCS4. So at this distance and 12 dBm, MCS4/7 and therefore 16–25 Mbit/s will most
  likely not hold [INFERRED from W2]. The run measures exactly that.
- **Proposed second geometry (needs the user):** the same run with the Quest ~1 m from the air unit. It shows what the
  chain itself can do (encoder at 25 Mbit/s, injection, decode, latency) apart from the link. Then the answer to
  "how far can the bitrate go" has two parts: at this distance, and at best.

**Order.**
- The extremes first, as bracketing asks: m7b25f45 and m2b4f46 in the first steps, then the middle points.
- Anchor A = `m2b4f46` every 4th step, for the drift fit.
- 2 passes, shuffled differently (N = 2 per point), 20 s steps + 2 s guard. A pass is 12 points + 4 A ≈ 16 × 22 s ≈ 6 min.
- One trace per pass: 1080p at 25 Mbit/s is ~2 300 packets/s, so a trace grows ~2× faster than at 480p/2 Mbit/s.
- **Time:** 2 × 6 min + mode switch + decoder check + analysis setup ≈ 20 min on the devices per geometry.

**Step log from the air.** One line per step, after the MCS, FEC and bitrate are set:
`<air epoch> m<M>b<Mbit>f<kn> tx=<wlan0 tx_packets> temp=<C> enc_kbps=<waybeam's actual kbps> enc_fps=<fps> drop=<wfb_tx injection drops>`.
- `enc_kbps` and `enc_fps` show whether the encoder itself reaches 25 Mbit/s at 1080p90.
- `drop` shows whether the injection keeps up (air TX queue full).

**Quest per step.**
- `ab_segments.py`: loss after FEC, frames without a decoded mark, capture → decoded, spread, packets/frame. The
  frame-size cost is Δ capture → decoded against 4 Mbit/s at the same MCS.
- `ab_link.py`: loss before FEC, RSSI, rx/s against the air's tx/s.
- Quest thermal and uplink.
- Guardian paused, and restored after the run.

**Output.**
- The table of real caps per MCS: the highest bitrate with ≤ 0.1 % loss after FEC and no undecoded frames, plus its
  latency cost against 4 Mbit/s.
- New rows for alink proposed from it (m4/m7 with caps).
- The results go into [link-envelope.md](link-envelope.md).

**Safety.**
- Air temperature stop as before (skip ≥ 60 °C, abort ≥ 70 °C).
- `drop` rising means the air's TX queue is overflowing: skip the remaining points above that bitrate at that MCS.

**Step lists (A = `m2b4f46`, 12 points per pass; the extremes come early).**
- Pass 1: `A m7b25f45 m2b4f48 m4b16f46 A m7b4f46 m2b8f46 m7b16f48 A m4b8f46 m7b25f46 m4b4f46 A m7b8f48 m4b8f48 m7b16f46 A`
- Pass 2: `A m7b25f46 m4b4f46 m7b16f46 A m2b8f46 m7b8f48 m4b16f46 A m2b4f48 m7b25f45 m4b8f48 A m7b16f48 m4b8f46 m7b4f46 A`
- Order inside a switch, as in W2: raise capacity before load (MCS, then FEC, then bitrate); lower load before capacity.

**Where the extra fields can come from** (pointers for the air script):
- `enc_fps` / `enc_kbps`: waybeam's own verbose line in `/tmp/waybeam.log` (`[verbose] <s> | 166 fps | 8899 kbps | …`)
  [PROVEN: read on 2026-09-26, waybeam at 640×480].
- `drop`: wfb_tx's injection statistics ("tx …/2s, drop 0" as reported by the OpenIPC session on 2026-09-27).
