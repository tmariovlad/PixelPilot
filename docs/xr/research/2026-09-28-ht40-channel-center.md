# 40 MHz on the Quest: devourer's center map and the uplink sub-channel (2026-09-28)

Context: the OpenIPC session -68 plans a 40 MHz / 2-stream test (O82b; OpenIPC repo
`repos/tasks/o82b-40mhz-2ss-2026-09-28/00-PLAN-o82b-40mhz-2ss.md`). It reported two problems in the Quest code.
This file checks both against the code and the 802.11 channel rules, and proposes a fix. **Code only, nothing changed
on a device.** Paths are relative to `app/wfbngrtl8812/src/main/cpp/`. devourer is the submodule at `bb03774`.

## 802.11 rules used (5 GHz)

40 MHz channels in 5 GHz are fixed pairs of 20 MHz channels. The lower channel of a pair is HT40+ (secondary above);
the upper one is HT40- (secondary below). The 40 MHz center is between them:

| Pair | Center 40 | Pair | Center 40 |
|---|---|---|---|
| 36 / 40 | 38 | 116 / 120 | 118 |
| 44 / 48 | 46 | 124 / 128 | 126 |
| 52 / 56 | 54 | 132 / 136 | 134 |
| 60 / 64 | 62 | 140 / 144 | 142 |
| 100 / 104 | 102 | **149 / 153** | **151** |
| 108 / 112 | 110 | **157 / 161** | **159** |
| | | 165 / 169 | 167 |

80 MHz centers: 42 (36–48), 58 (52–64), 106 (100–112), 122 (116–128), 138 (132–144), 155 (149–161), 171 (165–177).
So ch157 is HT40+ with 161 (center 159), ch153 is HT40- with 149 (center 151), and ch161 is HT40- with 157 (center 159).
In 5 GHz the pair, and so the offset, follow from the channel number alone.

## (1) The 40 MHz center map: confirmed wrong for 153 and 161

`get_40mhz_center_channel` (`devourer/src/jaguar1/RadioManagementModule.cpp:20-47`) maps
`{149, 151}, {153, 155}, {157, 159}, {161, 163}` [PROVEN: lines 40-42].
- 153 → 155 is wrong; it should be 151. 155 is the **80 MHz** center of 149–161.
- 161 → 163 is wrong; it should be 159. 163 is not a 40 MHz center at all.
- Every other 5 GHz entry is right. 165/169 → 167 is missing, and those channels fall through to "center = channel".
- The 80 MHz table in `rtw_get_center_ch` (`:216-240`) is right.
- 2.4 GHz has only `{4, 6}, {8, 6}`; any other 2.4 GHz channel at 40 MHz also falls through to center = channel.

`set_channel_bwmode` (`:257-286`) tunes the RF to this center, so at 40 MHz on 153 or 161 the Quest listens 20 MHz
off the air unit's channel [INFERRED: center = RF tune, `rtw_hal_set_chnl_bw(center_ch, …)` at `:284`]. Today the Quest
runs 157 at 20 MHz, which is not affected.

## (2) Channel offset and the 20 MHz uplink inside 40 MHz: the sub-channel is undefined

- `WfbngLink.cpp:276-280` passes `InitWrite(SelectedChannel{.Channel = ch, .ChannelOffset = 0, .ChannelWidth = 20|40})`.
  0 is `HAL_PRIME_CHNL_OFFSET_DONT_CARE` (`RadioManagementModule.h:21`) [PROVEN].
- `phy_GetSecondaryChnl_8812` (`:2240-2287`) at 40 MHz handles only UPPER/LOWER. With DONT_CARE it logs
  `SCMapping: DONOT CARE Mode Setting` and returns 0 (`UNDEFINED`) [PROVEN]. That 0 is written to `REG_DATA_SC` (0x483),
  `rRFMOD[0x3C]` and `rCCAonSec[31:28]`, and the CCK primary bit is set to "lower" (`:323-333`) [PROVEN].
- The uplink (`WfbngLink.cpp:293`, `args->bandwidth = 20`) sends 20 MHz frames with `TX_DESC.DATA_BW = 0`
  (`RtlJaguarDevice.cpp:1088-1099`). `SET_TX_DESC_DATA_SC_8812` is defined (`FrameParser.h:87`) but **never called**
  anywhere in devourer, so `DATA_SC = 0` [PROVEN: grep].
- **Which 20 MHz half the uplink lands on at 40 MHz is therefore not set by any code** [PROVEN]. What the 8812AU
  does with DATA_SC 0 and a 0x483 of 0 for a 20 MHz frame is [SPECULATION]. The possibilities are the lower half, the
  upper half, or duplicated. Only an on-air check can tell: a second monitor at 20 MHz on each half (e.g. 157 and 161).
- It matters because a receiver in 40 MHz mode normally decodes 20 MHz frames only on its **primary** 20 MHz [INFERRED:
  the same rule the SC mapping above implements]. The uplink must land on the air unit's primary.

