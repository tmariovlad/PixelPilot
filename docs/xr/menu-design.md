# In-headset menu: every option and every stat, right thumbstick only (design, 2026-09-29)

Status: **approved 2026-09-29 (coordinator 66: "go phase 1"), phase 1 in progress.** It extends the preset menu of [presets-design.md](presets-design.md)
(MODE/QUALITY over VMODE1), which stays valid for the air protocol and its safety rules. Code map this design builds on:
[tasks/menu-infra-map-2026-09-29.md](../../tasks/menu-infra-map-2026-09-29.md) (file:line for every "today" below).

## 1. Requirements (the user, via the coordinator, 2026-09-29)

1. "Work on the menu too, so I can see it with the joystick, turn options on and off, and have everything" (RO: "lucrează și la meniu, să-l văd cu joystick, să activez/inactivez opțiuni, să am tot"):
   **full options**. Nothing may be reachable only via adb/prefs.
2. "Let me also see all stats: MCS, dBm, the G2G latency and each segment of it" (RO: "să văd și toate stats: MCS, dBm, latența G2G și pe fiecare segment"): **full stats**, with latency per segment.
3. **A complete UI controlled ONLY with the right joystick.** A/B/trigger may be shortcuts, never the only path.
4. Readable in XR: at most 7 lines per page. Each line shows the current value, a cost label, and whether it applies live, needs a relaunch, or switches the air.
5. Every air change reverts by itself if the video does not come back. The menu cannot exceed the approved limits: TX power
   MCS7 ≤ 18 dBm, other rates ≤ 24 dBm; payload ≤ 3900 B if packet size is ever offered.

## 2. What exists today and what changes

