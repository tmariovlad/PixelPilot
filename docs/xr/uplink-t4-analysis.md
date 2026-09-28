# What `adaptive_link_enabled=true` turns on, and why T4's "uplink = half the floor" may be a capture artefact (2026-09-28)

Context: the link-25mbit audit's T4 (OpenIPC repo `repos/tasks/link-25mbit-audit-2026-09-28/T4-T5-RUNBOOK.md`
"T4 result") found post-FEC loss doubled with the Quest uplink on (ABBA×2, 30 s relaunched steps). The T2 control
3 minutes later, uplink on and the app running continuously, lost no more than T4's off steps
([link-envelope.md § T4](link-envelope.md), commit `42109ed`). This file answers the coordinator's question: what the
pref generates, what differs between T4's ON steps and T2, and which test separates the hypotheses. **Analysis only,
no code change** (by the coordinator's decision, until the test below has run).

Keywords: uplink, adaptive link, alink report, TX DESC, half duplex, loss runs, quest_tx_log, streaming logcat, adb
over Wi-Fi, desense, T4, T2, ABBA, confound, legătură ascendentă, pierderi.

## 1. What the pref turns on

`LinkOptions.java:18` passes `adaptive_link_enabled` (default true) to `nativeSetAdaptiveLinkEnabled`; the link reads it
when the TX thread starts (`WfbngLink.cpp:341`). When true, `start_link_quality_thread` (`WfbngLink.cpp:561-677`):

| What | Detail | Frames on air | Tag |
|---|---|---|---|
| Periodic link report | UDP to `10.5.0.10:9999` through the VPN tunnel → UDP 8001 → `TxFrame` → radio port 160, one per `interval_ms` = 1000 / `uplink_rate_hz` (default **4/s**, `LinkOptions.java:65`) | × FEC n/k = **3** (default 1/3, MCS0) → **12/s** | [PROVEN: code] |
| "News" report | Sent at once, outside the grid, when `idr_code` or `fec_change` changed (`UplinkSchedule.h:41-45`, polled every 20 ms). A new `idr_code` is minted on every stats window with `p_lost > 0` (`SignalQualityCalculator.cpp:156-158`); windows come ~3/s (the `tunnel window` log lines are 0.3–0.9 s apart) | ≤ ~3 news/s × 3 → **≤ ~9/s**, only while there is loss | [PROVEN: code; cadence INFERRED from logcat 2026-09-28 11:08] |
| Session-key announce | `TxFrame` re-announces the key when ≥ 1 s passed and a packet arrives (`TxFrame.cpp:772-777`, `SESSION_KEY_ANNOUNCE_MSEC 1000`) | **1/s** | [PROVEN: code] |
| **Quest RTL TX power** | The thread's start calls `SetTxPower(adaptive_tx_power)` on the RTL8812AU (`WfbngLink.cpp:676`; pref default 20, `LinkOptions.java:19`). With the pref false this call never happens, so the RTL stays at devourer's init power | 0 (a setting, not frames) | [PROVEN: code] |

Measured: T4 ON 23.7–24.5 TX/s, T2 22.0–22.5 TX/s, T4 OFF 0.4 TX/s [PROVEN: link-envelope.md T4 table]. The ON value
fits 12 + 1 + ~3 news × 3 [INFERRED]. The residual 0.4/s when off (VMODE `LIST` every 60 s + retries, session key) is
not itemised. The air's alink was **stopped** in both T4 and T2, so the reports and IDR requests changed nothing on
the air side in either run [PROVEN: T4 runbook "useless while the air's alink is stopped"; link-envelope.md T4 header
"air alink + vmoded off"].

## 2. What differs between T4's ON steps and T2

| Factor | T4 ON steps | T2 control (uplink ON) | Tag |
|---|---|---|---|
| Uplink frames | 23.7–24.5/s | 22.0–22.5/s | [PROVEN] |
| RTL TX power call | yes (20) | yes (20; prefs rewritten by `set_prefs` in T4 leave `adaptive_tx_power` at its default) | [INFERRED] |
| Air | `m7b25f46`, 17 dBm, alink off, ~3490 inj/s | `m7b25f46`, alink off, ~3526 inj/s (`air-t2-wifi-control`: tx 3683794 → 4355796 in 190.6 s), RSSI 74–76 in both | [PROVEN] |
| App launch | relaunched every 30 s by `pref_ab.sh` | ≥ 195 s since the last relaunch; very likely the same process as T4's last ON step (T4 ended 1790613465.6, T2 started 1790613630) | [PROVEN / INFERRED] |
| **TX-frame capture** | **`quest_tx_log.sh`: a streaming `adb logcat -s devourer:D` over adb-over-Wi-Fi** (`out/qtx_uplink.log`: "wrote out/qtx_uplink.txt (6244 TX frames in 400 s)", the output of `quest_tx_log.sh:13`) | **`ab_detached.sh`: logcat written to a file on the Quest, pulled afterwards** — no traffic during the run (`link-envelope.md:141`) | [PROVEN] |
| Log volume per uplink frame | 5 devourer lines, **548 B** per TX frame (measured on T2's raw file, `out/qtx_wifi.raw.txt`: 2 830 336 B / 5165 frames), streamed live: ~24 small bursts/s ≈ 13 KB/s on the Quest's internal Wi-Fi (Zeul36, 5180 MHz) plus the TCP ACKs back | the same lines, but into a local file | [PROVEN bytes; INFERRED air traffic] |

The streaming capture makes internal-Wi-Fi traffic **proportional to the RTL's uplink frames**: about 24 bursts/s in
ON steps, about 0.4/s in OFF steps. That matches the T4 signature "loss runs/s ≈ TX frames/s" (24.6 vs 24.5, 26.7 vs
23.9) just as well as RTL half-duplex blanking does [INFERRED].

## 3. Hypotheses

| # | Hypothesis | Fits T4 ON ≫ OFF | Fits T2 ON ≈ T4 OFF | Tag |
|---|---|---|---|---|
| **H1** | **Capture artefact.** The streamed logcat puts one internal-Wi-Fi transmission (plus ACKs) right after each RTL uplink frame. The co-located internal radio desenses the RTL receiver, or the adb/Wi-Fi interrupts starve the devourer RX thread, and 1–4 video packets are lost | yes (traffic ∝ uplink frames) | yes (no streaming in T2) | [SPECULATION, strongest fit] |
| H2 | RTL half-duplex blanking by the uplink frames themselves | yes | **no**, unless the blanking needs another factor present only in T4 | [SPECULATION, weakened by T2] |
| H3 | Something tied to a fresh launch with the pref true that lasts > 30 s and ends before ~195 s (e.g. an RTL state after `InitWrite` + `SetTxPower`) | yes | yes | [SPECULATION; the timeline shows no decay from 5 to 25 s, which argues against] |
| H4 | The RTL TX power call changes the receiver | would show in T2 too (same call) | no | [INFERRED: excluded as the sole cause] |
| H5 | IDR / fec_change reports acting on the air | no effect: the air's alink was off in both | — | [INFERRED: excluded] |
| H6 | The air or the channel changed between T4 and T2 | — | possible in principle; same MCS/bitrate/RSSI, similar inj/s | [INFERRED: unlikely; excluded by an in-run ABBA] |

H1 would also confound the earlier finding that the uplink costs pre-FEC loss at MCS2 (2026-09-27, `m2b2f48`, 17 dBm,
51 TX/s → about 28 KB/s of streamed log). That run also used `quest_tx_log.sh` ([link-envelope.md](link-envelope.md)
§ Phase 3b, "Adaptive link on/off") [PROVEN: same capture script].

## 4. The test that separates them (needs a slot; air at `m7b25f46`, 17 dBm, alink off, as in T4)

All logging is **detached** (written on the Quest, pulled after), including `PKT_LOST`: a streamed `PKT_LOST` capture
would itself put Wi-Fi traffic next to each loss. Capture per run:
`logcat -T 1 -v epoch -s wfb-ng:I devourer:D -f <file on the Quest>` (as `ab_detached.sh` does, with `wfb-ng:I`
added) + the lean trace + `link_audit.py`.

**U1: capture streaming vs detached, uplink ON throughout, app never relaunched (~10 min).** ABBA×2, 120 s steps:
A = `quest_tx_log.sh` streaming running, B = no streaming (detached logcat only). One launch before the first step.
- **H1:** A steps lose like T4 ON (post ~2 %, runs ≈ TX/s), B steps like T2 (post ~0.8 %). In A, the loss gaps
  follow `TX DESC` by the adb/Wi-Fi delay (a few to tens of ms); in B there is no excess coincidence.
- **H2:** A ≈ B, both lossy, with gaps within ≤ 2 ms after `TX DESC` in both.
- **H3 / H6:** A ≈ B ≈ T2 (clean): the T4 effect needs relaunches; go to U2.

**U2: uplink ON vs OFF, detached capture only, ≥ 120 s steps, ABBA×2 (~12 min).** `pref_ab.sh` with a detached
capture and `--guard-s 20` (relaunch per step is unavoidable: the pref is read at start-up).
- **H1 confirmed by U1:** ON ≈ OFF. The uplink is not part of the floor at MCS7/25 Mbit/s, and nothing on the uplink
  side needs changing.
- **H2 / H3:** ON > OFF again, with gaps near `TX DESC` (H2) or only in the first N seconds after each launch (H3,
  read from 10 s bins of the timeline).

`link_audit.py --logcat <file> --window-ms 2`, then again with a wider window (20–50 ms), prints the fraction of
post-FEC gaps within the window after a `TX DESC` (`uplink_coincidence`) and the periodicity (4 Hz report grid). Those
two numbers, per state, are the per-frame evidence.

## 5. If the uplink turns out to matter (only then)

Frame budget options, with their cost to alink [INFERRED from §1, not measured]:
- Uplink FEC 1/3 → 1/1: 12 → 4 periodic frames/s. A lost report is repeated 250 ms later, and the `idr_code` persists
  until the next loss (`SignalQualityCalculator.cpp:156-158`), so a lost IDR request is re-sent with the next report.
  To go stale at the air's 1500 ms threshold, 6 consecutive reports would have to be lost.
- Fewer news reports: at most one per ~100 ms, or none when the air's alink is stopped. They are ~9 of the ~24 frames/s
  under loss.
- The rate 4 → 2/s is cheaper still, but leaves only 3 reports inside the 1500 ms stale window.
- Timing the TX into the downlink's gaps needs the air's frame boundaries and a USB-to-air latency the Quest cannot
  hold to < 1 ms. It is the most expensive option and the last one to try [SPECULATION].
