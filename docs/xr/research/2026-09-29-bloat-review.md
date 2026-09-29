# Independent review: is the +210–250 ms at 1 MB over capacity a bug? (2026-09-29)

Reviewer: independent sub-agent, offline only (no ssh / adb / DPS / COM). Scope: the bufferbloat gate of
2026-09-29 22:39–22:50 (MCS4, 1080p90 16 Mbit/s, FEC 4/8, 192K / 1M / 192K / 1M, 120 s per step).
Inputs: air log `docs/xr/data/air-bloat-gate-2026-09-29.txt`, Quest data `docs/xr/data/*-bloat.txt`, rig raw data
`c:/Users/vlad_/Documents/Arduino/latency_test/tasks/saturation-gate-2026-09-29/run3/`, the air script
`rmem_sat.sh` (scratchpad), wfb-ng `993120d` (`git show 993120d:src/tx.cpp`), driver source
`repos/wifi-drivers/libc0607-rtl88x2eu` (identical in `svpcom-rtl8812eu` for the functions cited).

## Verdict

**The 1M − 192K difference is not a bug. It is the arithmetic of a full UDP receive queue, and it matches to
within ~5 %.** The "20× for 5.3×" nonlinearity is an artefact: the Quest's 12 ms is measured above the 5th
percentile of the 192K state itself, not above zero.

**The review did find what the conclusion missed.** Over capacity, a **second standing queue of ~60–70 ms** sits
**downstream of wfb_tx**, in the driver/chip TX path. It exists at 192K too and does not depend on rmem. The planned
`wfb_tx -A` age guard cannot see it. The TX path also **drops ~13–15 % of the FEC-coded packets silently** after
a busy-wait, while wfb_tx counts them as injected. There are also three bookkeeping defects (rig step labels,
rmem_max left at 196608 after the revert, big-frame survivorship).

## 1. The arithmetic: 180 / 430 ms reproduced

### 1a. How the buffer is applied [PROVEN]
- `rmem_sat.sh` `setrmem()` writes `R` to **both** `/proc/sys/net/core/rmem_max` and `rmem_default`, then
  `vrestart` kills and relaunches only the video wfb_tx (`-p 0 -u 5600`). There is no `-R`, so wfb_tx sets no
  `SO_RCVBUF` [PROVEN: `wifibroadcast.cpp:85-90` at 993120d: `setsockopt(SO_RCVBUF)` only `if (rcv_buf_size > 0)`;
  `tx.cpp` `rcv_buf = 0` default]. The new socket's `sk_rcvbuf` = `rmem_default` **as is**. The kernel's
  doubling applies only to `setsockopt(SO_RCVBUF)`.
- Log confirms: `rmem=196608/196608` and `rmem=1048576/1048576` on the SET/STEP lines [PROVEN: air log lines 12-19].
- The deployed HD path (`wfb_tx -R 524288`, HANDOFF line 30) gives `min(524288, rmem_max) × 2` = 1 MB **only if
  rmem_max ≥ 524288**. With that, the gate tested the same effective buffer as the deployed preset. See §4c for
  the case where rmem_max is smaller.

### 1b. How many packets fit [INFERRED from kernel 4.9 skb sizing]
- Air kernel 4.9.84 armv7 [PROVEN: `openipc-low-latency…/docs/superpowers/plans/2026-06-28-link-mode-switch-slice1-2.md:9`].
  waybeam `maxPayloadSize` 1400 [PROVEN: `repos/openipc-extra/waybeam_venc/config/waybeam.default.json:59`].
  Measured mean is 16 Mbit/s ÷ 89.5 fps ÷ 16.05 pkt/frame ≈ 1392 B/packet [INFERRED: `latency-2026-09-29-bloat.txt` pkt/f].
- A loopback UDP skb for 1400 B: 1400 + 8 + 20 + 16 (LL reserve) + 15 = 1459 → aligned 1472, + shinfo (192)
  → kmalloc-2048. truesize = 2048 − 192 + 192 (sk_buff) + 192 = **~2240 B** (1.6× the payload). The 4.9
  `__sock_queue_rcv_skb` admits while `sk_rmem_alloc < sk_rcvbuf`.
  - 192K: 196608 / 2240 → **88 packets** (~123 KB of video).
  - 1M: 1048576 / 2240 → **469 packets** (~653 KB of video).
  - [INFERRED; exact truesize ±~5 %, confirm with probe P1]

