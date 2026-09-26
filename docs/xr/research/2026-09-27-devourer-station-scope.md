# Scope: Wi-Fi station (client) mode on devourer for APFPV through the RTL8812AU (2026-09-27)

Goal: the Android app joins the OpenIPC air unit's WPA2-PSK AP (`OpenIPC` / `12345678`, ch157, VHT80 center 155,
WMM on, `max_num_sta=1`, AP 192.168.0.1) through the RTL8812AU driven by devourer. It then receives the unicast RTP/H.264
stream (~850 pkt/s x ~1357 B, to 192.168.0.10:5600) and hands the UDP payload to the existing video path.
This is option 2 of [transport-choice.md](../transport-choice.md) and the mandate in [HANDOFF.md](../HANDOFF.md).

Paths are relative to `app/wfbngrtl8812/src/main/cpp/` (devourer = `devourer/`), unless they start with `app/`.
Read-only research: no code was changed and no device was touched.

## TL;DR

- **Feasible, about 6-8 working days.** Every hard piece exists in some form. The WPA2 crypto and the software CCMP are
  in the AP test harness `devourer/tests/ap_wpa2.cpp`. The hardware ACK knob is `SetAckResponder`. RX of frames
  addressed to us is promiscuous by default. What is missing is the supplicant half and some glue.
- **Recommended shape:** tune **ch157 at 20 MHz**. Advertise HT20 + WMM, but no VHT and no 40 MHz. Decline ADDBA (no
  A-MPDU). Use a static IP 192.168.0.10 with an ARP responder, and skip DHCP. Do software CCMP with a small vendored
  AES-128 + SHA-1. Send the decrypted UDP payload to `127.0.0.1:5600`, as the wfb path already does.
- **Top risk (a go/no-go gate before writing the protocol code):** devourer documents the **8812AU as a *degraded*
  hardware ACK responder**, at 97% delivery with ~7 mean retries [PROVEN: devourer/docs/scheduled-mac.md:182-185]. If
  that holds against the real AP, the AP will retransmit heavily and drop its rate. Measure it first (W0).
- **Two latent issues in `ap_wpa2.cpp` must be fixed when its code is reused:**
  1. It does not strip the 4-byte FCS before CCMP decrypt.
  2. It has no QoS-data AAD/nonce, and the AP will send QoS data because WMM is on.

---

## 1. What in `ap_wpa2.cpp` is reusable for the supplicant

The file is a single-client WPA2-PSK AP whose crypto is OpenSSL in userspace
[PROVEN: devourer/tests/ap_wpa2.cpp:1-18, 45-47]. It interoperates with a real Linux `wpa_supplicant`: the 4-way
handshake completes, encrypted DHCP works, and ping shows 0% loss
[PROVEN: devourer/docs/ap-mode.md:69-83].

