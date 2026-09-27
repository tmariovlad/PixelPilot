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
- **Temperatures.** Log the air SoC temperature and the Quest thermal status/battery with every step. Stop a step if the
  air SoC runs away (rising without levelling) or goes above the limit the OpenIPC project documents for this board, or
  if the Quest reports a thermal throttling status or battery < 30 %.
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

Filled in by the coordinator as results come back.