### 1c. Drain rate [PROVEN: air log + Quest]
- inj = 341880 / 345633 / 341911 / 345494 per step. The PKT window is ≈ 117–118 s (N0 at E, STEP after `sleep 117`),
  and FEC 4/8 means inj = 2 × data. So the data drain ≈ **1460 ± 20 pkt/s** (1461 / 1477 / 1461 / 1476).
- Cross-check: the Quest audit's `rx` over the 110 s guarded window is 1463 / 1491 / 1461 / 1451 pkt/s
  [PROVEN: `audit-2026-09-29-bloat.txt`].

### 1d. Predicted vs measured

| state | socket queue when full | predicted socket delay | rig first light, median (relabeled, §3) | rig − clean 46 | residual after the socket |
|---|---|---|---|---|---|
| clean MCS7 | 0 | 0 | 46.0 ms | 0 | 0 |
| 192K MCS4 | 88 pkts | **60 ms** | **179.3 / 180.0 ms** | 134 ms | **~74 ms** |
| 1M MCS4 | 469 pkts | **321 ms** | **430.3 / 433.0 ms** | 386 ms | **~65 ms** |

- **Δ(1M − 192K) predicted ≈ 261 ms, measured (rig medians) 252 ms** (−3.5 %).
- Rig means Δ ≈ (399.4 + 418.0)/2 − (176.9 + 178.4)/2 = **231 ms**; **Quest Δlast (mean) = 223.9 ms**
  [PROVEN: `latency-2026-09-29-bloat.txt` per state].
  - Means sit below the plateau median because the 1M queue is not always full.
  - drop_secs are 55 / 74 of 120 at 1M. Plateau minima of 207 / 301 / 345 ms appear between overflow episodes
    [PROVEN: `per_flash.csv` ids 54, 57, 59, 105, 111].
  - The Quest bins dip too (123 ms in step 1, bin 6) [PROVEN: `latency-bins-2026-09-29-bloat.txt`].
- The Quest and the rig agree once both are taken as differences. The Quest cannot give an absolute value: see §2.

## 2. Red flag 1 (nonlinearity): an artefact of the baseline [PROVEN: `scripts/quest-latch/ab_segments.py:72-84, 93-98`]
- `fit_drift` fits a line through the **5th-percentile lower envelope** (per 1 s window) of the **192K** frames.
  Every Quest number is "ms above that line".
- The 192K standing queue (~60 ms socket + ~70 ms downstream) is therefore inside the intercept. The 12.5 ms is only
  the 192K state's mean minus its own p5.
- "12 → 224" is a ratio of a residual to a difference, so it has no meaning.
- In absolute terms (rig) the added delay over clean goes 134 → 386 ms (2.9×). That is exactly **a linear term
  (60 → 321 ms, 5.3×) plus a constant ~65–74 ms**.
- The Quest cannot give absolute capture→arrival here: the fit absorbs the clock offset (±0.1 s uncertainty).

## 3. Red flag 4 ("second 1M starts full") and a rig labeling defect

### 3a. The steps start late, cumulatively [PROVEN: script + air log]
- The loop waits for `T = START + k·120`. After `setrmem` + `vrestart` (0.5 + 1.5 s), it records E, sleeps
  `DWELL − 3` = 117 s, then logs (wget + control-port calls + awk).
- E + 117 + logging overruns the next T, so the next step starts immediately and later each time. The SET epochs are
  710902 / 711024 / 711147 / 711269 against nominal T = 710900 / 711020 / 711140 / 711260. That is +2, +4, +7 and
  **+9 s**; the relaunch happens ~2 s before each E.
- The Quest `steps-2026-09-29-bloat.txt` uses the SET epochs, which is correct.
- **The rig README uses the nominal T** ("192K @710900 · 1M @711020 · 192K @711140 · 1M @711260"). That is wrong by
  up to 9 s.

### 3b. The rig flashes, relabeled with the air SET epochs [PROVEN: my re-run `scratchpad/relabel.py` on `per_flash.csv`]
- The relaunch is taken as E − 2 s. Results are the same for PC−air = +0.05 s and +0.8 s.
- **id 69 (436 ms)** was labeled 192K and explained as "the 1M queue draining". It lands 121 s into the **1M** step,
  before that step's kill.
  - A relaunch destroys the socket, so a queue cannot drain across it. The "draining" explanation is a label artefact.