| Function / block | Lines | Reuse for STA | Change needed |
|---|---|---|---|
| `kRsn` RSN IE (group CCMP, pairwise CCMP, AKM PSK) | 68-70 | **As is.** It goes into the assoc request and into msg2 key data (they must be byte-identical). | none |
| `enqueue()` + TX drain loop in `main` | 78-84, 419-424 | **Pattern as is.** `send_packet` must not run on the RX thread. | none [PROVEN: docs/ap-mode.md:19-20] |
| `mgmt_hdr()` | 85-89 | Pattern | STA→AP: addr1 = BSSID, addr2 = our MAC, addr3 = BSSID |
| `append_ies()` 5 GHz OFDM rate set | 90-102 (rates 99) | **Rates bytes as is** | add HT caps + WMM IE (see §7) |
| `prf()` (IEEE 802.11 PRF on HMAC-SHA1) | 105-116 | **As is** | swap HMAC backend (see §6) |
| `compute_ptk()` | 117-130 | **Logic as is.** min/max ordering of AA/SPA and ANonce/SNonce is role-symmetric. | AA = AP BSSID, SPA = our MAC. Move PBKDF2 (4096 iterations) out: compute the PMK **once** per SSID/PSK, not per handshake. |
| `set_mic()` / `check_mic()` (HMAC-SHA1-128 with KCK over EAPOL, MIC at offset 81) | 132-145 | **As is** | none |
| `aes_wrap()` (RFC 3394) | 147-156 | Not needed | the STA needs the **unwrap** (new, about 30 lines) for the GTK in msg3 and in group rekey msg 1/2 |
| `eapol_frame()` EAPOL-Key builder | 159-180 | **Body as is** (descriptor type 2, key info, replay counter, nonce, key data, MIC) | 802.11 wrapper becomes to-DS `08 01`, addr1/3 = BSSID, addr2 = STA. Key-length 0 in msg2/msg4. |
| `send_msg3()` key-data layout (RSN IE + GTK KDE `dd 16 00 0f ac 01`, pad `0xDD` then `0x00`) | 191-199 | **Parser spec** for msg3 key data | write the KDE walker |
| `csum16()` | 210-213 | **As is** | none |
| `ccmp_aad_nonce()` | 215-225 | **Core as is** (FC mask, A1-A3, seq mask, nonce `0\|A2\|PN`) | **Add QoS:** for `fc0=0x88`, AAD += QC masked to TID; nonce priority byte = TID. The current code is non-QoS only (`aadlen=22`, `nonce[0]=0`). |
| `ccm()` AES-128-CCM enc/dec, M=8, L=2 | 226-246 | **Semantics as is** | swap the OpenSSL EVP calls for the vendored CCM (§6) |
| `ccmp_tx()` | 248-267 | **Structure as is** (CCMP header with ext-IV and PN, MIC append) | `fc1 = 0x41` (to-DS + protected), addr1 = BSSID, addr2 = STA, addr3 = destination; nonce A2 = STA |
| `handle_plain()` ARP branch | 291-297 | **Pattern** | answer "who-has **192.168.0.10**" with our MAC, CCMP-encrypted to the AP |
| `on_rx()` dispatch + CCMP RX block + EAPOL parse | 321-386 (CCMP 349-365, EAPOL 366-384) | **Skeleton** | invert the direction checks (from-DS `fc1&0x02`, addr1 = us); STA state machine; see fixes below |
| `main()` device bring-up | 388-415 | Pattern only | in the app this is `WfbngLink::run` (§5) |
| DHCP server `dhcp_payload()` / ICMP echo | 270-286, 298-306 | **Not reused** | a DHCP *client* is different; skip DHCP entirely (static IP, §7) |

Fixes required when this code is lifted:
- **FCS.** `Packet::Data` holds the whole frame *including the trailing 4-byte FCS*
  [PROVEN: devourer/src/RxPacket.h:92-98]. Jaguar1 sets `RCR_APPFCS` in monitor mode
  [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:191-192], and the wfb path strips it
  (`- 4`) [PROVEN: WfbngLink.cpp:211,226]. `ap_wpa2` computes `ctlen = len - hlen - 8 - 8` with no FCS strip
  [PROVEN: devourer/tests/ap_wpa2.cpp:350-357]. On an FCS-appending chip that reads the MIC from the wrong offset and
  fails CCM.
  [INFERRED: the WPA2 AP was added in #227 on 2026-07-10, before #290 on 2026-07-15 made Jaguar2 append the FCS
  (`git log` of `tests/ap_wpa2.cpp` and `2ba608c`); ap-mode.md:17 says the AP was bench-validated on J2/J3. So it
  probably ran on a J2 adapter without an FCS. Either way, the STA code must subtract 4 on the 8812AU.]
- **QoS data.** The AP has `wmm_enabled=1`. With a WMM/HT station it sends QoS data (`fc0=0x88`, 26-byte header).
  `ap_wpa2` sets `hlen=26` for 0x88 [PROVEN: devourer/tests/ap_wpa2.cpp:348] but builds a non-QoS AAD
  [PROVEN: devourer/tests/ap_wpa2.cpp:215-225], so decryption of QoS frames would fail.
- **Replay/dup.** There is no PN replay check. The STA must drop PN <= last PN per key and TID. This also discards the
  AP's retransmissions of frames whose ACK was lost.

## 2. Channel and bandwidth: ch157, 80 MHz (center 155)

- **API:** `IRtlDevice::InitWrite(SelectedChannel{Channel, ChannelOffset, ChannelWidth})`, then at runtime
  `SetMonitorChannel` / `FastRetune` [PROVEN: devourer/src/IRtlDevice.h:53,67,78; devourer/src/SelectedChannel.h:17-27].
  There is no env var in the app path: `WfbngLink` fills `SelectedChannel` directly and today only maps `bw` to 20 or
  40 with `ChannelOffset=0` [PROVEN: WfbngLink.cpp:257-262]. (For the devourer demos, `DEVOURER_CHANNEL`, `DEVOURER_BW`
  and `DEVOURER_CHOFFSET` exist [PROVEN: devourer/examples/rx/main.cpp:1609-1631].)
