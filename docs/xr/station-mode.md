# APFPV through the RTL8812AU: devourer station mode (option 2)

Quest XR docs: [guide](../xr-quest.md) · [transport choice](transport-choice.md) · [real link](real-link.md) · [troubleshooting](troubleshooting.md) · repo rules in [CLAUDE.md](../../CLAUDE.md)

The goal: receive the air unit's APFPV video (a WPA2 Wi-Fi AP) through the RTL8812AU on the Quest. That needs a Wi-Fi *client* on top of devourer, which today only has the AP side. The full scope, reuse map and risks are in [research/2026-09-27-devourer-station-scope.md](research/2026-09-27-devourer-station-scope.md) (~6–8 days). APFPV through the Quest's own Wi-Fi already beats wfb-ng at MCS2 in one room ([measured](transport-choice.md#measured-apfpv-quest-internal-wi-fi-vs-wfb-ng-rtl8812au-2026-09-27)).

## Status (2026-09-27)

| Step (scope §8) | State |
|---|---|
| W0 go/no-go gate: does the 8812AU's hardware ACK work against the real AP? | harness built and unit-tested; **not run yet** (needs slot 4 on the air unit) |
| W1+ supplicant, CCMP RX, ARP, hand-off to the video path | not started; waits for the W0 result |

## Code

- [sta/StaFrames.h](../../app/wfbngrtl8812/src/main/cpp/sta/StaFrames.h) / [.cpp](../../app/wfbngrtl8812/src/main/cpp/sta/StaFrames.cpp): station-side 802.11 builders and parsers (open auth, association request with RSN / HT20 / WMM, deauth; header, beacon, response-status parsing). Pure bytes, no devourer dependency, so the app can reuse it later.
- [sta/tools/sta_ack_gate.cpp](../../app/wfbngrtl8812/src/main/cpp/sta/tools/sta_ack_gate.cpp): the W0 harness (Linux host, devourer over libusb).
- [sta/tests/StaFrames_test.cpp](../../app/wfbngrtl8812/src/main/cpp/sta/tests/StaFrames_test.cpp): 8 gtests [PROVEN: `ctest` 8/8 in WSL Ubuntu-22.04, 2026-09-27].
- Host build ([sta/host/CMakeLists.txt](../../app/wfbngrtl8812/src/main/cpp/sta/host/CMakeLists.txt)), from the repo root in WSL Ubuntu-22.04:

```bash
cmake -S app/wfbngrtl8812/src/main/cpp/devourer -B /tmp/devourer-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/devourer-build --target devourer -j16
cmake -S app/wfbngrtl8812/src/main/cpp/sta/host -B /tmp/sta-host -DDEVOURER_LIB=/tmp/devourer-build/libdevourer.a
cmake --build /tmp/sta-host -j16 && (cd /tmp/sta-host && ctest --output-on-failure)
```

The station code lives outside the devourer submodule (which is upstream OpenIPC's repo).

## W0 gate: how it works

- The harness associates to the air unit's AP with **open authentication and no crypto**. A WPA2 AP accepts the association when the request carries the RSN element.
- It then stays silent. hostapd sends EAPOL msg1, retries it, deauthenticates after the 4-way timeout, and the harness starts over. Each cycle yields an auth response, an association response, several EAPOL msg1 data frames and a deauth, all unicast to our MAC.
- For every such frame, grouped by class and sequence number, it records how many copies arrived and whether the first copy already had the Retry bit set:
  - with a working hardware ACK, each MPDU arrives once with Retry = 0;
  - without one, the AP's MAC retransmits it with Retry = 1.
- devourer documents the 8812AU as a degraded responder against another devourer: 97 % delivery at ~7 mean retries (devourer `docs/scheduled-mac.md:182-185`). It has never been tried against a third-party AP. That is why this gate comes first.

**Limit:** mostly low-rate frames (management frames and EAPOL, which the AP sends at a basic rate). It does not show how the ACK behaves for high-MCS video data. That needs W1, the full handshake [SPECULATION: Realtek vendor drivers such as the air unit's 8812eu usually send EAPOL at a low rate; not checked].

## W0 gate: procedure for the slot (slot 4 with the coordinator)

1. **Air unit on APFPV** (OpenIPC session: `linkmode-air.sh apfpv`). The AP takes **one client** (`max_num_sta=1`), so the Quest must not be on `OpenIPC`: `adb shell cmd wifi connect-network Zeul36 …`, or any saved home network.
2. **RTL8812AU from the Quest to the PC**, then attach it to WSL (usbipd runs as a service; see the global `wsl-usb` rule):

```bash
usbipd list                              # find the BUSID of 0bda:8812
usbipd bind --busid <id>; usbipd attach --wsl --busid <id>
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -u root bash -lc 'lsusb | grep -i 0bda'
```

3. **Alternate, N ≥ 2 each, with nothing moved:**

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -u root bash -lc 'GATE_ACK=1 /tmp/sta-host/sta_ack_gate 60'
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -u root bash -lc 'GATE_ACK=0 /tmp/sta-host/sta_ack_gate 60'
```

4. **Read the `GATE` report** (`copies/mpdu`, `first_copy_retry`, `repeated` per class):
   - **GO:** with `GATE_ACK=1`, `repeated` stays at a few percent and `copies/mpdu` ≈ 1, while `GATE_ACK=0` shows most MPDUs repeated.
   - **NO-GO:** both look alike. The next step is then the register diff between the kernel station and devourer (net_type, BSSID register, response rate / SIFS; scope §3).
5. **Afterwards:** detach the RTL (`usbipd detach --busid <id>`), plug it back into the Quest, and return the air unit to wfb (OpenIPC session).
