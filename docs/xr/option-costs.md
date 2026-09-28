# Option costs (generated)

**Canonical source: [`app/xr/src/main/res/raw/option_costs.json`](../../app/xr/src/main/res/raw/option_costs.json).**
This page is generated from it by [option_costs_md.py](../../scripts/quest/option_costs_md.py); do not edit it by hand.
The headset menu (pixelpilot-xr-25) reads the JSON through `OptionCosts` (app/xr) and shows the cost next to each
option. Keywords: option costs, menu labels, cost table, latency cost, fps, post-FEC loss, bitrate, MCS, FEC, 2SS,
TX power, FIF, IDR, FRZ, codec, costuri opțiuni, meniu, etichete, latență.

**One place per number.** The G2G and FOV of the presets the air unit lists (`race`, `balanced`, `balanced-lite`, `wide`) come only from the air's
VMODE1 `list` ([presets-design.md](presets-design.md)); this table never copies them, and the JVM test
(`OptionCostsTest`) enforces it. A preset the air does not list yet (e.g. HD) carries its numbers here until it does;
then they move to the air's `list` and leave this table. Moving G2G/FOV between the air and this table is an open
question for the owner of the air's preset receiver (vmoded).

Updated 2026-09-29. Tags: [PROVEN] measured, [INFERRED] derived from measurements, [SPECULATION] not measured.
Empty cells = not measured. `a…b` = the spread over runs. In a link or lever delta, p95 is the p95 of the
same latency metric (not a difference of p95s).


## Video mode

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `mode.race` | Race | `race` | W3c: 2000 kbit/s, FEC 4/8, MCS2, 12 dBm, O112 pin, N = 2 (main arm + repeat arm) |  |  | 0.06…0.17 % |  | [PROVEN] | docs/xr/g2g-budget.md:236,260 (2026-09-27) |
| `mode.balanced` | Balanced | `balanced` | W3c: 2000 kbit/s, FEC 4/8, MCS2, 12 dBm, O112 pin, N = 2 |  |  | 0.14 % |  | [PROVEN] | docs/xr/g2g-budget.md:237 (2026-09-27) |
| `mode.balanced-lite` | Balanced-lite | `balanced-lite` | W3c extra arm: 2000 kbit/s, FEC 4/8, MCS2, 12 dBm; one loss burst in one of the two steps |  |  | 0.45 % |  | [PROVEN] | docs/xr/g2g-budget.md:261 (2026-09-27) |
| `mode.wide` | Wide | `wide` | W3c: 2000 kbit/s, FEC 4/8, MCS2, 12 dBm, O112 pin, N = 2; loss-vs-mode attribution unproven |  |  | 0.46 % | ~2.2x softer than Race per % of view | [PROVEN] | docs/xr/g2g-budget.md:238,253-254 (2026-09-27) |
| `mode.hd` | HD | `hd` | BASE: 1080p90 native, 8000 kbit/s, FEC 4/6, MCS2, 12 dBm, N = 2. Moves to the air's list once the air lists HD | G2G 46.6…51.9 ms |  | 2.06 % |  | [INFERRED] | docs/xr/g2g-budget.md:220 (segments PROVEN; ISP and panel terms INFERRED) (2026-09-27) |

## Bitrate

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `bitrate.8000` | 8 Mbit/s | `8000` | slot 2: 640x480 @ 166.6, MCS2, FEC 4/6, N = 2 | Δ +0 ms vs `bitrate.8000` |  |  |  | [PROVEN] | docs/xr/g2g-budget.md:81 (2026-09-27) |
| `bitrate.6000` | 6 Mbit/s | `6000` | not measured: lies between the 4000 and 8000 points at 480p167 |  |  |  | about +3 to +4 ms vs 2000, not measured | [SPECULATION] | docs/xr/presets-design.md:39 (2026-09-27) |
| `bitrate.4000` | 4 Mbit/s | `4000` | slot 2: 640x480 @ 166.6, MCS2, FEC 4/6, N = 2 | Δ -3…-2.3 ms vs `bitrate.8000` |  |  |  | [PROVEN] | docs/xr/g2g-budget.md:82 (2026-09-27) |
| `bitrate.2000` | 2 Mbit/s | `2000` | slot 2: 640x480 @ 166.6, MCS2, FEC 4/6, N = 2; picture from stills with motion | Δ -4.8…-4.1 ms vs `bitrate.8000` | 166.6 |  | smears with motion | [PROVEN] | docs/xr/g2g-budget.md:83,86; docs/xr/link-envelope.md:725-726 (2026-09-27) |

