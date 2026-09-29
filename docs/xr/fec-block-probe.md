# Unrecoverable FEC blocks on the Quest: PPXR_FECBLK (2026-09-29)

Why: the residual loss comes in outages of ~4 ms (p50), 1–4 packets, ~1/s, not locked to beacons, and at ~2950 pkt/s
a FEC 4/8 block lasts ~2.7 ms, so one outage takes out a whole block (pixelpilot-xr-25, `f31d38f`,
`docs/xr/data/loss-bursts-2026-09-29-hdsweep.txt`). The question is what an outage is: the air not transmitting, the
Quest's RX not detecting, or frames arriving with a bad FCS. **Status: built and host-tested; not yet run on the
headset.**

Keywords: FEC block, unrecoverable, outage, loss burst, bad FCS, keep_corrupted, fragment bitmap, wfb-ng Aggregator,
PPXR_FECBLK, bloc FEC pierdut, întrerupere.

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

How to read the classes [INFERRED from the definitions; nothing measured yet]:
- `gap_max_us` ≥ 2 ms with `fcs=0` (keep_corrupted on): **no frame at all** reached the Quest's RX: either the air did
  not send (compare with the air's per-second TX log) or the RX did not detect them.
- `fcs` > 0 around the block: frames arrived **corrupted** (RF errors: interference, multipath, a fade).
- `where=scattered` with small gaps: individual losses, not an outage.

## 4. Tests

Host gtests `FecBlockProbe_test.cpp` (11: the session tap; complete vs flushed blocks; bitmap, span, outage gap; FCS
window; duplicates; parity counting towards k; ring overflow; a new FEC/session; rate limit). Mutation check: raising
the line cap failed 1 test, and requiring > k instead of ≥ k failed 4. Python `test_fec_blocks.py` (5).

## 5. Headset check (to do)

Install the build; run a slot with `keep_corrupted` on (so `fcs` is known) and a detached capture
(`ab_detached.sh`), at the geometry that shows the ~1/s outages; `fec_blocks.py` on the capture, next to the air's TX
log for the same window.