- **Jaguar1 80 MHz math exists.** `rtw_get_center_ch` maps 149/153/157/161 to center 155
  [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:235-236]. `set_channel_bwmode` derives the 80 MHz prime offset
  from center vs primary [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:273-282], and
  `phy_GetSecondaryChnl_8812` programs the 20-in-80 sub-channel
  [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:2247-2268]. For primary 157 in 149-161:
  - center 155 < 157, so Offset80 = UPPER;
  - 157 is the lower half of the 157/161 pair, so `ChannelOffset = 1` (`HAL_PRIME_CHNL_OFFSET_LOWER`,
    RadioManagementModule.h:22);
  - the call is `SelectedChannel{157, 1, CHANNEL_WIDTH_80}`.
  [INFERRED: from the cited mapping. This also matches hostapd's HT40+ for ch157 with center 155.]
- **RX of VHT80:** a receiver parked at 80 MHz decodes 20/40/80 frames on its primary without retuning, with a 0 dB
  wide-RX penalty [PROVEN: devourer/docs/pseudo-preamble-puncturing.md:107-116]. That was proven with an **8814AU** RX,
  which is the Jaguar1 code path (`tests/rx80_narrow_tx_probe.sh:17`). **No devourer doc or test shows 80 MHz RX on the
  8812AU specifically** [PROVEN: grep of devourer docs/tests for 8812AU plus 80 MHz found nothing]. So 80 MHz on the
  8812AU is [INFERRED: same J1 code path as the 8814AU], not proven.
- **TX at a narrower width while tuned wide is a trap.** The J1 TX descriptor sets `DATA_BW` from radiotap but never
  writes `DATA_SC` (the sub-channel) [PROVEN: devourer/src/jaguar1/RtlJaguarDevice.cpp:1085-1100; grep finds no
  `DATA_SC` in the TX path]. A 20 MHz auth/assoc/EAPOL/ARP frame sent while tuned to 80 MHz may not land on primary 157
  [SPECULATION: the vendor driver sets TX `DATA_SC` via SCMapping; without it the placement is undefined].
- **Recommendation: tune ch157 at 20 MHz** (`SelectedChannel{157, 0, CHANNEL_WIDTH_20}`), which is the path the app
  already uses. Advertise HT caps with *Supported Channel Width Set = 0* and no VHT IE, so the AP must send to us at
  20 MHz. The beacons are 20 MHz non-HT on the primary anyway. HT20 MCS7-15 (72-144 Mbit/s) is far above the
  9.2 Mbit/s stream. [INFERRED: an AP limits a STA to the STA's advertised width; the vendor 8812eu driver's rate mask
  obeying this is SPECULATION until measured.] Wide RX remains a later lever.

## 3. Hardware ACK for frames addressed to our station MAC

- **Mechanism.** `SetAckResponder(mac)` does three things:
  - writes `REG_MACID` 0x610 and `REG_BSSID` 0x618 = `mac`;
  - sets MSR/net_type 0x102[1:0] = 3 (AP);
  - the MAC then auto-ACKs any unicast frame whose RA = MACID, SIFS-timed, with no host involvement.

  Monitor RX and injection stay as they were [PROVEN: devourer/src/AckResponder.h:3-34, 43-54;
  devourer/src/IRtlDevice.h:214-227]. The Jaguar1 implementation is at
  [PROVEN: devourer/src/jaguar1/RtlJaguarDevice.cpp:737-751]. It can also be armed at bring-up with
  `DeviceConfig rx.ack_responder` [PROVEN: devourer/src/DeviceConfig.h:147-152;
  devourer/src/jaguar1/RtlJaguarDevice.cpp:76-77].
- **The MAC must be unicast** (I/G bit clear). Use a locally-administered `02:..` address
  [PROVEN: devourer/docs/ap-mode.md:55-60; devourer/docs/aggregation.md:175-180].
- **Proven with a real peer?**
  - Yes against a real Linux station in AP mode: auth/assoc arrive at retry=0 [PROVEN: devourer/docs/ap-mode.md:49-53].
    That was via the `StartBeacon` MACID, on J2/J3 adapters (ap-mode.md:17).
  - Closed-loop devourer-to-devourer measurements [PROVEN: devourer/docs/aggregation.md:155-161;
    devourer/docs/scheduled-mac.md:168-185]:
    - responder ON gives 100% delivery at 0.4 mean retries;
    - **8814AU responder: retries ~0.1**;
    - **8812AU responder: "works but degraded (97% delivery at ~7 mean retries — its SIFS ACKs only land
      intermittently)"**;
    - 8821AU never closed the loop.
  - The 8812AU has **never been tested as a responder against a third-party AP**. This is the #1 risk.
  - The 8812AU as the *soliciting* TX is fine: 1.00 ACK rate at 0.34 retries [PROVEN: devourer/docs/scheduled-mac.md:172].
    So our own auth/assoc/EAPOL/ARP get hardware retries **if** `DeviceConfig tx.retry_limit > 0`. The default is 0, and
    the app never sets it [PROVEN: devourer/src/DeviceConfig.h:180-186; devourer/src/jaguar1/RtlJaguarDevice.cpp:1171-1178;
    WfbngLink.cpp:159-172].