- **id 91 (176 ms)** was labeled 1M. It is still in the **192K** step.
- **id 115 (434 ms, "after")** is the last flash of 1M#2 (the revert began ~711390).
- **id 46 (48 ms)** falls ~0.6 s after the 1M relaunch (at +0.05 s offset). **A fresh MCS4 path with every queue
  empty gives 48 ms, the same as clean MCS7.** So MCS4 airtime alone adds ~nothing; all the excess is queue that
  rebuilds [INFERRED: at +0.8 s the flash falls just before the kill, where 48 ms would not be possible with a full
  192K path].
- Corrected per-step rig numbers: 192K#1 median 179.3 / mean 176.9 (n 24); 1M#1 430.3 / 399.4 (n 21); 192K#2
  **180.0 / 178.4** (n 21, 1657 ms outlier excluded; the README's mean 261.1 and "first third 214" were inflated by
  id 69); 1M#2 433.0 / 418.0 (n 23).

### 3c. Fill times match a fresh socket [PROVEN: rig; INFERRED: rate]
- 1M#1: 254 ms at t+8 s, 363 at t+12, 431 at t+18 (full in ~15–18 s). 1M#2: **308 ms at t+3.9 s, 438 at t+8.8 s**.
  192K: 151 ms at t+3.3, 179 at t+3.5.
- Fill time ≈ capacity / excess rate. Excess ≈ (drops + queue) / 117 s:
  - 1M#1: (5053 + 469)/117 = 47/s → ~10 s.
  - 1M#2: (6497 + 469)/117 = 60/s → ~8 s.
  - 192K: 88 / ~70 → ~1.3 s.
- The Quest's first bin starts at SET + 5 s ≈ **7 s after the relaunch**, so in step 3 it lands on an almost-full
  queue. **"Starts already full" is a faster fill plus a late first bin, not a queue that survived the relaunch.**
- Why step 3 was more overloaded: most likely content and scene (+ rig cadence; each flash adds ~38 extra packets,
  ~8 pkt/s at one flash per ~4.7 s) [SPECULATION].

## 4. Findings the conclusion missed

### 4a. A second standing queue of ~65–74 ms downstream of wfb_tx, present at 192K too [INFERRED]
- Evidence:
  1. After subtracting the socket, the residual is 74 ms at 192K and 65 ms at 1M. It is nearly constant across a
     5.3× buffer change (§1d).
  2. The empty-queue flash id 46 = 48 ms.
  3. The Quest decode (decoded − last) is 2.5 / 1.5 ms in both states, and the frame spread is 10.4 ms in both
     [PROVEN: `latency-2026-09-29-bloat.txt`]. So the extra time is upstream of Quest packet arrival, not in the
     GS decoder or app.
- Where it can live [PROVEN code / SPECULATION sizes]:
  - wfb_tx sets `PACKET_QDISC_BYPASS` (`tx.cpp:225` at 993120d; `-Q` not passed), so there is **no qdisc**.
  - In monitor mode the driver copies each skb into a mgmt xmit frame from the ext pool and frees the skb
    immediately (`rtw_xmit.c:4904-5078`). So the sender's sndbuf never fills either.
  - The frames then wait in:
    - the driver's ext frame/buffer pool: `NR_XMIT_EXTBUFF` = 32 unless `CONFIG_RTW_MGMT_QUEUE`
      (`include/rtw_xmit.h:91-96`) → ~13 ms at the measured ~2490 pkt/s radio rate;
    - the USB bulk-out URBs;
    - the chip's TX FIFO (8822-class chips have a ~256 KB TX page buffer, i.e. ~100+ frames ≈ 40–60 ms)
      [SPECULATION on the exact 8822E size].
  - Plus the flash frame's own serialization at MCS4 (~110 coded packets ÷ 2490/s ≈ 44 ms vs faster at MCS7).
    Only part of that is new relative to clean.
- **Consequence for the `-A <ms>` design (HANDOFF line 25):** the guard measures age at wfb_tx dequeue. Over capacity
  the ~65–74 ms downstream stays. With `-A 40`, expect ≈ 46 + ≤40 + ~70 ≈ **~150 ms first light**, not ~90.
  The re-gate should read the rig in absolute terms, not only `/proc/net/udp`.