| Today [PROVEN in the map] | Change |
|---|---|
| One 1024×256 stats surface (~7 lines) holds the headline, the preset menu and the stats (`XrStatsRenderer`, `LayerLayout`) | **A third quad layer, "menu"**: 1024×640 px, ~16 lines of 28 px monospace. It is submitted only while the menu is open, next to the video on the right, head-locked like the stats. The stats panel stays as it is. |
| Stick and click are bound on both hands and merged into one bitmask (`XrInput.cpp:63-78`) | Menu actions are bound to the **right** hand only. The left stick does nothing (the pilot's left hand may rest on it). A/X/B/Y keep their panel shortcuts. |
| Input reaches Java at the 250 ms stats tick (`XrVideoActivity.java:99`) | While the menu is open, a **50 ms menu tick** takes the input bits (the same `XrBridge.takeInputEvents`). Hold timers run on it. |
| Prefs are read once in `onCreate`; nothing re-applies them (`XrVideoActivity.java:125`, `:147`) | The stream levers are applied **live**: the menu writes the pref, then calls `setDecoderLevers` with a fresh `LatencyExperiments`. The native setters are atomics (FIF, IDR, interval, FRZ, tight reorder). |
| Decoder-configure and XR levers apply at start only | **Controlled relaunch**: write the pref, show `RELAUNCH ~3 s`, then `recreate()`, which already exists for XR levers in `onNewIntent`. No `System.exit`. |
| The preset menu covers MODE and QUALITY only (`PresetMenu`) | It becomes the "Air ▸ Mode / Quality" page of the tree. `VmodeSession` and `CommitGate` are reused unchanged for mode/quality; radio, codec and channel are added (§7). |
| Per-packet MCS/GI/STBC/BW is parsed by devourer but dropped (`RxAtrib`) | Session 36's `StatsSource` exposes it (§6). |

## 3. Controls (right thumbstick only)

| State | Input | Action |
|---|---|---|
| Menu closed | **Click held 1 s** (a ring fills on the panel) | Open the menu at the last page |
| Menu closed | anything else | Nothing. A flick while watching must not do anything |
| Browse | Up / down (flick past 0.7, re-armed below 0.3, as today) | Move the highlight; wraps |
| Browse | **Right** or click | Folder: enter. Boolean: toggle. Choice/number: start editing |
| Browse | **Left** | Back one level; at the root: close |
| Edit | Left / right | Previous / next value (numbers step by the option's step, clamped to its range) |
| Edit | Click | Quest-local option: apply now (live or relaunch per §4). Air option: nothing yet; the line shows `hold 1 s to apply` |
| Edit | **Click held 1 s** | Apply an air option (confirm-or-rollback, §7) |
| Edit | Up / down or 6 s idle | Cancel the edit (value unchanged) |
| Browse, on an air line showing the active value | **Click held 3 s** | "Save as default" on the air (`save_default`, presets-design §4) |
| Any page except Stats | 20 s idle | Close |
| Stats pages | no idle close | Stay open while the pilot watches. Left = back |

Hold feedback: a bar on the highlighted line fills over 1 s (and to 3 s). Releasing early does nothing. The simple
controller profile gets no menu, as today.

## 4. Apply classes (shown on every line)

| Tag | Meaning | How |
|---|---|---|
| `L` | live, Quest only | write the pref + `setDecoderLevers(LatencyExperiments.load())` at once. XR layout levers are re-pushed with `setLayout` |
| `R` | relaunch, Quest only | write the pref, show `RELAUNCH ~3 s` for 1 s, then `recreate()` |
| `A` | air | VMODE1 `apply` with a 1 s hold, the air's revert timer, commit after 30 decoded frames |
| `A+Q` | air and Quest in step | channel: both ends switch at an agreed time, and both revert on no video (§7) |

## 5. The tree (≤ 7 lines per page including `‹ back`)

Line format, 40 columns:
`<label, 18>  <value, 8>  <tag>  <cost>`. Example: `Keyframe on loss    ON      L  -smear +airtime`.
The cost is formatted from `option_costs.json` (session dc, one table, looked up by pref key or air field). An option
without an entry shows no cost, never a made-up one.

```
Root
  Stats ▸            (§6)
  Picture ▸          stream + decoder levers (Quest)
  Air ▸              mode, quality, radio, codec (air)
  Display ▸          XR levers (Quest)
  Panel ▸            the stats panel
  Save / reset ▸
  Close

Picture ▸
  Feed incomplete     OFF   L   +fps, smears on loss        feed_incomplete_frames
  Keyframe on loss    ON    L   -smear, +keyframes          request_idr_on_loss
  Keyframe interval   200ms L                                idr_min_interval_ms (100–2000, step 100)
  Freeze until IDR    ON    L   brief hold on loss          freeze_until_idr
  Tight reorder       ON    L                                rtp_tight_reorder
  Decoder ▸                                                  LL / picture order / operating rate / LL component / AU (R each)

Air ▸                (values and allowed ranges come from the air's `list`; nothing is hard-coded)
  Mode                Race  A   G2G 26.7-32 ms, FOV 33 %    Race / Balanced / Balanced-lite / Wide / HD
  Quality             4 Mbit A  est. +1.7 ms                 the air's list
  Radio ▸             MCS, FEC k/n, streams (1SS STBC / 2SS), TX power, adaptive link
  Codec               H.264 A   (H.265 cost from bc's table)
  Channel             157   A+Q
  Air status          (read-only: temp, phase, pending mode, revert countdown)

Display ▸            refresh 72/90/120 (R), FOV (L via setLayout), curved (L), flip (L), timestamps (R), perf (R), thread hints (R)
Panel ▸              detail compact/detailed (L), hidden (L), position under/over the video (L)
Save / reset ▸       Save air default (hold 3 s) · Quest levers to defaults (L/R as needed) · Revert air to boot default (A)
```

## 6. Stats pages (live, 2 Hz, from session 36's `StatsSnapshot`)

The data model is agreed with session 36: `com.openipc.xr.stats.StatsSnapshot` in :app:xr, numbers only, NaN or `NA`
= no data, fed by `XrVideoActivity` on each tick. The menu formats it.

| Page | Lines |
|---|---|
| **Summary** | `G2G est. 31.4 / p95 36.0 ms (no sensor/panel)` · `fps 89.6  post-FEC 0.74 %  holes 5.1/s` · `RX MCS7 LGI STBC  -63/-66 dBm  SNR 17/18` · `air Race 4.0 Mbit  m7 f8/10  17 dBm` |
| **Latency ▸** | one line per segment, p50 / p95 over ~2 s: capture→encoded · encoded→sent · sent→complete (radio + FEC) · complete→decoded · decoded→shown (est.) · **sum** · `matched 178 frames, clock ±0.4 ms` |
| **Link ▸** | RX rate + share · RSSI A/B dBm · SNR A/B dB · pre-FEC % / post-FEC % · FEC rec/s · holes/s |
| **Levers ▸** | IDR requests ok/failed per s · IDRs sent by the air per s · frozen slices/s · decode errors · undecoded/s |
| **Air ▸** | mode, resolution@fps, bitrate req/effective, MCS/FEC/power in use, channel, codec (from the VMODE1 `state` beacon) |

Air segments are greyed out with `no sidecar` when the sidecar is older than 2 s (`ageMs`), and the sum reads `n/a`.
The optical G2G (photodiode) stays the absolute reference.

## 7. Air side: what the app needs from VMODE1 (for the OpenIPC side, via session -40)

Everything below extends the existing protocol ([presets-design §2](presets-design.md#2-protocol-app--air-through-the-wfb-tunnel)); `list`/`apply`/`commit`/`save_default`, `seq`, retry
and `state=busy` stay the same.

1. **`list` also returns the radio capabilities and limits**, so the air stays the single source for what is allowed:
   `radio=mcs:0-7,12,13|fec:4/6,4/8,8/10,8/12|streams:1stbc,2|txp:12-24|txp_max_mcs7:18|channels:149,153,157,161,165|codecs:h264,h265|alink:0,1`
   plus the active values in the `state` beacon (`mcs= fec= streams= txp= ch= codec= alink=`). The menu shows only the
   listed values. The air rejects anything outside them with `state=error reason=out_of_range`.
2. **`apply` accepts these fields**: `mcs= fec=k/n streams= txp= codec= alink= ch=`. Each one is optional, and one apply
   may carry several. Radio fields are live (wfb_tx control port, as in the grids). `codec=` restarts waybeam, so it
   behaves like a mode switch: `pending` → the app commits after 30 frames.
   - The app needs live codec switching (session bc: `VideoDecoder.cpp:91`). Until that lands, the app does a controlled
     relaunch when the codec in the beacon changes.
3. **Every radio apply goes through confirm-or-rollback**, like a mode switch. The air keeps the previous radio state, and
   restores it by itself if no `commit` arrives within `revert_s`. The app commits after 30 decoded frames with the new
   values active in the beacon. A bad MCS/power choice can cost the link, and then the uplink with it, so the timer must
   run on the air.
4. **Channel (`A+Q`)**, two-phase, because both radios must move:
   - `apply ch=<n>` → `ack state=accepted token=<t> switch_at_ms=<air epoch ms, ~1.5 s ahead>`;
   - both ends switch at that time; the app sets devourer's channel;
   - the app commits after 30 frames on the new channel;
   - with no commit within `revert_s`, the air returns to the old channel, and the app does the same on its own after
     `revert_s` + 2 s with no video. There is no uplink to coordinate that step.
5. **Limits are enforced on the air.** The menu shows only the listed values as a convenience, but the air must refuse
   `txp` above `txp_max_mcs7` when the resulting MCS is 7, and so on.

## 8. Build plan

**Phase 1 (no air dependency; first build for the user):**
1. `MenuTree` / `MenuOption` registry (pure Java, :app:xr): the options, their pref keys or air fields, the kind (bool / choice / number), range and step, and the apply class. This is the one place that says what the menu offers.
2. `MenuNavigator` (pure logic): browse/edit states, holds, idle close, right-stick events → actions. JVM tests for every row of §3.
3. `MenuPageRenderer` (pure): tree + values + costs + stats → ≤ 16 lines of ≤ 40 columns. JVM tests for formatting and truncation.
4. Native: the menu quad layer (third swapchain + layer), right-hand-only bindings for the menu actions. Checked on the headset via `DebugInput` and then by hand.
5. `XrVideoActivity` wiring: the 50 ms menu tick, live `setDecoderLevers`, `recreate()` for `R`, and the Stats pages from 36's snapshot.
6. The Air pages show Mode/Quality through the existing `VmodeSession`. Radio/codec/channel appear greyed out as `needs air vX` until the air lists them.

**Phase 2 (after the air side):** radio/codec/channel applies with confirm-or-rollback, checked first against
`vmode_fake.py`, which gets the new fields, and then on the air.

Tests: JVM for tree/navigator/renderer; `vmode_fake.py` + `test_vmode_fake.py` extended for the new `apply` fields and the
channel two-phase; on the headset with the user: every page opened by hand, one live lever, one relaunch lever, one mode
switch and one forced revert.

## 9. Decisions (coordinator 66, 2026-09-29) and open points

Decided:
1. The menu sits **to the right of the video** by default, never over its lower third, so it does not cover the picture while flying. The position can become a Display option later.
2. **No left-stick mirroring** (the user: right stick only).
3. HD comes from the air's `list` once the air side exists. Until then it shows greyed out as `needs air`.

Still open:

1. Which Display levers are worth offering live vs relaunch after a quick check on the headset (FOV/curved/flip should be live through `setLayout`).
