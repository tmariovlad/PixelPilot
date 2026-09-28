# Presets: switch the air unit's video mode and quality from the headset (design, 2026-09-27)

Status: **approved 2026-09-27 (coordinator d2). App side implemented; on the headset against a fake air 2/2 commits + 2/2 reverts (2026-09-28); real thumbsticks and the real air side (c8) pending.** See [Implementation (app side)](#implementation-app-side-2026-09-27). App side: this repo (PixelPilotXr). Air side: the OpenIPC project
(session c8, writes on `.132` through session a61381). The message format follows c8's proposal. Air-side mechanics
are marked as questions for c8 at the end.

User decisions (2026-09-27, via the coordinator d2):
- **One confirmation (a hold) is enough, also when armed.** The panel shows a short warning.
- **Two separate axes:**
  - **MODE** (Race / Balanced / Wide / Balanced-lite) restarts waybeam;
  - **QUALITY** (2 / 4 / 6 Mbit/s) applies live, without a restart.
  - The air caps the bitrate for the current airtime, and the app shows the effective bitrate, not only the requested one.

## Axis 1: MODE

Glass-to-glass ranges from the W3c budget ([g2g-budget.md](g2g-budget.md#field-of-view-against-latency-480p167-vs-720p120-vs-1080p90-scaled-w3c-2026-09-27)),
all at 2000 kbit/s, FEC 4/8, MCS2, 12 dBm, adaptive link on [PROVEN there].

| Air name | Shown as | Sensor mode → encode | G2G at 2 Mbit/s | Field of view (sensor share) | Detail |
|---|---|---|---|---|---|
| `race` | **Race** | 640×480 @ 167 (crop) | 26.7 – 32.0 ms | 33 × 44 % | 19.3 px/% |
| `balanced` | **Balanced** | 1280×720 @ 119.2 | 33.0 – 38.3 ms | 66 × 66 % | 19.2 px/% |
| `balanced-lite` | Balanced-lite | 1280×720 @ 119.2 → VPE 848×480 | 31.3 – 37.6 ms | 66 × 66 % | ~13 px/% [INFERRED: 848 px over 66 %] |
| `wide` | **Wide** | 1920×1080 @ 90 → VPE 848×480 | 35.3 – 41.6 ms | 99 × 98 % | 8.6 px/% |

**What a mode switch costs.**
- **Time from the command to a stable new encoder: ~10–14 s** [c8 / a61381, `w3_switch` timing on the air].
- **Time the picture is actually frozen on the Quest: 3.1–3.6 s**, 8 switches measured. For the rest of the 10–14 s the
  old mode keeps playing. On the Quest the first new RTP packet arrives 3.0–3.5 s after the last old frame, and the
  decoder then adapts in place in 29–55 ms [PROVEN: [audit § final slot](research/2026-09-27-xr-ux-audit.md#final-slot-on-the-headset-2026-09-27), [data](data/2026-09-27-final-switch-gap.txt)].
- So the panel warning reads `switch ~10–14 s, picture frozen ~4 s` (decided by the coordinator).

## Axis 2: QUALITY

| Level | Requested | Cost against 2 Mbit/s |
|---|---|---|
| **Q2** | 2000 kbit/s | 0 (today's REC) |
| **Q4** | 4000 kbit/s | about +1.7 ms capture → decoded [INFERRED: slot 2 measured 4000 vs 2000 = −2.74 vs −4.46 ms against 8000 at 480p167, [g2g-budget § slot 2](g2g-budget.md#air-unit-levers-measured-in-one-trace-2026-09-27-slot-2)] |
| **Q6** | 6000 kbit/s | about +3 to +4 ms [SPECULATION: between the measured 4000 and 8000 points at 480p167; not measured at 720p/1080p] |

- The cost is airtime: a larger frame spreads over more packets on the radio. So it grows with the bitrate and is
  similar across modes at the same MCS [INFERRED: slot 2, where the first packet moved by only 0.3–0.7 ms].
- The cost is shown next to the level, labelled "est.". The Q6 value becomes a measured number after one in-trace A/B.
- **Live, no restart.** The bitrate is live in waybeam's API [PROVEN: slot 2 switched `video0.bitrate` live]. But the
  same API also writes `/etc/waybeam.json` (`venc_api.c:399`, `:1923-1930`, [HANDOFF](HANDOFF.md)), which clashes with
  rule 4 below. c8 needs a live bitrate path that does not persist [open question 2].
- **The cap belongs to the air.** alink_air knows the current MCS and airtime. The app sends the requested level; the
  air runs `effective = min(requested, cap(current MCS))` and re-evaluates it whenever alink changes the MCS. The app
  never computes a cap. The `state` beacon carries both `req_kbps` and `kbps` (the effective value), and the panel
  shows the effective one, with `(capped)` when they differ.

## 1. UX in XR

**Inputs.** X01 already uses A/X (compact/detailed panel) and B/Y (hide/show) on Touch controllers, and select on the
simple profile ([XrInput.cpp](../../app/xr/src/main/cpp/XrInput.cpp)). Presets use inputs nobody uses yet, on either
hand:

| Input | Action |
|---|---|
| **Thumbstick left / right** (flick past 0.7, re-armed below 0.3) | Opens the menu; moves between MODE choices |
| **Thumbstick up / down** (same flick) | Moves between QUALITY levels |
| **Thumbstick click, held 1 s** | Applies what is highlighted: a mode, a quality, or both. A bar fills while held; releasing early does nothing |
| **Thumbstick click, held 3 s on the active mode + quality** | "Save as default" (rule 4) |
| B/Y while the menu is open | Closes the menu instead of hiding the panel |
| No input for 6 s | The menu closes by itself |

A flick has to be pushed on purpose, and nothing is applied without the 1 s hold, so a knock on the controller cannot
switch anything. The simple profile (select only) gets no presets. The 2D app can offer the same list later (out of
scope).

**What the panel shows.**
- **Menu line** (over the panel): `MODE ◀ Wide ▶ 1080p90→848×480  FOV 99 %  35–42 ms` and
  `QUALITY ▲ 4 Mbit ▼  est. +1.7 ms  now 2.0 Mbit`, with `hold ● 1 s` and the active choice marked.
  - When the highlighted MODE differs from the active one, the menu adds `switch ~10–14 s, picture frozen ~4 s`.
  - When armed, it also adds `ARMED`, in the alert colour.
  - A QUALITY-only change shows no warning.
- **While a mode applies** (headline band, alert colour): `SWITCHING TO Wide… <s> s`, counting down the revert time.
  The last frame stays on the quad (frozen, as today).
- **Afterwards**:
  - success: `Wide ✓` for 3 s;
  - revert: `REVERTED to Race: no video from Wide` for 5 s;
  - refusal: `NOT APPLIED: air busy | no reply from air | <reason>`.
- **The detailed panel** always shows the active mode and the effective bitrate in the link line, from the air's `state`
  beacon. A switch done elsewhere is therefore visible too.

Headlines stay within the 40-character limit that the panel headline test checks ([PanelText](../../app/xr/src/main/java/com/openipc/xr/PanelText.java)).

## 2. Protocol app ↔ air (through the wfb tunnel)

**Transport.**
- UDP on the tunnel: the app on `10.5.0.3` (the VPN address, [WfbNgVpnService.java](../../app/src/main/java/com/openipc/pixelpilot/WfbNgVpnService.java)),
  the air on `10.5.0.10`, port **9998** [proposal; c8 to confirm it is free]. The alink reports use the same path, to
  `10.5.0.10:9999` ([WfbngLink.cpp](../../app/wfbngrtl8812/src/main/cpp/WfbngLink.cpp)).
- The air accepts requests only from `10.5.0.0/24`, like the alink filter.
- The app keeps one UDP socket for the whole XR session. The air replies to the sender's address and port, and sends its
  beacon to the last requester, so the headset needs no fixed listen port.
- Inbound traffic to `10.5.0.3` works: a ping from the Quest to `10.5.0.10` got its replies back through the tunnel,
  3–7 ms [PROVEN: final-slot pre-check]. UDP to the app's own socket takes the same path [INFERRED; the fake daemon
  checks it first].

**Messages.** One ASCII line per datagram, `VMODE1 <verb> key=value ...`, versioned like the PPXR1 report
([phase-lock-protocol.md](phase-lock-protocol.md)). The app chooses `seq`, and the reply echoes it.

| Request (app → air) | Reply (air → app) |
|---|---|
| `VMODE1 list seq=<n>` | `VMODE1 list seq=<n> active=<mode> default=<mode> kbps=<req> presets=<p>,<p>,... qualities=<q>,<q>,...` |
| `VMODE1 apply seq=<n> [preset=<mode>] [kbps=<req>] revert_s=<s>` | `VMODE1 ack seq=<n> state=accepted token=<t>`, or `state=busy`, or `state=error reason=<code>` |
| `VMODE1 commit seq=<n> token=<t>` | `VMODE1 ack seq=<n> state=committed`, or `state=error reason=no_pending` |
| `VMODE1 save_default seq=<n>` (the active mode + requested bitrate) | `VMODE1 ack seq=<n> state=saved`, or `state=error reason=enospc\|fail` |
| (air, 1 Hz and on every change) | `VMODE1 state preset=<mode> phase=<p> pending=<mode> left_s=<s> kbps=<eff> req_kbps=<req> mcs=<m> fps=<x>` |

- One preset `<p>` is `<mode>|<label>|<desc>|<fov>|<g2g>`, e.g. `wide|Wide|1920x1080@90>848x480|99x98|35.3-41.6`.
  `desc` is `<sensor WxH>@<fps>`, plus `><encode WxH>` when the VPE scales. `fov` is the sensor share in %, and `g2g`
  the measured glass-to-glass range in ms (`-` if not measured). No field contains a space, `|` or `,`.
- One quality `<q>` is `<kbps>|<est. ms against the lowest>`, e.g. `4000|1.7`.
- `phase` is `ok | applying | pending | reverted`. `pending` means the new mode runs and waits for the app's commit.
- A bitrate-only `apply` needs no commit: it is live and harmless, and the ack comes back with `state=committed`.
- Error reasons: `unknown_preset`, `bad_kbps`, `fail` (waybeam did not start, and the air has already reverted),
  `bad_request`, `no_pending`, `enospc`. Arming is **not** a refusal reason (user decision).
- **One mode switch at a time.** A request during a switch gets `state=busy` instead of silence, so the app can show
  `air busy`.
- **Reliability.** The app resends a request every 300 ms, up to 5 times, until a reply with its `seq` arrives. The air
  keeps the last reply per `seq`, so a repeated `apply` is not applied twice. With no reply after 5 tries, the panel
  shows `no reply from air` and nothing has changed.

**Who receives it on the air** [proposal, c8 decides]: a small separate daemon (`vmoded`) rather than an alink_air
extension.
- It restarts waybeam and runs a revert timer, which alink_air should not have to wait on.
- It can be deployed and rolled back on its own.
- It needs two links to alink_air: the bitrate cap, and a "waybeam restarted" notice, so that alink re-applies its
  bitrate and FEC (the `.orig_bitrate` race, OpenIPC O109, is the known trap there).

## 3. Safety

- **A single 1 s hold, armed or not** (user decision). The menu warns before a mode switch (see 1) and marks `ARMED`.
  A QUALITY change is live and needs only the same hold, with no warning.
- **Confirm-or-rollback, with the timer on the air:**
  1. `apply` carries `revert_s` = **25 s** by default. That is c8's 10–14 s to a stable encoder, plus the time for the
     app to see 30 frames, plus margin for one slow restart. The app sends the value, so it can be tuned without an air
     update.
  2. The air starts the new mode and enters `pending`.
  3. The app sends `commit` once it has decoded 30 frames at the new mode's resolution (the decoder reports the size,
     `onVideoRatioChanged`).
  4. With no commit in time, the air restores the previous mode by itself. The cause can be no picture on the Quest, a
     wrong resolution, or a dead uplink. The air also reverts at once if the encoder does not come back (c8's check).
- Because the timer runs on the air, a revert happens even if the uplink is gone.
- Worst case for the pilot: up to 25 s on a failed mode, then the revert's own restart (~10–14 s, picture frozen ~4 s
  of it). The app shows the countdown and the revert. The revert time should be calibrated on the first device tests
  (median command → commit, N ≥ 4) and then set to about twice that value [open point 3].

## 4. Persistence (the air's `/overlay` is nearly full, jffs2)

- **Neither a mode switch nor a bitrate change writes under `/etc`.**
  - Mode: the daemon builds the waybeam config for the mode in RAM, in `/tmp`, from the base `/etc/waybeam.json` plus
    the mode's fields. It starts waybeam on that file, either through a config-path option or through a bind mount of
    the `/tmp` file over `/etc/waybeam.json`, which does not touch jffs2 [SPECULATION: c8 to check which works with
    waybeam `13b85893` and `start.sh`].
  - Bitrate: through a live path that does not persist [open question 2].
- After a reboot the air starts on its default (today REC = Race at 2 Mbit/s). A choice is not remembered unless it is
  saved.
- **"Save as default"** is a separate, explicit action: hold 3 s on the active choice. `save_default` is the only request
  that writes under `/etc`. It writes once, and checks free space first; with too little space it answers `enospc` and
  writes nothing.
- The mode definitions live in the daemon (compiled in, or a read-only file installed once with it; c8's choice).
  Switching does not rewrite them.

## Where each fact lives (single source of truth; coordinator's decision)

- **Air:** everything about a preset: which modes and quality levels exist, their encoder parameters, the bitrate cap,
  and the numbers shown to the pilot (label, FOV, measured G2G, estimated bitrate cost). The G2G and FOV values are
  taken from [g2g-budget.md](g2g-budget.md) (W3c) when the air config is written; the air config is canonical after
  that. The app gets all of it through `list`.
- **App:** nothing about presets is hard-coded. It only holds its own timing: the hold times, the revert time it asks
  for, and the frames it needs before `commit`.

## App-side pieces (after approval)

| Piece | Where | Responsibility |
|---|---|---|
| `VmodeClient` | `app/src/main/java/.../VmodeClient.java` | the UDP protocol: send, retry, parse, the beacon; no UI |
| `PresetCatalog` | `app/xr/src/main/java/com/openipc/xr/PresetCatalog.java` | the parsed `list`: modes, qualities, active choice (data only) |
| `PresetMenu` | `app/xr/src/main/java/com/openipc/xr/PresetMenu.java` | menu state: highlight on two axes, hold timers, timeouts; pure logic, with JVM tests like `PanelMode` |
| `XrInput` | `app/xr/src/main/cpp/XrInput.cpp` | new actions: thumbstick x/y (float) and thumbstick click (bool) on both hands; new `INPUT_*` bits |
| Panel | `XrStatsRenderer` / `PanelText` | the menu lines and headlines above |
| Commit | `XrVideoActivity` | counts decoded frames at the new size, then sends `commit` |

Tests:
- JVM:
  - `PresetMenu`: holds, axes, timeouts;
  - `VmodeClient` against a fake UDP peer: retry, duplicate `seq`, `busy`/error replies, beacon parse;
  - `PresetCatalog`: merge, unknown `desc`.
- Offline air stand-in: `scripts/quest/vmode_fake.py`, like `mavlink_fake.py`. It runs the whole flow on the headset,
  including a forced revert, before the air side exists.
- On the device:
  - N ≥ 2 mode switches per pair, with the picture gap from [switch_gap.py](../../scripts/quest-latch/switch_gap.py)
    and the command → commit time;
  - one forced revert;
  - one in-trace A/B of Q2/Q4/Q6 to replace the estimated costs.

## Open points

Decided (coordinator, 2026-09-27): the warning wording above; QUALITY must not write the flash (c8 proposes a tmpfs
bind mount over `/etc/waybeam.json` for the session, which covers mode switches, bitrate sets and alink's own sets);
the app side is built and tested against a fake air until the air side is approved.

For c8 (air side; c8's design: OpenIPC repo `repos/tasks/vmode-presets-2026-09-27/00-DESIGN-vmode-presets.md`):
1. A live bitrate path that does not write `/etc/waybeam.json` (the waybeam API persists it today), and where the cap
   per MCS lives (alink_air).
2. Daemon or alink_air extension, and the UDP port (9998 proposed). How the daemon tells alink_air about a waybeam
   restart.
3. How waybeam starts on a `/tmp` config without writing `/etc`: a config-path option or a bind mount.
4. Whether the VPE-scaled modes need anything beyond the waybeam config (W3c ran them through `w3_switch`).

Answers for c8's questions (app side):
- **Decoder:** nothing is needed from the air before a switch. A resolution change is handled in place (29–55 ms;
  `501094a` removed the rebuild), and the quad follows the new aspect (`onVideoRatioChanged`). The first frame of the
  new stream must be an IDR, which a waybeam start gives [INFERRED: 0 undecoded frames after the measured switches].
- **List:** the app takes everything from the air's `list`, including the Quest-measured numbers.
- **Rate:** one mode switch at a time, fine. The app asks for `state=busy` instead of silence.

## Implementation (app side, 2026-09-27)

Built as designed, with the approved decisions above. Nothing about presets is hard-coded in the app: the menu shows
only what the air's `list` sends.

| File | What it does |
|---|---|
| [XrInput.cpp](../../app/xr/src/main/cpp/XrInput.cpp) / [.h](../../app/xr/src/main/cpp/XrInput.h) | thumbstick flicks per hand (on past 0.7, re-armed under 0.3) and thumbstick click down/up, as new event bits (`XrBridge.INPUT_STICK_*`) |
| [PresetCatalog.java](../../app/xr/src/main/java/com/openipc/xr/PresetCatalog.java) | the parsed `list` (modes, qualities, active choice); `encodeSize()` from `desc` |
| [PresetMenu.java](../../app/xr/src/main/java/com/openipc/xr/PresetMenu.java) | the menu: two axes, 1 s apply hold, 3 s save hold on the active choice, 6 s idle close, B/Y closes it; menu lines |
| [PresetStatus.java](../../app/xr/src/main/java/com/openipc/xr/PresetStatus.java) | the headline: `SWITCHING TO Wide... 25 s`, `Wide ACTIVE`, `REVERTED TO Race: NO VIDEO`, `NOT APPLIED: …` (≤ 40 chars) |
| [VmodeProtocol.java](../../app/src/main/java/com/openipc/pixelpilot/VmodeProtocol.java) | VMODE1 request lines and reply parsing |
| [VmodeClient.java](../../app/src/main/java/com/openipc/pixelpilot/VmodeClient.java) | one UDP socket, resend every 300 ms × 5, duplicate replies dropped; target `10.5.0.10:9998`, or the debug pref `vmode_air` = `"<IPv4>:<port>"` |
| [VmodeSession.java](../../app/src/main/java/com/openipc/pixelpilot/VmodeSession.java) | menu action → request; acks and beacon → catalog, headline, effective bitrate; `revert_s` 25 |
| [CommitGate.java](../../app/src/main/java/com/openipc/pixelpilot/CommitGate.java) | commit only after the air says `pending` **and** 30 frames decoded at the new size. The size alone would match old frames when two modes share 848×480 |
| [XrVideoActivity.java](../../app/src/main/java/com/openipc/pixelpilot/XrVideoActivity.java) | wiring: the stats tick feeds input, frames and size; the preset headline wins while switching; menu lines above the panel; `Race 2.0 Mbit (capped)` on the video line; started only with the wfb link |
| [vmode_fake.py](../../scripts/quest/vmode_fake.py) | the fake air: same protocol, revert timer, `--switch-s`, `--fail <mode>`, `--busy`, `--same-size` (lists `race-b` at 640×480, so a commit can happen while the real video stays at Race). c8 uses it as the conformance reference for the air's receiver |
| [DebugInput.java](../../app/xr/src/main/java/com/openipc/xr/DebugInput.java) | debug builds only: `adb shell am broadcast -a com.openipc.pixelpilot.xr.DEBUG_INPUT --es input <left\|right\|up\|down\|press\|release\|detail\|visibility>`. The bits go into `XrBridge.injectInputEvents`, the same path the thumbsticks use |
| [preset_flow.py](../../scripts/quest/preset_flow.py) | the scripted headset run: fake air on the PC, `vmode_air` pointed at it, menu driven by broadcasts, screenshots per stage, prefs restored; `--fail` for the revert path |

Aligned with c8's air design (§13/§14/§16, OpenIPC repo `repos/tasks/vmode-presets-2026-09-27/00-DESIGN-vmode-presets.md`):
- **Commit bound to the token.** The gate arms only on a `phase=pending` beacon whose `token` equals the token of our
  `accepted`. A stale pending from an earlier apply, or a switch started by another requester, cannot arm it.
- The beacon carries its own counter in `seq`, and the client does not treat it as a reply.
- The phases `reverting` and `failed` are shown as a revert.
- `list` is resent every 60 s as a keepalive, so the air keeps sending its beacon.
- The air lists only the qualities it can deliver (v1: 2000 and 4000). The menu takes any list length.
- The air clamps `revert_s` to 15–60 s; the app sends 25.

Tests (all offline, 2026-09-27):
- JVM, :app:xr: `PresetMenuTest` 12, `PresetStatusTest` 3, `DebugInputTest` 2.
- JVM, :app: `VmodeProtocolTest` 4, `VmodeSessionTest` 10, `CommitGateTest` 5, `VmodeClientTest` 3 (real UDP on
  localhost, stable over 4 reruns).
- Full suites: app 60, xr 63, videonative 18, 0 failures.
- Python: [test_vmode_fake.py](../../scripts/quest/test_vmode_fake.py) 7: list, switch + commit (token and seq in the
  beacon), revert without commit, a failing mode, busy + idempotent resend, the same-size mode, bitrate-only.
- The native flick code has no host test; it gets checked on the headset.

Next, on the headset:
1. `python3 preset_flow.py <label>`, then `python3 preset_flow.py <label> --fail`. Both use the fake air on the PC,
   with the menu driven by the debug broadcast. This checks the menu, the countdown, the commit and the revert on the
   headset. The real thumbsticks are checked with the user at the end, together with the RTL replug.
2. After the air side exists, repeat on the tunnel, and measure picture gap, command → commit time, and Q2/Q4/Q6 cost.

## On the headset against the fake air (2026-09-28)

`preset_flow.py` × 4 on the Quest, build `c31ddd0f` (`672aaa6`). The menu was driven by the debug broadcast; the fake air
ran on the PC (UDP 9998, reached without any firewall change). The real air unit was untouched and streamed Race
throughout. Data: [fake-air logs](data/2026-09-28-preset-flow.txt).

| Run | Target | Result | Timeline (s from the run start) |
|---|---|---|---|
| ok1 | `race-b` (640×480) | **PASS**: committed | apply 22.1 → pending 25.1 → commit 41.3. The link delivered no video for the first ~20 s after the app restart (NO SIGNAL), so the 30 frames took until 41 s |
| ok2 | `race-b` | **PASS**: committed | apply 42.5 → pending 45.6 → commit 46.1 (0.5 s: 30 frames at 167 fps) |
| fail1 | `wide` (never pending) | **PASS**: reverted | apply 41.9 → reverted 66.9 (= `revert_s` 25) |
| fail2 | `wide` | **PASS**: reverted | apply 42.1 → reverted 67.1 |

[PROVEN: data file; screenshots below.] A first fail1 attempt stopped before any request reached the fake. Its error
was filtered out of the console, so the cause is not known. It left no trace on the headset, and the rerun above
passed.

What the headset showed ([commit run](img/presets-flow-commit.jpg), [revert run](img/presets-flow-revert.jpg)):
- the menu `MODE < Race > 640x480@167 (active)` / `FOV 33x44 % G2G 26.7-32.0 ms` / `QUALITY ^ 2 Mbit v`;
- on another mode the hint `hold stick 1 s: switch ~10-14 s, picture frozen ~4 s`;
- then `SWITCHING TO Wide... 24 s`, then `Race-B ACTIVE` or `REVERTED TO Race: NO VIDEO`;
- on the video line `Race-B 2.0 Mbit` [PROVEN: screenshots].

Found and fixed: `list` went out twice at start (seq 1 and 2, ~0.4 s apart in every run). The keepalive timer started
at 0 before the first stats tick. It now starts at the first tick (`VmodeSession.tick`, with a regression test that
fails without the fix).

Still open on the headset: the real thumbsticks (with the user, together with the RTL replug), and the real air
receiver (c8, after its deploy).