## Link states (MCS × bitrate × FEC)

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `link.m1b2f46` | MCS1 2M 4/6 | `m1b2f46` | phase 2: 480p167, 17 dBm, streamed capture (absolute loss inflated) | Δ +0 ms vs `link.m1b2f46` |  | 0.18…0.21 % |  | [PROVEN] | docs/xr/link-envelope.md:104 (2026-09-27) |
| `link.m2b2f46` | MCS2 2M 4/6 | `m2b2f46` | phase 2: 480p167, 17 dBm, streamed capture (absolute loss inflated) | Δ -0.43 ms vs `link.m1b2f46` |  | 0.32 % |  | [PROVEN] | docs/xr/link-envelope.md:105 (2026-09-27) |
| `link.m2b2f48` | MCS2 2M 4/8 | `m2b2f48` | phase 2: 480p167, 17 dBm, streamed capture (absolute loss inflated); at 12 dBm 0.24 % | Δ -0.1 ms vs `link.m1b2f46` |  | 0 % |  | [PROVEN] | docs/xr/link-envelope.md:106,766 (2026-09-27) |
| `link.m2b4f48` | MCS2 4M 4/8 | `m2b4f48` | phase 2: 480p167, 17 dBm, streamed capture (absolute loss inflated) | Δ +1.48 ms vs `link.m1b2f46` |  | 0.07 % |  | [PROVEN] | docs/xr/link-envelope.md:109 (2026-09-27) |
| `link.m7b25f46` | MCS7 25M 4/6 | `m7b25f46` | G5: 1080p90, 17 dBm, ch157, alink off, 1SS STBC long GI, 60 s steps, x2; latency vs this state's drift line | Δ +0 (p95 5…5.3) ms vs `link.m7b25f46` | 85.9…86.2 | 0.47…0.54 % |  | [PROVEN] | docs/xr/link-envelope.md:213 (2026-09-29) |
| `link.m7b20f46` | MCS7 20M 4/6 | `m7b20f46` | G5: 1080p90, 17 dBm, ch157, alink off, 1SS STBC, N = 1 | Δ -3.3 (p95 1.8) ms vs `link.m7b25f46` | 87.7 | 0.35 % |  | [PROVEN] | docs/xr/link-envelope.md:217 (2026-09-29) |
| `link.m7b20f48` | MCS7 20M 4/8 | `m7b20f48` | G5: 1080p90, 17 dBm, ch157, alink off, 1SS STBC, N = 1 | Δ +19.8 (p95 44.6) ms vs `link.m7b25f46` | 88.9 | 0.22 % | air TX queue knee | [PROVEN] | docs/xr/link-envelope.md:216,230 (2026-09-29) |
| `link.m7b16f48` | MCS7 16M 4/8 | `m7b16f48` | G5: 1080p90, 17 dBm, ch157, alink off, 1SS STBC, N = 1 | Δ -2.8 (p95 1.9) ms vs `link.m7b25f46` | 89.8 | 0.13 % |  | [PROVEN] | docs/xr/link-envelope.md:215,228 (2026-09-29) |
| `link.m12b20f48` | MCS12 20M 4/8 | `m12b20f48` | G6: 1080p90, 17 dBm, ch157, alink off, 2SS long GI, N = 1 | Δ -1.4 (p95 3.3) ms vs `link.m7b25f46` | 89.5 | 0.13 % |  | [PROVEN] | docs/xr/link-envelope.md:218,228 (2026-09-29) |
| `link.m13b25f48` | MCS13 25M 4/8 | `m13b25f48` | G6: 1080p90, 17 dBm, ch157, alink off, 2SS long GI, N = 1 | Δ +0.1 (p95 5.5) ms vs `link.m7b25f46` | 87.6 | 0.33 % |  | [PROVEN] | docs/xr/link-envelope.md:220 (2026-09-29) |
| `link.m13b30f47` | MCS13 30M 4/7 | `m13b30f47` | G6: 1080p90, 17 dBm, ch157, alink off, 2SS long GI, N = 1 | Δ +1.9 (p95 7.9) ms vs `link.m7b25f46` | 84.7 | 0.59 % | 2SS clean limit | [PROVEN] | docs/xr/link-envelope.md:223,231 (2026-09-29) |
| `link.m7b25f810` | MCS7 25M 8/10 | `m7b25f810` | above-25 run: 1080p90, 17 dBm, ch157, alink off, 1SS STBC, N = 1 | Δ -0.45 (p95 3.22) ms vs `link.m7b25f46` |  | 0.65 % |  | [PROVEN] | docs/xr/link-envelope.md:370,384 (2026-09-28) |
| `link.m12b25f46` | MCS12 25M 4/6 | `m12b25f46` | above-25 run: 1080p90, 17 dBm, ch157, alink off, 2SS, N = 1 | Δ +0.4 (p95 3.25) ms vs `link.m7b25f46` |  | 0.73 % |  | [PROVEN] | docs/xr/link-envelope.md:372,383 (2026-09-28) |
| `link.m13b35f46` | MCS13 35M 4/6 | `m13b35f46` | above-25 run: 1080p90, 17 dBm, ch157, alink off, 2SS, N = 1 | Δ +6.89 (p95 16.4) ms vs `link.m7b25f46` |  | 1.48 % |  | [PROVEN] | docs/xr/link-envelope.md:375,381 (2026-09-28) |
| `link.m7b30f810` | MCS7 30M 8/10 | `m7b30f810` | ceiling grid B: 1080p90, 17 dBm, ch157, alink off, 1SS STBC, N = 1; latency vs that run's drift line | Δ +2.94 (p95 8.02) ms vs `grid B drift line` | 83.5 | 0.82 % | 1SS bitrate ceiling | [PROVEN] | docs/xr/link-envelope.md:337,350 (2026-09-29) |
| `link.m12b30f810` | MCS12 30M 8/10 | `m12b30f810` | ceiling grid B: 1080p90, 17 dBm, ch157, alink off, 2SS, N = 1; latency vs that run's drift line | Δ +1.01 (p95 4.37) ms vs `grid B drift line` | 81.8 | 0.93 % |  | [PROVEN] | docs/xr/link-envelope.md:341,351 (2026-09-29) |
| `link.m13b38f810` | MCS13 38M 8/10 | `m13b38f810` | ceiling grid B: 1080p90, 17 dBm, ch157, alink off, 2SS, N = 1; latency vs that run's drift line | Δ +2.5 (p95 5.36) ms vs `grid B drift line` | 73.6 | 1.65 % |  | [PROVEN] | docs/xr/link-envelope.md:345,352 (2026-09-29) |

