# Real link: Quest 2 + RTL8812AU + OpenIPC air unit

Quest XR docs: [guide](../xr-quest.md) · [decoder levers](decoder-levers.md) · [compositor phase + phase lock](compositor-phase.md) · [real link](real-link.md) · [G2G budget](g2g-budget.md) · [troubleshooting](troubleshooting.md) · raw data in [data/](data/) · repo rules in [CLAUDE.md](../../CLAUDE.md)

> Moved verbatim from `docs/xr-quest.md` on 2026-09-26 (doc restructure); only relative links were re-rooted.

Setup (APFPV vs wfb, keys, link id) and the picture-order finding on the real OpenIPC stream. The branch-by-branch G2G budget measured on this link is in [g2g-budget.md](g2g-budget.md).

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

