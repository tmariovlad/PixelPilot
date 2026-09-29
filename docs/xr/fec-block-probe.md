# Unrecoverable FEC blocks on the Quest: PPXR_FECBLK (2026-09-29)

Why: the residual loss comes in outages of ~4 ms (p50), 1–4 packets, ~1/s, not locked to beacons, and at ~2950 pkt/s
a FEC 4/8 block lasts ~2.7 ms, so one outage takes out a whole block (pixelpilot-xr-25, `f31d38f`,
`docs/xr/data/loss-bursts-2026-09-29-hdsweep.txt`). The question is what an outage is: the air not transmitting, the
Quest's RX not detecting, or frames arriving with a bad FCS. A second probe, PPXR_RTPHOLE (§6), splits every hole in
the delivered RTP sequence into packets that never entered the air's wfb_tx and packets lost on the radio.
**Status: both built and host-tested; not yet run on the headset.**

Keywords: FEC block, unrecoverable, outage, loss burst, bad FCS, keep_corrupted, fragment bitmap, wfb-ng Aggregator,
PPXR_FECBLK, PPXR_RTPHOLE, RTP hole, RTP sequence gap, wfb slot, PKT_LOST, pre-FEC vs post-FEC, air input drop, wfb_tx
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
so the last term is small, ≈ +50…90 ms (slot_watch's `clock_offset_s`, [slot-watch.md](slot-watch.md)). The air log
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

## 5. Headset check (to do)

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
- uses `RtpHoleAggregator.h`, wfb-ng's `AggregatorUDPv4` with `send_to_socket` overridden for the video channel only.
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