- **Why the degraded 8812AU ACK may be fixable** [SPECULATION]. The kernel 88XXau driver is a clean STA on the same chip
  (the HIL GS `.208` does APFPV with it). devourer's recipe differs from a kernel STA in these ways:
  - net_type 3 (AP) instead of 2 (Infra);
  - BSSID reg = own MAC instead of the AP BSSID;
  - monitor RCR with `AAP` and no `CBSSID` [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:186-213];
  - the response-rate/SIFS init [PROVEN: devourer/src/jaguar1/HalModule.cpp:1749-1777].

  A register diff (kernel STA vs devourer), in the style of devourer's existing usbmon/end-state diff tests, is the way
  to find the difference.
- **Does RX still deliver frames addressed to us while ACKing?** Yes:
  - monitor RCR = `AAP|APM|AM|AB|ADF|ACF|AMF` with `RXFLTMAP2=0xFFFF`, so every frame reaches the host
    [PROVEN: devourer/src/jaguar1/RadioManagementModule.cpp:188-213];
  - the responder leaves "monitor RX/injection unchanged" [PROVEN: devourer/src/AckResponder.h:11-13];
  - the AP harness receives and answers frames addressed to its MACID while ACKing them
    [PROVEN: devourer/docs/ap-mode.md:49-53].
- **HW crypto engine.** J1 never programs `SECCFG`/CAM keys (grep finds no SECCFG in `src/jaguar1`; bring-up
  clears the CAM). So protected frames reach the host raw and the software CCMP works on them
  [INFERRED: from grep plus the J2/J3 proof in docs/ap-mode.md:78-90].
- **Also answered by the same gate** [SPECULATION]: RTS→CTS and the null-data poll the AP sends for
  `ap_max_inactivity`. The poll is a plain unicast frame, so a working ACK covers it.

## 4. A-MPDU / BlockAck

- **RX side:** Realtek chips de-aggregate in hardware. Each MPDU arrives with its own RX descriptor, and devourer's J1
  parser walks the USB aggregate into separate `Packet`s and flags `paggr` (the MPDU came inside an A-MPDU)
  [PROVEN: devourer/src/jaguar1/FrameParser.cpp:100-103, 150-200; devourer/src/RxPacket.h:72-79]. So an A-MPDU from the
  AP would reach the callback as individual MPDUs [INFERRED: from the parser; A-MPDU RX from a third-party AP has not
  been tested on J1].
- **BlockAck:** the same MACID + net_type gate makes the MAC send an immediate hardware BlockAck, with no ADDBA state.
  This is proven with a J3 TX and a J2 (0x012d) responder [PROVEN: devourer/src/AckResponder.h:15-20;
  devourer/docs/aggregation.md:163-173; devourer/tests/ampdu_ba_check.sh:22-26]. It is **not proven with an 8812AU
  responder**, and the plain ACK on the 8812AU is already degraded (§3).
- **What devourer does not have:** any ADDBA/DELBA action-frame handling (the harnesses have none; grep finds no
  ADDBA code), and no RX reorder buffer.
- **Recommendation: decline.** Answer the AP's ADDBA Request (Action, category 3, action 0) with an ADDBA Response of
  status 37 (REQUEST_DECLINED), or do not advertise HT at all. The AP then sends single MPDUs with normal ACK. For
  ~9.2 Mbit/s, single MPDUs at HT20 MCS7 SGI take about 25-30% airtime [INFERRED: 850 x (~150 us PPDU + SIFS + ACK +
  backoff)], which is acceptable. It also removes BA-window and reorder latency, and the risk of an untested 8812AU BA.
  Accepting (with hardware BA) is a later experiment, and would need software reordering by SN/PN.