## MCS / guard interval

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `mcs.m7_long_gi` | MCS7 long GI | `m7L` | R5: 1080p90, 25 Mbit/s, FEC 4/6, 17 dBm, ch157, alink off, ABBA x2, 8 x 120 s | Δ +0 ms vs `mcs.m7_long_gi` |  | 0.48…0.51 % |  | [PROVEN] | docs/xr/link-envelope.md:452 (2026-09-28) |
| `mcs.m6_short_gi` | MCS6 short GI | `m6S` | R5: 1080p90, 25 Mbit/s, FEC 4/6, 17 dBm, ch157, alink off, ABBA x2, 8 x 120 s | Δ +0.7 (p95 2) ms vs `mcs.m7_long_gi` |  | 0.28…0.34 % | ~40 % less loss | [PROVEN] | docs/xr/link-envelope.md:453,455 (2026-09-28) |
| `mcs.m6_long_gi` | MCS6 long GI | `m6L` | G5: 1080p90, 25 Mbit/s, FEC 4/6, 17 dBm, ABAB, N = 2 | Δ +55 (p95 60…61) ms vs `link.m7b25f46` | 85.7…86.2 | 0.42…0.48 % | air TX queue full | [PROVEN] | docs/xr/link-envelope.md:214,229 (2026-09-29) |

