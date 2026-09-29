# Unrecoverable FEC blocks on the Quest: PPXR_FECBLK (2026-09-29)

Why: the residual loss comes in outages of ~4 ms (p50), 1–4 packets, ~1/s, not locked to beacons, and at ~2950 pkt/s
a FEC 4/8 block lasts ~2.7 ms, so one outage takes out a whole block (pixelpilot-xr-25, `f31d38f`,
`docs/xr/data/loss-bursts-2026-09-29-hdsweep.txt`). The question is what an outage is: the air not transmitting, the
Quest's RX not detecting, or frames arriving with a bad FCS. A second probe, PPXR_RTPHOLE (§6), splits every hole in
the delivered RTP sequence into packets that never entered the air's wfb_tx and packets lost on the radio.
**Status: both built and host-tested; not yet run on the headset.**

Keywords: FEC block, unrecoverable, outage, loss burst, bad FCS, keep_corrupted, fragment bitmap, wfb-ng Aggregator,
PPXR_FECBLK, PPXR_RTPHOLE, PPXR_RELEASE, -Z, marker flush, frame completion delay, waited for next frame, FEC
recovery release, FRAME_FLUSH, zflush.py, RTP hole, RTP sequence gap, wfb slot, PKT_LOST, pre-FEC vs post-FEC, air input drop, wfb_tx
UDP overflow, circular time shift control, bloc FEC pierdut, întrerupere, gaură RTP.

## 1. What is logged

One logcat line, tag `PPXR_FECBLK`, per video FEC block that wfb-ng gave up on (at most 10/s; the next second's first
line carries `suppressed=N`):

`t_mono_ms=<Quest CLOCK_MONOTONIC> blk=<block_idx> k= n= got=<bitmap, fragment 0..n-1> span_us=<first→last received
fragment> gap_max_us=<longest gap between received frames (any channel) while the block was pending> frags=<idx:dt_us:
rssiA:rssiB,...> fcs=<bad-FCS frames from 10 ms before the block to its flush, or - > reason=flush|ring [next=<block
that completed and flushed it>]`

- RSSI is devourer's raw value (dBm = raw − 110, `devourer/src/LinkHealth.cpp:8`); the parser converts it.
- `fcs` needs devourer's `keep_corrupted` diagnostic on. Otherwise bad-FCS frames are dropped in the chip/driver and the
  field is `-` (unknown, not zero). With it on, `RxDiag` also sums bad FCS per stats window (~300 ms) into the
  `ppxr_rx_*` trace counters, which gives the per-window bad-FCS rate.

## 2. How a block is judged lost

`app/wfbngrtl8812/src/main/cpp/FecBlockProbe.h` mirrors wfb-ng's `Aggregator::process_packet` (`wfb-ng/src/rx.cpp`):
a block is recovered once it holds k distinct fragments; at that moment every older block still short of k is flushed
and its missing data counted lost (`reason=flush`, rx.cpp lines 203–218); a block that falls out of the 40-block ring
is dropped (`reason=ring`, `RX_RING_SIZE`, rx.hpp:79). It is fed on the RX thread with the fragments the video
aggregator **accepted** (decrypted: its data counter moved), whose block/fragment come from the clear
`data_nonce = (block_idx << 8) + fragment_idx` (wifibroadcast.hpp:243).

k/n come from the session the aggregator accepts: this port's `IPC_MSG` (`wfb_log.h`) passes wfb-ng's
`SESSION <epoch>:<type>:<k>:<n>` message to `WfbSessionTap.h`. That tap is per thread; the link clears it before the
video aggregator's call and reads it after, so the wfb-ng submodule is unchanged.

## 3. Reading it

`python3 scripts/quest-latch/fec_blocks.py <detached logcat> [--tsv blocks.tsv]`
([fec_blocks.py](../../scripts/quest-latch/fec_blocks.py), test `test_fec_blocks.py`). Per block: missing count,
missing data fragments, where the holes sit (head / middle / tail, or scattered), mean RSSI A/B dBm. The summary gives
blocks per minute, outages (`gap_max_us` ≥ 2 ms), blocks with bad FCS, hole positions, reasons, gap p50/p95 and mean RSSI.