### 4b. The TX path drops ~13–15 % of the coded packets silently, and wfb_tx calls them "injected" [PROVEN code, INFERRED rate]
- `rtw_monitor_xmit_entry` → `monitor_alloc_mgtxmitframe` (`libc0607-rtl88x2eu/core/rtw_xmit.c:~4884-4898`):
  - It busy-waits 300 + 450 + 675 µs (`rtw_udelay_os`).
  - If the pool is still empty: `tx_drop++`, the skb is freed, and it **returns NETDEV_TX_OK** (`:4955-4960`).
  - `sendmsg` therefore succeeds. wfb_tx counts the packet in `count_p_injected` and never in `ant_drop`
    (`tx.cpp:341-349`, `log_latency(…, rc >= 0, …)`).
  - So **"injection never failed / ant_drop=0" does not mean the driver sent it.**
  - The driver exposes the count as `tx_dropped` (`os_intfs.c:1798`).
- The data shows exactly this:
  - Quest link rx/s = **2483.8 / 2488.9 / 2490.2 / 2483.0**: a flat ceiling in all four steps = the MCS4 air
    capacity [PROVEN: `link-2026-09-29-bloat.txt`].
  - The air hands the driver 2922–2954 coded pkt/s. Pre-FEC data loss `p_data%` is **12.8 / 14.1 / 12.8 / 14.0 %**
    [PROVEN: `audit-2026-09-29-bloat.txt`].
  - The same channel/MCS **under** capacity gives 1.5–3 % (ch165 MCS7: `audit-2026-09-29-chab.txt`,
    `-chab7.txt`; MCS4 12 Mbit: `audit-2026-09-29-hdredo.txt` 2.95 / 1.48 %).
  - **The 1M steps inject ~1 % more and lose ~1.2 pp more pre-FEC.** The extra injections land in the driver
    drop, not on air [INFERRED].
- Why it matters:
  - (i) FEC 4/8 over capacity burns ~half the drain on parity that is then dropped after coding.
  - (ii) The 1.4 ms spin per failed allocation runs in wfb_tx's `sendmsg` context. That throttle is plausibly what
    holds wfb_tx's socket drain at ~1460 data/s, i.e. what makes the socket fill [SPECULATION: needs P2].
    `sendmsg_lat_max_us` 18–23 ms in every step [PROVEN: air log] is compatible with this.
  - (iii) Any "injected" count from wfb_tx over capacity overstates what went on air.
- This does not change the 1M − 192K verdict. It is a real, unlogged loss point that the envelope work should record.

### 4c. The revert leaves `rmem_max` = 196608, which silently halves the deployed HD preset until reboot [PROVEN: script + log]
- PRE shows `rmem=196608/524288` (boot state rmem_max = 524288). `revert()` → `setrmem 196608` writes **rmem_max** =
  196608 too, and END logs `rmem=196608/196608`.
- The kernel caps `SO_RCVBUF` at rmem_max before doubling. So after any such slot, an HD preset's `wfb_tx -R 524288`
  gives 2 × 196608 = **384 KB, not 1 MB**, until a reboot (RAM only).
- Any A/B run after a gate script and before a reboot would measure the wrong HD buffer. The same pattern is likely
  in `rmem_ab.sh` [SPECULATION: not read].
- Fix in the scripts: restore rmem_max to the value read at start.

### 4d. Red flag 5 (global rmem_default hitting other sockets): no path found [INFERRED]
- Sockets created while rmem_default = 1 MB: the new video wfb_tx input socket (intended) and its control socket
  (`-C 9000`, command traffic only).
- waybeam was started in PRE, when rmem_default = 196608 [PROVEN: PRE line]. It is not restarted per step
  [PROVEN: script, `start.sh` only before the loop and in `revert`]. Its socket only sends: a loopback UDP send
  never queues at the sender (the skb is delivered in softirq or dropped at the receiver).
- The tunnel wfb_tx (`-p 32`) is not restarted. `wget` in `rb()` is TCP (tcp_rmem, not rmem_default).
- alink/vmoded were stopped. The Quest and GS are separate devices.
- No other big buffer sits in the video path.

### 4e. Red flag 6 (clocks, RTP base, analysis) [PROVEN / INFERRED]
- **Rig:** first_us is timed inside the ESP32 (µs), with no clock join. Offsets matter only for step labels (§3).
- **Quest:** the Δ between states comes from one trace, one drift line.
  - Capture time = RTP timestamp (90 kHz air capture clock, `ab_segments.py:3,53`). waybeam is not restarted
    between steps, so the RTP base is continuous; both 192K steps sit at 2.09 / 12.5 ms.
  - A PC−air error of ±0.1 s only shifts which frames fall in which step; the 5 s guard absorbs it.
  - **No clock artefact can create a 224 ms state difference.**