## FEC

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `fec.4_6` | FEC 4/6 | `4/6` | slot 2: 480p167, 8000 kbit/s, MCS2 | Δ +0 ms vs `fec.4_6` |  |  |  | [PROVEN] | docs/xr/g2g-budget.md:93 (2026-09-27) |
| `fec.4_5` | FEC 4/5 | `4/5` | slot 2: 480p167, 8000 kbit/s, MCS2; at m7b25 1080p90: 3.9-4.3 % vs 2.3-2.6 % after FEC | Δ -1.7…-1.2 ms vs `fec.4_6` |  |  | more loss than 4/6 | [PROVEN] | docs/xr/g2g-budget.md:94; docs/xr/link-envelope.md:570 (2026-09-27) |
| `fec.4_8` | FEC 4/8 | `4/8` | phase 2: 480p167, 2 Mbit/s, MCS2, 17 dBm, streamed capture; 4/8 beats 4/6 at every 1080p90 grid point | Δ +0.33 ms vs `fec.4_6` |  | 0.32 % → 0 % |  | [PROVEN] | docs/xr/link-envelope.md:118,656 (2026-09-27) |
| `fec.8_10` | FEC 8/10 | `8/10` | above-25 run: m7b25, 1080p90, 17 dBm, N = 1; off = 4/6, on = 8/10 | Δ -2 ms vs `fec.4_6` |  | 0.49 % → 0.65 % |  | [PROVEN] | docs/xr/link-envelope.md:368,370,384 (2026-09-28) |
| `fec.8_12` | FEC 8/12 | `8/12` | slot 2: 480p167, 8000 kbit/s, MCS2; inside the baseline spread | Δ -0.7…+0 ms vs `fec.4_6` |  |  | not a lever | [PROVEN] | docs/xr/g2g-budget.md:95,98 (2026-09-27) |

## Spatial streams (1SS / 2SS)

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `streams.stbc_off` | STBC off | `stbc_off` | 480p167 m2b2f48, 12 dBm, 6 x 30 s alternating, streamed capture; off = STBC on, on = STBC off | Δ +0.21 ms vs `STBC on` |  | 0 % → 0.18 % | ~9 lower RSSI column | [PROVEN] | docs/xr/link-envelope.md:149-150,155 (2026-09-28) |
| `streams.2ss` | 2 streams | `2ss` | G5 vs G6 and the above-25 run: 1080p90, 17 dBm, ch157; per-state costs are under Link states |  |  |  | per-chain RSSI ~4 dB lower than 1SS STBC, same SNR | [PROVEN] | docs/xr/link-envelope.md:231,378 (2026-09-29) |

## Air TX power

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `txpower.12` | 12 dBm | `12` | power bracket: 480p167 REC (MCS2, FEC 4/8, 2 Mbit/s), N = 3, streamed capture; RSSI column 68.7 | Δ +0.01 ms vs `txpower.17` |  | 0.02 % | boot default | [PROVEN] | docs/xr/link-envelope.md:674,686 (2026-09-28) |
| `txpower.17` | 17 dBm | `17` | power bracket: 480p167 REC, N = 3; RSSI column 74.0 | Δ +0 ms vs `txpower.17` |  | 0.02 % |  | [PROVEN] | docs/xr/link-envelope.md:675 (2026-09-28) |
| `txpower.20` | 20 dBm | `20` | power bracket: 480p167 REC, N = 3; RSSI column 78.0 | Δ +0.07 ms vs `txpower.17` |  | 0.03 % |  | [PROVEN] | docs/xr/link-envelope.md:676 (2026-09-28) |
| `txpower.23` | 23 dBm | `23` | power bracket: 480p167 REC, N = 3; RSSI column 81.0. At MCS7 the link was lost at 22-23 dBm | Δ -0.08 ms vs `txpower.17` |  | 0 % | MCS7 needs <= 20 dBm | [PROVEN] | docs/xr/link-envelope.md:677,585-597 (2026-09-28) |

## Channel

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `channel.157` | Ch 157 | `157` | R3 + R3': m7b25f46, 17 dBm, 1080p90, ABBA x2, 8 x 150 s |  |  | 0.41…0.5 % | strongest signal | [PROVEN] | docs/xr/link-envelope.md:396,407,422 (2026-09-28) |
| `channel.161` | Ch 161 | `161` | R3: inside the neighbour's 80 MHz band |  |  | 0.42…0.56 % |  | [PROVEN] | docs/xr/link-envelope.md:423 (2026-09-28) |
| `channel.165` | Ch 165 | `165` | R3': outside the neighbour's band; signal ~4-6 dB lower than 157 |  |  | 0.5…0.55 % |  | [PROVEN] | docs/xr/link-envelope.md:397,399 (2026-09-28) |