- **Fallback if the AP ignores the decline:** send DELBA, or drop HT from the assoc request, so the AP uses legacy
  OFDM up to 54 Mbit/s with no aggregation possible.

## 5. How `WfbngLink.cpp` drives devourer, and where station mode goes

| Step | Code |
|---|---|
| libusb init, wrap the Android fd (`libusb_wrap_sys_device`) | WfbngLink.cpp:104-121 |
| per-adapter `UsbDeviceLock` with a bounded wait for the 2D→XR handoff | WfbngLink.cpp:124-150 |
| claim interface 0; `DeviceConfig`: `rx.enable_with_tx=true`, `usb.lock_dir=filesDir`, `rx_zerocopy=false` | WfbngLink.cpp:152-172 |
| `WiFiDriver::CreateRtlDevice(dev_handle, ctx, usb_lock, cfg)` | WfbngLink.cpp:174 |
| RX callback lambda: `RxFrame::IsValidWfbFrame`, channel-id match, strip the 802.11 header and the 4-byte FCS, then `video_aggregator->process_packet` | WfbngLink.cpp:190-245 |
| `InitWrite(SelectedChannel{ch, 0, 20/40})` | WfbngLink.cpp:257-262 |
| TX thread: `TxFrame::run(device)` reads UDP 8001 and calls `send_packet` | WfbngLink.cpp:264-288; TxFrame.cpp:504, 798 |
| blocking `StartRxLoop(packetProcessor)` on the JNI thread | WfbngLink.cpp:295-302 |
| teardown: `Stop()`, erase the device (which releases the lock), release the interface | WfbngLink.cpp:317-339 |
| JNI entry `nativeRun(ch, bw, fd)` on a Java thread | WfbngLink.cpp:400; wfbngrtl8812/.../WfbNgLink.java:42,130 |

**How video reaches the decoder today:** through localhost UDP.
1. wfb-ng's `AggregatorUDPv4` is constructed for `127.0.0.1:5600` [PROVEN: WfbngLink.cpp:75-84] and `sendto`s each
   decoded RTP packet [PROVEN: wfb-ng/src/rx.cpp:934-936].
2. `VideoPlayer::start` creates a `UDPReceiver` on port 5600, bound to `INADDR_ANY`, which calls `onNewRTPData`
   [PROVEN: app/videonative/src/main/cpp/VideoPlayer.cpp:187-197; app/videonative/src/main/cpp/UdpReceiver.cpp:69-110].

There is also an abstract-UDS receiver `"\0my_socket"` feeding the same `onNewRTPData`
[PROVEN: app/videonative/src/main/cpp/VideoPlayer.cpp:199-213].

**Cleanest insertion point:** a new native class (e.g. `StaLink`, or a `StationSession` beside `WfbngLink`), selected by
a transport mode. It reuses steps 1-3 and the teardown of `run()` unchanged: the lock, the claim and the device
creation. It differs in these ways:
- `cfg.rx.ack_responder = sta_mac` and `cfg.tx.retry_limit = 4..7`;
- `InitWrite(SelectedChannel{157, 0, CHANNEL_WIDTH_20})`;
- its own TX-queue thread instead of `TxFrame` (`send_packet` must stay off the RX thread
  [PROVEN: docs/ap-mode.md:19-20; tests/probe_responder.cpp:45-46]);
- an RX callback running the STA state machine;
- video delivered by `sendto(127.0.0.1:5600)` of the decrypted UDP payload, so **zero changes in videonative**.

Keep the protocol core (state machine, crypto, frame builders) in pure C++ with no JNI and no libusb. That lets it run
as a host gtest in WSL like the existing `tests/` (CLAUDE.md "Tests"). Loopback UDP costs tens of microseconds and is
already what the wfb path pays [INFERRED].

## 6. Crypto on Android

- **What is linked today:** `libWfbngRtl8812.so` links `devourer`, `wfb-ng`, `libusb1.0.so`, **`libsodium.so`** and
  `libpcap.a` [PROVEN: wfbngrtl8812/src/main/cpp/CMakeLists.txt:114-121]. videonative links no crypto
  [PROVEN: app/videonative/src/main/cpp/CMakeLists.txt, grep]. There is **no OpenSSL/BoringSSL/mbedTLS** anywhere
  outside `ap_wpa2.cpp` [PROVEN: grep of `app/` for sha1/aes/pbkdf2 implementations].