- IDR-on-loss off: no IDR bursts. The rig flashes are themselves the bursts (~8 extra pkt/s).
- **Caveat on `big_frames`:** at 1M#1, big frames read 188 ms vs 225 for the rest [PROVEN: `big-frames-2026-09-29-bloat.txt`].
  - When a burst hits a full socket, its tail is dropped, so the frame's "last received packet" comes earlier.
  - Survivorship bias lowers the big-frame latency in overflowing states. Do not read it as "big frames are faster"
    [INFERRED].

## 5. Probes (cheapest first; for a future live slot, none run here)

**P1: confirm the socket arithmetic.** During an MCS4 overload step at 192K and at 1M, run on the air:

```sh
while :; do awk '$2 ~ /:15E0$/ {print $5, $NF}' /proc/net/udp; usleep 100000; done
```

- `rx_queue` (hex) = `sk_rmem_alloc` bytes; the last column = drops.
- Expected: plateaus near 0x30000 at 192K and 0x100000 at 1M while dropping.
- rx_queue ÷ 2240 ≈ 88 / 469 packets; ÷ 1460 pkt/s ≈ 60 / 321 ms.
- If this holds, the 1M − 192K part is closed.

**P2: prove the silent driver drop and the downstream pool.** Read these at SET and STEP, and sample the second at 10 Hz:
- `cat /sys/class/net/wlan0/statistics/tx_dropped /sys/class/net/wlan0/statistics/tx_packets`
- `cat /proc/net/*/wlan0/tx_buf_stat` (format `MaxTxBufLen:free_xframe_ext_cnt:free_xmit_extbuf_cnt:NR_XMIT_EXTBUFF`,
  `rtw_proc.c:6130-6139`)

Expected:
- tx_dropped rises by ≈ (inj − Quest rx) ≈ 50k per 120 s step.
- free_xframe_ext_cnt ≈ 0 during overload, and ≈ NR_XMIT_EXTBUFF at MCS7 under capacity.
- NR_XMIT_EXTBUFF itself gives the pool size (32 vs 64).

**P3: size the downstream queue (extreme-value bracket).** Run the same gate with rmem at the two ends, plus 192K:
- 16384 (≈ 7 packets, ≈ 5 ms of socket): predicted rig first light ≈ 46 + 5 + ~70 ≈ **~120 ms** if §4a holds, and
  ≈ 50 ms if it does not.
- 2097152: ≈ 46 + 640 + 70 ≈ ~760 ms.
- Three points separate the linear socket term from the constant downstream term directly.

**P4 (lever, optional): shrink the driver pool.** Write N to `tx_buf_stat` (`max_tx_buf_len`, `rtw_proc.c:6147-6172`)
over capacity and watch the ~70 ms residual.
- Caution: with max_tx_buf_len > 0 the driver returns `NETDEV_TX_BUSY`. With QDISC_BYPASS, `sendmsg` then gets
  ENOBUFS, and wfb_tx counts it as a failed inject (visible, still after FEC).
- The earlier "MaxTxBufLen inert" result was below capacity, where the pool never fills [SPECULATION that it acts over capacity].

## 6. One-paragraph answer for the coordinator

No bug in the 1 MB buffer. Over capacity the socket holds 469 × ~2240 B truesize = 469 packets ≈ 321 ms at the
measured 1460 pkt/s drain, against 88 packets ≈ 60 ms at 192K. The difference, 261 ms, matches the rig's 252 ms
(medians) and, as means, the Quest's 224 vs the rig's 231. The "~12 ms at 192K" is measured above the 192K state's
own p5 line.

What we missed: at 192K the rig is already 134 ms over clean. Only ~60 ms of that is the socket. The other ~70 ms is a
standing queue in the driver/chip TX path that stays with any rmem and with the planned `-A` guard. The same path
silently drops ~13–15 % of coded packets that wfb_tx reports as injected. Measure both with `tx_dropped` +
`tx_buf_stat` + a 16 KB rmem bracket before the `-A` re-gate. Also restore `rmem_max` in the slot scripts' revert.