## App levers

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `lever.fif` | FIF | `feed_incomplete_frames` | air m7b30f810, 1080p90, 17 dBm, alink off, ABBA x2, 4 x 90 s; H.264 only |  | 82.4…84.1 → 89.2…89.6 | 0.7…0.92 % → 0.74…0.83 % | smears on loss | [PROVEN] | docs/xr/link-envelope.md:272-282 (2026-09-29) |
| `lever.idr` | IDR | `request_idr_on_loss` | with FIF, user walking, air m7b30f810 1080p90 17 dBm |  |  |  | +keyframes on loss; ~1.1 IDR/s honoured, 0.4/s coalesced by the air | [PROVEN] | docs/xr/link-envelope.md:293,302 (2026-09-29) |
| `lever.frz` | FRZ | `freeze_until_idr` | not measured; expected with request_idr_on_loss on |  |  |  | brief hold on loss; hold ~0.1-0.3 s until the IDR, not measured | [SPECULATION] | docs/xr/link-envelope.md:308 (2026-09-29) |
| `lever.tight_reorder` | Tight reorder | `rtp_tight_reorder` | L3: 480p167 m4b2f44 (no FEC), 8 dBm, 3.5-4.3 % loss; frames after a loss 2.24-2.40 -> 1.68-1.74 ms | Δ -0.18 ms vs `off` |  |  |  | [PROVEN] | docs/xr/g2g-budget.md:204,207 (2026-09-28) |
| `lever.picture_order` | Picture order | `dec_picture_order` | real stream 480p166, N = 3 per state, alternating; decode off 95.5-112.7 ms, on 1.29-1.45 ms | Δ -111.4…-94 ms vs `off` |  |  | off holds ~16 frames | [INFERRED] | docs/xr/real-link.md:162-167 (difference of PROVEN rows) (2026-09-26) |
| `lever.operating_rate` | Operating rate | `dec_operating_rate` | replayed clean single-slice streams, LL on, N = 3; decode LL -> LL + OR on H.264 720p / H.265 720p / H.265 1080p | Δ -0.99…-0.45 ms vs `off` |  |  |  | [INFERRED] | docs/xr/decoder-levers.md:59-61 (difference of PROVEN rows) (2026-09-26) |
| `lever.component` | Decoder component | `dec_component` | OR-only defaults, 12 s single-slice streams, N = 3; c2.qti against the OMX default (empty pref) | Δ +1 ms vs `OMX default` |  |  | c2.qti ~30 % fewer fps | [PROVEN] | docs/xr/decoder-levers.md:71-80 (2026-09-26) |
| `lever.alink` | Adaptive link | `adaptive_link_enabled` | range test at 8 dBm, 480p167, in-trace A-B-A, streamed capture; at 17 dBm +0.10 ms, inside the spread | Δ -0.4 ms vs `off` |  | 1.29…1.65 % → 0.33…0.6 % |  | [PROVEN] | docs/xr/link-envelope.md:748-752,769-772 (2026-09-27) |
| `lever.thread_hints` | XR thread hints | `xr_thread_hints` | Quest 2 runtime |  |  |  | inert: the runtime rejects every hint (-1000003001) | [PROVEN] | docs/xr/decoder-levers.md:27 (2026-09-26) |

## Codec

| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |
|---|---|---|---|---|---|---|---|---|---|
| `codec.h264` | H.264 | `h264` | replayed single-slice streams, OMX default, N = 3; the air stream is H.264 | Δ +0 ms vs `codec.h264` |  |  |  | [PROVEN] | docs/xr/decoder-levers.md:73-82 (2026-09-26) |
| `codec.h265` | H.265 | `h265` | replayed single-slice streams, OMX default, N = 3, same resolution; FIF does not apply to H.265 | Δ +0.1…+0.3 ms vs `codec.h264` |  |  |  | [PROVEN] | docs/xr/decoder-levers.md:82; docs/xr/link-envelope.md:253 (2026-09-26) |