- **libsodium 1.0.19 does not cover WPA2.** It has HMAC-SHA256/512, SHA-256/512, AES-256-GCM, ChaCha and
  `randombytes`, but **no SHA-1, no AES-128, no CCM, no PBKDF2** [PROVEN: include/sodium/ header list;
  include/sodium/version.h:7]. Use it only for `randombytes_buf` (the SNonce).
- **Needed:** PBKDF2-HMAC-SHA1 (4096 iterations → PMK, once), HMAC-SHA1 (PRF-384 for the CCMP PTK, EAPOL MIC),
  AES-128 encrypt (CCM = CTR + CBC-MAC use only the forward cipher), AES-128 decrypt (only for RFC 3394 unwrap of the
  GTK).
- **Smallest dependency-free option (recommended):** vendor two small public-domain files:
  - SHA-1 (Steve Reid's, about 150 lines);
  - AES-128 with encrypt + decrypt (e.g. tiny-AES-c, Unlicense, about 300 lines);

  plus about 150 lines of glue: HMAC-SHA1, PBKDF2, PRF, CCM-8, RFC 3394 unwrap. Put it in a `wpa_crypto.{h,cpp}` with no
  dependencies. Test it on the host with known vectors:
  - RFC 3174 (SHA-1);
  - RFC 2202 (HMAC-SHA1);
  - RFC 6070 (PBKDF2);
  - FIPS-197 (AES);
  - RFC 3394 §4.1 (unwrap);
  - IEEE 802.11 Annex J CCMP / PRF test vectors;
  - `ap_wpa2`'s OpenSSL output as a cross-check.

  Alternative with the same shape: lift wpa_supplicant's `src/crypto/{sha1-internal,sha1-pbkdf2,sha1-prf,aes-internal*,
  aes-unwrap}.c` (BSD, compatible with devourer's GPL-2.0, `devourer/LICENSE:1-2`).
- **Performance:** software CCM for 850 x 1357 B ≈ 1.15 MB/s ≈ 145k AES blocks/s (CTR + CBC-MAC). A table-based C AES
  on the XR2's A77 cores costs a few percent of one core [SPECULATION: ~200-400 ns/block → 30-60 ms CPU per second].
  The ARMv8 Crypto Extension intrinsics (`vaeseq_u8`/`vaesmcq_u8`) would make it negligible if needed.
- **Rejected:** a prebuilt OpenSSL/BoringSSL (MB-sized, new build plumbing); Java `javax.crypto` via JNI per packet
  (Android has no AES-CCM provider, and the per-packet JNI cost).

## 7. Minimum viable protocol for receive-only video

**Required:**
1. **Find the BSS.**
   - Either fix the channel at 157 or dwell on it and wait for a beacon with SSID `OpenIPC`. Take the BSSID from addr3,
     and check the RSN IE and the HT/VHT operation.
   - A directed probe request (`fc 0x40`) is optional; beacons every 100 TU are enough.
2. **Open System auth.** Send `b0 00` with alg 0, seq 1. Expect seq 2, status 0.
3. **Assoc request** (`00 00`):
   - capability ESS | Privacy (`0x0011`), listen interval, SSID;
   - rates `01 08 8c 12 98 24 b0 48 60 6c` (5 GHz OFDM, ap_wpa2.cpp:99);
   - RSN IE `kRsn` (ap_wpa2.cpp:68-70);
   - **HT Capabilities** (20 MHz only; SGI20; RX-STBC1; RX MCS 0-15; A-MPDU parameters present but we will decline BA);
   - **WMM Information Element** (`dd 07 00 50 f2 02 00 01 00`).

   WMM is required for the AP to use HT with us [SPECULATION: hostapd only enables HT for a WMM STA; verify on the air
   unit's hostapd]. Omit VHT caps. Parse the Assoc Response: status 0 and AID.
4. **EAPOL supplicant.**
   - **msg1:** keyinfo `0x008a`. Store the ANonce and the replay counter. Generate the SNonce. Derive the PTK
     (`compute_ptk`, roles swapped).
   - **msg2:** keyinfo `0x010a`, key-len 0, SNonce, key data = the assoc RSN IE, MIC with KCK, same replay counter.
   - **msg3:** keyinfo `0x13ca`. Verify the replay counter increased, the ANonce is unchanged and the MIC is valid.
     AES-unwrap the key data with KEK = PTK[16:32], then extract the GTK KDE (key id, 16 B GTK).
   - **msg4:** keyinfo `0x030a`, MIC, same replay counter.
   - Install TK = PTK[32:48] (pairwise) and the GTK.
   - EAPOL-Key frames are cleartext 802.11 data with LLC `aa aa 03 00 00 00 88 8e`, before the keys are installed.
4b. **Group-key rekey handshake (required).** hostapd rekeys the GTK periodically (`wpa_group_rekey`). After the 4-way,
   EAPOL frames arrive **CCMP-encrypted with the PTK**. On a group msg 1/2 (keyinfo: group, ack, MIC, secure, enc):
   unwrap the new GTK and answer 2/2 (MIC, secure). If this is ignored, hostapd disconnects the station after its retries
   [SPECULATION: hostapd "group key handshake failed ... after N tries" → deauth; the interval depends on the air
   unit's hostapd defaults].
5. **CCMP RX decrypt:**
   - from-DS data (`fc1 & 0x02`, addr1 = us or group);
   - strip the FCS, header 24 or 26 (QoS), CCMP header 8, MIC 8;
   - QoS-aware AAD and nonce;
   - key = TK for unicast, GTK for group (key id from CCMP header byte 3 bits 6-7);
   - PN replay check per key and TID.
6. **LLC/SNAP → IPv4 → UDP dst 5600** → `sendto(127.0.0.1:5600, udp_payload)`. Ignore fragments (RTP at ~1357 B is
   below the MTU).
7. **ARP responder for 192.168.0.10** (static IP; no DHCP):
   - The AP's ARP request for .10 is a **broadcast, GTK-encrypted**. Decrypt it and reply unicast, **CCMP-encrypted with
     the TK**, to-DS.
   - Without an ARP entry, the air unit's kernel drops the UDP sends.
   - Also send one ARP request for 192.168.0.1 right after keying. Linux learns the requester's IP/MAC from an ARP
     request addressed to it, which primes the entry even before any broadcast is seen [SPECULATION: standard Linux
     neighbour behaviour].
   - Keep answering the later unicast NUD probes.
8. **Deauth (`c0`) / Disassoc (`a0`) from the BSSID to us:** clear the keys and restart from step 2 after a short
   back-off. **Beacon loss** (no beacon for ~2-3 s) also means rejoin.
9. **ADDBA Request → ADDBA Response, status 37** (§4).
10. **TX:** our frames are auth, assoc, EAPOL msg2/4 and group 2/2, ARP and ADDBA-resp.
    - Rate: 6 Mbit/s legacy (`build_stream_radiotap(parse_tx_mode_str("6M"))`, ap_wpa2.cpp:405).
    - `tx.retry_limit > 0` so the chip retries until the AP ACKs.
    - Sequence numbers are stamped by hardware (`HWSEQ_EN=1`, RtlJaguarDevice.cpp:1160).

**Can be skipped, and why:**
- **DHCP client.** The air unit sends to a fixed 192.168.0.10 [PROVEN: docs/xr/real-link.md:189 `"server":
  "udp://192.168.0.10:5600"`]. With `max_num_sta=1` there is no address conflict. Claim .10 statically and answer ARP.
  Add a minimal DHCP client later only if the air unit's scripts gate on a lease [SPECULATION].
- **Null-data / keep-alive TX.** The AP's inactivity poll (`ap_max_inactivity=3600`) is a unicast null frame, so the
  hardware ACK answers it. The ARP answers also count as activity. We never set the PM bit, so there is no PS-Poll and
  no TIM handling.
- **PMF/SA-Query** (not configured on the AP), **VHT/80 MHz**, **A-MPDU**, **multicast beyond ARP**, **IPv6**, **ICMP**,
  **PTK rekey** (off by default in hostapd), **TKIP**, **roaming**, **scan across bands**.
- **TX of video:** the path is receive-only, and uplink telemetry stays out of scope.

## 8. Work breakdown and top risks

| # | Work item | Size | Output |
|---|---|---|---|
| **W0** | **Gate: 8812AU ACK health on ch157 against the real AP.** Minimal harness: arm `SetAckResponder(02:..)`, send open auth + assoc (no crypto), and log the **retry bit** of every AP frame addressed to us (auth resp, assoc resp, then the AP's EAPOL msg1 retries). Alternate with a kernel-STA run on the HIL GS for reference, N >= 2 per state. If it is degraded, register-diff kernel STA vs devourer (net_type 2 vs 3, BSSID reg, RRSR/SIFS). | 0.5-1 d | go/no-go and the register recipe |
| W1 | `wpa_crypto` (vendored SHA-1/AES + HMAC/PBKDF2/PRF/CCM/unwrap) + host gtests with the RFC/802.11 vectors | 1 d | ~500 LOC |
| W2 | STA state machine: BSS discovery, auth, assoc IEs, EAPOL 4-way + group rekey, deauth/disassoc/beacon-loss, ADDBA decline; pcap-replay host tests | 1.5-2 d | ~600 LOC |
| W3 | Data plane: CCMP RX (QoS, FCS, PN, TK/GTK), LLC/IP/UDP decap → `127.0.0.1:5600`, ARP responder (CCMP TX) | 1 d | ~300 LOC |
| W4 | App integration: new native session beside `WfbngLink::run`, JNI entry, Java transport toggle (e.g. in **Video → Latency experiments** or a link-mode setting), TX-queue thread, handoff/lock reuse | 1 d | |
| W5 | On-device bring-up with the air unit in APFPV, then measure: G2G and loss vs wfb-ng and vs Quest internal Wi-Fi, alternated, N >= 2, headset fixed (CLAUDE.md rules) | 1-2 d | results in `docs/xr/real-link.md` / `g2g-budget.md` |

**Total: about 6-8 days** (matches "days of work, with risk" in transport-choice.md).

**Top risks:**
1. **Degraded 8812AU hardware ACK** (scheduled-mac.md:182-185). Unacked frames make the AP retransmit up to its limit,
   drop its rate (longer airtime) and add latency spikes. hostapd `disassoc_low_ack` may also kick the station
   [SPECULATION: depends on the 8812eu driver reporting low-ACK events]. Mitigations:
   - W0 first;
   - a register fix;
   - worst case, live with it: the AP's retries still deliver, at a latency cost.
2. **Bandwidth/sub-channel.** 80 MHz RX on the 8812AU is not bench-proven, and the TX `DATA_SC` is not set (§2).
   Mitigation: 20 MHz tune + HT20-only caps.
3. **AP rate control and latency.** The AP (vendor 8812eu driver, firmware rate adaptation) picks our MCS from our caps
   and the ACK success. APFPV "hides its retransmissions" (transport-choice.md:14), so G2G may show spikes that wfb-ng
   does not have. This is exactly what W5 has to measure.
4. **A-MPDU.** If the AP keeps aggregating despite the decline, and the 8812AU BA response is also flaky, loss follows.
   Mitigation: drop HT (54 Mbit/s legacy is still 5x the stream).
5. **Reused-code bugs.** FCS not stripped, and non-QoS AAD (§1). Unit tests with a captured QoS CCMP frame catch both.
6. **Group rekey** unhandled means a periodic disconnect (§7 4b).
7. **USB RX thread and CPU.** The callback runs on the libusb event thread. Decrypt there (fast), but never TX there.
   The ARP/EAPOL replies go through the TX-queue thread. The userspace RX→TX round trip is a few ms, far inside EAPOL
   timeouts [PROVEN: docs/ap-mode.md:44-45].
8. **`max_num_sta=1`.** The Quest's internal Wi-Fi or the PC card ("Wi-Fi 2") holding the association blocks us
   [PROVEN: docs/xr/HANDOFF.md:20]. Detect assoc status 17 (AP full) and tell the user.
9. **Retry-limit scope.** `tx.retry_limit` is session-wide. That is fine because station mode is its own session, but it
   must not leak into the wfb session (whose default is 0 on purpose) [PROVEN: devourer/src/DeviceConfig.h:180-186].

## Open questions / hypotheses

- [SPECULATION] Is the 8812AU ACK degradation specific to devourer's register state (net_type=AP, BSSID reg = own MAC,
  monitor RCR), or a chip limit? The kernel STA on the same chip works, which points to registers. W0 decides.
- [SPECULATION] Does the air unit's hostapd/8812eu actually transmit VHT80 frames, and does it honour a 20 MHz-only STA?
  Check with our RX `bw` attribute (`FrameParser.cpp:122`) during W0.
- [SPECULATION] The hostapd `wpa_group_rekey` value on the air unit, and whether it requires WMM for HT. Read
  `/etc/hostapd.conf` and the hostapd version on `.132` before W2.
- [SPECULATION] Does `waybeam` or the air unit need anything beyond ARP (e.g. a DHCP lease) before it starts sending to
  .10? The HIL GS path suggests not (fixed destination), but it is unverified.