**Joining the air's injection drops** (the air's `wfb_tx` drops packets at injection itself: non-zero in 27 of ~200 s,
1–148 pkt/s, per the coordinator's FEC-span run): `fec_blocks.py <capture> --air-log <air /tmp/wfbtx.log>
--quest-minus-pc-ms Q --air-minus-pc-ms A` marks each block `air_drop=Y/N/?`. It uses the `dropped` field (6th) of the
air's per-second `PKT` line (wfb-ng `tx.cpp:729-730`; per-interval counters, so a line covers (previous ts, ts]) and
the interval containing the block's air time ([air_drops.py](../../scripts/quest-latch/air_drops.py), shared with
rtp_holes.py). The summary gets `air_drop_share` = Y / (Y + N). Clocks: the capture's
logcat epoch (Quest wall) − Q (`quest_minus_pc_ms`, ab_detached's meta) = PC wall; + A = the air's `get_time_ms`
(CLOCK_MONOTONIC: [PROVEN for this repo's wfb-ng copy: `wfb-ng/src/wifibroadcast.cpp:50-56`; INFERRED for the air's
wfb_tx, the same upstream function]). So A is **not** the wall-clock offset: A = air monotonic ms − PC epoch ms =
(air `/proc/uptime` × 1000 − air `date +%s%3N`, read together on the air) − (PC − air wall offset). The air runs ntpd,
so the last term is small, ≈ +50…90 ms (slot_watch's `AIR_CLOCK pc_minus_air_s`, [slot-watch.md](slot-watch.md)). The air log
has 1 s resolution, so Y means "the air dropped packets in that second", not that it dropped this block's fragments.

How to read the classes [INFERRED from the definitions; nothing measured yet]:
- `gap_max_us` ≥ 2 ms with `fcs=0` (keep_corrupted on): **no frame at all** reached the Quest's RX: either the air did
  not send (compare with the air's per-second TX log) or the RX did not detect them.
- `fcs` > 0 around the block: frames arrived **corrupted** (RF errors: interference, multipath, a fade).
- `where=scattered` with small gaps: individual losses, not an outage.

## 4. Tests

Host gtests `FecBlockProbe_test.cpp` (11: the session tap; complete vs flushed blocks; bitmap, span, outage gap; FCS
window; duplicates; parity counting towards k; ring overflow; a new FEC/session; rate limit). Mutation check: raising
the line cap failed 1 test, and requiring > k instead of ≥ k failed 4. Python `test_fec_blocks.py` (6) and
`test_air_drops.py` (7: intervals, time mapping, the circular-shift control). The per-second line budget is shared
with PPXR_RTPHOLE (`LineRateLimiter.h`); the FECBLK suite stayed green after the refactor.

## 5. Headset check (done 2026-09-29, cause run)

First run on the headset (APK cd960b31, `keep_corrupted` on, 192 KB vs 1 MB air input buffer as positive/negative control): pre-FEC holes only at 192 KB and 67–83 % in the air's drop intervals vs 2 % for rotations; at 1 MB ~20–24 unrecoverable blocks/min remain, 68 % with bad-FCS frames around them at −26 dBm, only 7 of 114 a gap with no frame at all. Results: [link-envelope.md, cause run](link-envelope.md#cause-run-2026-09-29-04460451-with-the-air-input-fixed-1-mb-what-remains-is-the-radio-mostly-frames-that-arrive-corrupted). The original instructions:

Install the build; run a slot with `keep_corrupted` on (so `fcs` is known) and a detached capture
(`ab_detached.sh`), at the geometry that shows the ~1/s outages; `fec_blocks.py` on the capture, next to the air's TX
log for the same window.

## 6. RTP holes: before or after FEC (PPXR_RTPHOLE)

Why: the air's input drops are proven: wfb_tx's UDP receive buffer overflows on the LED-flash frames (192 KB drops,
512 KB is clean; the coordinator's rmem A/B, `7eec4e0`). Those packets never enter FEC, so PPXR_FECBLK cannot see them.
The question is whether the frequent 1–4-packet outages are that or a separate loss after wfb_tx (pixelpilot-xr-40's
proposal, OpenIPC `O2-soc-usb-stalls-probe.md`).

**What is logged.** One logcat line, tag `PPXR_RTPHOLE`, per hole in the RTP sequence the video aggregator delivers
(at most 10/s, `suppressed=N` as FECBLK):

`t_mono_ms=<Quest CLOCK_MONOTONIC of the frame that released the packet> rtp_prev= rtp_next= gap=<missing RTP packets>
slots_lost=<wfb data slots lost between the two packets> session=0|1`

**How.** wfb-ng's `Aggregator::send_packet` (`wfb-ng/src/rx.cpp` 835–861) hands every payload, FEC-recovered ones
included, to the virtual `send_to_socket` in wfb slot order (`packet_seq = block_idx·k + fragment_idx`). When that slot
number jumps, it first logs `PKT_LOST\t<slots>` through `ANDROID_IPC_MSG` [PROVEN: rx.cpp:841-846]. This port:
- routes `ANDROID_IPC_MSG` through `wfb_log.h` to `WfbPktLostTap.h`, a per-thread count, like the SESSION tap;
- uses `VideoTapAggregator.h`, wfb-ng's `AggregatorUDPv4` with `send_to_socket` overridden for the video channel only.
  It takes the tap's count, then passes the payload's RTP sequence number and SSRC to `RtpHoleProbe.h`, then calls the
  base.

The wfb-ng submodule is unchanged. The cost per delivered packet is a 12-byte header read and a few compares; a line
is written only for a hole.

The slot loss comes from `PKT_LOST`, not from the aggregator's counters or its slot number. `count_p_lost` is cleared by
`StatsWindow` every stats window, and `seq` is private. `PKT_LOST` also leaves out FEC-only padding slots (they advance
`packet_seq` too), so counting those as "gaps between slot numbers" would be wrong.

**Classes.** Defined in one place, [rtp_holes.py](../../scripts/quest-latch/rtp_holes.py), from the raw fields
[INFERRED from the mechanism above; nothing measured yet]:

| class | condition | meaning |
|---|---|---|
| `pre_fec` | slots_lost = 0 | the neighbours sat in contiguous wfb slots: the packets never entered wfb_tx (air input loss) |
| `post_fec` | slots_lost ≥ gap | lost on the radio after FEC (more slots than packets = lost padding slots) |
| `mixed` | 0 < slots_lost < gap | at least gap − slots_lost never entered wfb_tx |
| `unknown` | session = 1 | a new wfb session restarted wfb-ng's slot counter between the two packets |

Packets are split the same way: pre-FEC = gap − min(slots_lost, gap), a lower bound; post-FEC = min(slots_lost, gap),
an upper bound. The probe ignores a non-RTP payload on the video port and resyncs on a new SSRC, a duplicate, a
backward jump or a jump of more than 1000. A lost slot of an ignored payload counts toward the next hole.

**Reading it.** `python3 scripts/quest-latch/rtp_holes.py <detached capture> [--tsv holes.tsv] [--air-log <air
/tmp/wfbtx.log> --quest-minus-pc-ms Q --air-minus-pc-ms A]`. It gives holes and missing packets per class,
`pre_fec_share` (of the packets with a known place) and gap histograms. With the air log, each class gets its share of
holes in the air's `dropped > 0` seconds, against every circular rotation of the air's per-second drop series
(`air_drops.shift_control`): the mean, p95 and max, and `p_value` = (1 + rotations ≥ real) / intervals. That is the
**time-shift control**. The slot class itself is exact per hole; the rotation checks the independent claim that
pre-FEC holes are the air's measured drops. If the model holds, the pre-FEC share should beat the rotations and the
post-FEC share should sit at their mean.

**Tests.**
- Host gtests `RtpHoleProbe_test.cpp` (12). The 10 probe tests cover: a contiguous stream; a hole with 0 or n lost
  slots; slot loss not carried past a delivery; wrap at 65536; duplicate / backward / big-jump resync; a new SSRC; a
  non-RTP payload; a hole across a new session; the rate limit. The other two cover `LineRateLimiter` and
  `WfbPktLostTap`.
- Python `test_rtp_holes.py` (6) and `test_air_drops.py` (7).
- Mutation checks:
  - not resetting the slot loss after a delivery failed exactly `SlotsLostWithoutAnRtpHoleAreNotCarriedToTheNextHole`;
  - classifying slots_lost ≤ 1 as pre-FEC failed 4 Python tests.

**Headset check (to do).** Same slot as §5: a detached capture (ab_detached.sh has the tag) next to the air's
`/tmp/wfbtx.log`, ideally with the LED rig flashing at a 192 KB wfb_tx buffer (known air drops, a positive control)
and at 512 KB (none).

## 7. Frame release timing for -Z (PPXR_RELEASE, zflush.py)

Why: pixelpilot-xr-40's wfb_tx patch `-Z` (wfb-ng branch o117-marker-flush `c8a5416`, OpenIPC
`repos/tasks/loss-outages-2026-09-29/o3-patch/`) closes the open FEC block at each RTP marker packet (fillers + parity),
so a frame's tail no longer waits for the next frame's packets. The planned slot compares 8/16 +Z, 8/16 −Z and
12/24 −Z at 1080p90 16 Mbit with the LED rig. So far 12/24 had 3–5× less loss than 4/8 but +2.6 ms mean G2G and
~+20 ms p95 (§6 run, `3ee9645`).

**When a frame waits** [PROVEN: wfb-ng `src/rx.cpp` 748–833]. Without loss, the Aggregator hands each data fragment
out the moment it arrives (the front-block loop). A payload waits only behind a gap in its block. Everything queued
behind the gap then comes out in one `process_packet` call, when the block is recovered (k fragments, which can need
the next frame's data, or parity the air sends only after that data fills the block) or when it is flushed. So a frame
whose tail sat in such a block has its marker packet released **in the same call as the next frame's packets**. With
-Z, the block closes with fillers and parity right after the marker, and the call holds the frame's own packets only.

**What is logged.** `ReleaseProbe.h`, driven by `VideoTapAggregator.h` (`beginCall` before and `endCall` after each
video `process_packet`, every delivered payload in between). One logcat line, tag `PPXR_RELEASE`, per call that is not
a plain on-arrival delivery (`rec > 0` or more than one payload); at most 100/s, `suppressed=N` as the others:

`t_mono_ms=<the frame that triggered the call> rec=<fragments recovered> n=<payloads> frames=<rtp ts>:<first seq>-<last
seq>:<marker 0|1>,... [more=N]`

`rec` = `count_p_fec_recovered` after minus before the call. The counter is reset only by `StatsWindow`, under the same
`agg_mutex`, so never inside a call [PROVEN: WfbngLink.cpp:535-536, the stats thread takes `agg_mutex` before `take_window`]. The
RTP header parse (`RtpHeader.h`) is shared with RtpHoleProbe.

**Frame classes.** Defined in one place, [zflush.py](../../scripts/quest-latch/zflush.py):
- `recovered`: released in a call with rec > 0.
- `held`: released late without recovery (queued behind a gap, then flushed).
- `clean`: neither.
- `waited_next` (a flag on top of the class): the frame's marker packet shares a call with a later frame's packets.
  wfb-ng releases in slot order, so position in the call is frame order.

**Reading it.** `python3 scripts/quest-latch/zflush.py trace.pftrace steps.txt capture.txt --air-offset-s S --baseline
LABEL [--guard-s 4] [--air-log wfbtx.log --air-mono-minus-epoch-ms M] [--by-step]`. Per state (or per step):
- frames;
- per class, `complete` (first → last packet, ms) and `capture→last` (ms above the baseline state's drift line, as
  [big_frames.py](../../scripts/quest-latch/big_frames.py)), each as n / mean / p95 / p99;
- the waited-for-next-frame share of all frames and of the recovered ones.

The frames come from the trace's `ppxr_rtp_seq` / `ppxr_rtp_ts` counters (`ab_segments.load_trace`) and are joined to
the log by 32-bit RTP timestamp. With `--air-log`, the air's `FRAME_FLUSH frame_ends:blocks_closed:fillers` per
interval (wfb-ng o117 `tx.cpp:827`, counters reset per interval) is summed per state. Its timestamps are the air's
CLOCK_MONOTONIC ms; M = air uptime ms − air epoch ms, read together on the air. Residual loss per state comes from the
existing tools (`ab_segments.py` loss per step, `rtp_holes.py`).

**Limits** [INFERRED from the mechanism]:
- A late release of a single payload without recovery (a flush with one queued packet) is not logged. That frame lost
  data anyway, so it shows in PPXR_RTPHOLE.
- A block closed by the air's `fec_timeout` fillers releases the frame on its own: `waited_next` = 0, but the wait
  still shows in `complete`.
- A state with `suppressed` > 0 undercounts recovered and held frames.
- The join needs one RTP timestamp base across the run, the same as big_frames.py (no waybeam restart).

**Tests.**
- Host gtests `ReleaseProbe_test.cpp` (7): a plain delivery writes nothing; a recovery lists frames, seq ranges and
  markers; a held release; non-RTP payloads; the frame cap; a counter that went backwards; the rate limit.
- Python `test_zflush.py` (8), and `test_air_drops.py` now also covers `parse_intervals`.
- Mutation checks:
  - logging single-payload calls failed 2 gtests;
  - marking every marker group as waited_next failed 3 Python tests.

**Headset check (to do).** Install a build with PPXR_RELEASE. In the -Z slot, record a Perfetto trace (as for
big_frames) plus a detached capture (ab_detached.sh has the tag) and the air's step log and `/tmp/wfbtx.log`.

## 8. RX: the next block waits after the front block completes (wfb-ng Aggregator fix, not yet landed)

Found by openipc-4b (O121, `repos/tasks/air-latency-30pct-2026-09-30/02-IMPLEMENTATION-PLAN.md` N3, §4.3); the same code
is in upstream wfb-ng HEAD and on the GS.

**The bug** [PROVEN: `wfb-ng/src/rx.cpp` 748–767 and 820–833, reproduced below]. When `rx_ring_front` advances (the
front block completed in order, or was recovered through FEC), the new front may already hold fragments that arrived
earlier: reordering, or the older block's parity arriving after the newer block's first data. Those fragments are not
released until one more fragment of the new front arrives, up to a frame later. Stock hits it on reordering or lost
parity. The air's planned `wfb_tx -Y` (parity after the frame) would hit it on any loss in a frame spanning 2 blocks.

**The test** (`tests/RxDrain_test.cpp`, 5 gtests, with `tests/rx_replay.*`). Real encrypted k=4/n=8 packets from our
`Transmitter` (TxFrame.cpp) go into wfb-ng's real `Aggregator` (rx.cpp built as in the app, `__WFB_RX_SHARED_LIBRARY__`
+ the `wfb_log.h` preinclude; needs libpcap-dev in WSL) in chosen orders:
- R1, the FEC path. Stock: the recovery call releases `{P2, P3}`, and P4 comes out only with the next fragment, as
  `{P4, P5}`.
- R2, the in-order path. Stock: the late fragment releases `{P3}`, and P4 and P5 wait for block 1's fragment 2.
- A gap in the new front stops the release, and FEC recovers the rest later.
- Waiting fragments are released, and the block carries on normally.
- A sanity test: in-order delivery.

A block holding k fragments takes the FEC path and flushes the older blocks (rx.cpp 771–790), so a block can wait
behind the front with at most k − 1 fragments. The fix's "retire a complete new front" branch is defensive.

**The fix** (4b's `c1/rx-drain-quest.diff`, md5 `c8e0d705`): `Aggregator::drain_front()` after both front advances.
It releases the new front's in-order prefix, retires it if it is complete, and stops at a gap.

**Verdict:**
- Stock: 4 of 5 red for the intended reason (the assertions above).
- Patched: 5/5, and the whole wfb host suite 70/70.
- Mutant: removing only the FEC-path `drain_front()` fails exactly R1.

**Reading a Quest A/B of this fix** [INFERRED from zflush.py's class definition and the rx.cpp release paths]: zflush's `recovered` = released in a call with rec > 0. With the drain, the next block's waiting frames join that call (recovered); on stock they come out a call later (held). Class membership moves with the lever, so compare all frames' p95/p99, or recovered ∪ held; the held count per state is the fix's direct signature. A/B APK 7f8b34c1 = 81643b5 + the diff, paired with c8986061.

**Gate: no `wfb_tx -Y` toward the Quest before the drain is in the installed APK.** Without it, a loss in a frame spanning 2 blocks keeps that frame's tail until the next frame (openipc-4b's T3, red without the drain) [PROVEN on the GS copy by 4b, wfb-ng o121-parity-defer `8e61b2b`; the same R1/R2 red/green and the same mutant result as ours].

**Not landed yet.** The wfb-ng submodule tracks upstream `svpcom/wfb-ng`, so the fix needs a home: a
`tmariovlad/wfb-ng` fork like devourer's (a GitHub fork plus a push, the user's decision) or a build-time patch. Until
then the test lives on the `rx-drain` branch, not in xr-native, where it would be red against the stock submodule.