## Proposal

**A. devourer (submodule): one pure center function, with a table test.**
- Move the center computation into a header-only `src/ChannelCenter.h` (next to `ChannelFreq.h`):
  `center_channel(channel, width, offset)` for 20 / 40 / 80 over all 5 GHz channels, plus 2.4 GHz 40 MHz, which needs
  the offset (HT40+: center = ch + 2; HT40-: center = ch − 2).
- `tests/channel_center_selftest.cpp` checks the whole 5 GHz table above. It is red on today's map (153, 161, 165, 169
  and 2.4 GHz fail) and green after.
- `rtw_get_center_ch` calls it, which removes the two tables (DRY).

**B. The Quest (this repo): an explicit offset instead of DONT_CARE.**
- `WfbngLink` passes `ChannelOffset` from the channel: in 5 GHz the lower channel of a pair gets
  `HAL_PRIME_CHNL_OFFSET_LOWER` (1, HT40+), the upper one `UPPER` (2, HT40-).
- No new app setting for 5 GHz, since the pair fixes it. A 2.4 GHz setting would only be needed for 40 MHz there,
  which nobody uses.
- The same pure helper (A) gives the offset, so there is one table only.

**C. The uplink at 40 MHz.** Either:
- C1. devourer sets `TX_DESC.DATA_SC` for a 20 MHz frame in a 40 MHz channel to the primary's sub-channel (the vendor
  driver's SCMapping per frame), so the uplink goes on the primary; or
- C2. the app sends the uplink at the link's width (`args->bandwidth = bw`) when at 40 MHz. That is simpler and leaves
  no sub-channel question, but costs ~3 dB of uplink SNR [INFERRED: noise bandwidth doubles].

Recommendation: A + B, and C1 if devourer is changed anyway (C2 as a no-submodule fallback). Before O82b uses 40 MHz,
check on air where the uplink lands, before and after the change.

**Air-unit coordination:** the air unit's 40 MHz primary (e.g. `iw … set channel 157 HT40+`) must be the same channel
the Quest uses as primary. For 157 that means HT40+ on both ends.

## Implemented (2026-09-28, code only, not yet on the headset)

The user chose option 1 (a fork). Everything is in code; the on-air check comes in O82b stage 1.
- **Fork:** https://github.com/tmariovlad/devourer, branch `pixelpilot-xr` from `bb03774`, pushed only there. This
  repo's `.gitmodules` points the submodule at the fork (`xr-native`).
- **A, devourer `978b84a`:** `src/ChannelCenter.h`, a pure header-only table (`center_channel`, `ht40_offset`,
  `center_80`/`center_40`). `rtw_get_center_ch` uses it, which removes the two old tables; `static_assert`s tie the
  offsets to the HAL values.
  - `tests/channel_center_selftest.cpp` (added to `CMakeLists.txt` as `channel_center`) checks the whole 5 GHz table
    for 20/40/80, the offsets, and 2.4 GHz by offset.
  - It was **red on the old map, extracted unchanged first**: 153, 161, 165–177, 2.4 GHz and all offsets failed.
    It is **green** after the fix [PROVEN: WSL g++ run].
- **C1, devourer `5e83556`:** the Jaguar1 TX path sets `TX_DESC.DATA_SC` with `tx_data_sc(channel width, frame width,
  primary)`. A 20 MHz frame in 40 MHz goes on the primary: 2 for primary lower, 1 for upper, the same values
  `phy_GetSecondaryChnl_8812` writes. Everything else stays 0 as before.
- **B, this repo:** `WfbngLink.cpp` passes `ChannelOffset = ht40_offset(channel)` at 40 MHz (DONT_CARE at 20 MHz).
- **The O82b case is a test** (the air unit on `157 80MHz` + `wfb_tx -B 40`, 40 MHz frames on 157/161, RX primary 157):
  the Quest at 40 MHz on 157 gets offset lower (HT40+), center 159, and uplink DATA_SC 2, i.e. 157.
- Tests: `channel_center` all checks passed (with `-Werror`); wfbng host tests 23/23; NDK build OK.

## How the devourer part was committed (was open; option 1 chosen)

devourer's origin is the upstream `https://github.com/openipc/devourer.git`, and the submodule is detached at `bb03774`.
A fix must not be pushed upstream by us. Options, for the coordinator to choose:
1. **A fork** `tmariovlad/devourer`, branch `pixelpilot-xr`. The fix goes there, this repo's `.gitmodules` points
   `app/wfbngrtl8812/src/main/cpp/devourer` at the fork (only on `xr-native`), and the submodule pointer moves.
   Clean history; CI and fresh clones follow the fork.
2. **A patch file in this repo** (`app/wfbngrtl8812/devourer-patches/*.patch`) applied at build time. The submodule
   stays upstream, but the build gets a patch step.
3. **Hand the finding to whoever maintains devourer upstream** and keep 20 MHz on the Quest until it lands.
