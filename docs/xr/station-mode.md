# APFPV through the RTL8812AU: devourer station mode (option 2)

Quest XR docs: [guide](../xr-quest.md) · [transport choice](transport-choice.md) · [real link](real-link.md) · [troubleshooting](troubleshooting.md) · repo rules in [CLAUDE.md](../../CLAUDE.md)

The goal: receive the air unit's APFPV video (a WPA2 Wi-Fi AP) through the RTL8812AU on the Quest. That needs a Wi-Fi *client* on top of devourer, which today only has the AP side. The full scope, reuse map and risks are in [research/2026-09-27-devourer-station-scope.md](research/2026-09-27-devourer-station-scope.md) (~6–8 days). At 1080p90 / 8000 kbit/s in one room, APFPV through the Quest's own Wi-Fi beats wfb-ng at MCS2 on loss, jitter and frame delivery ([slot 4A](transport-choice.md#re-measured-at-8000-kbits-on-both-arms-slot-4a-2026-09-27), N = 2 per arm). The first comparison, at ~1000 kbit/s, was withdrawn.

## Status (2026-09-27)

| Step (scope §8) | State |
|---|---|
| W0 go/no-go gate: does the 8812AU's hardware ACK work against the real AP? | **GO** (slot 4B, 2026-09-27): with the ACK on, every frame from the AP arrives once; with it off, 100 % are retransmitted ([result](#w0-result-go-2026-09-27)) |
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

## W0 result: GO (2026-09-27)

**Setup:**
- Air unit `.132` on APFPV: hostapd on ch157 / VHT80, 1080p90 / 8000 kbit/s, no other client; the Quest was on its home network.
- RTL8812AU on PC-VLAD, attached to WSL Ubuntu-22.04 over usbipd, `sta_ack_gate` as root on ch157 at 20 MHz, station MAC `02:42:75:05:d6:10`.
- `GATE_ACK` alternated 1 / 0 / 1 / 0, 60 s each, nothing moved.
- Each run: 11 cycles of auth → assoc → EAPOL msg1 (retried by hostapd) → deauth, 82 distinct MPDUs addressed to us, ~587 beacons per 60 s, RSSI raw ~68.

| Run | ACK | Copies per MPDU (all) | MPDUs repeated | Data (EAPOL msg1) copies per MPDU | Mgmt (auth/assoc resp) copies per MPDU |
|---|---|---|---|---|---|
| gate1 | on | 1.00 | 0.0 % | 1.00 | 1.00 / 1.00 |
| gate2 | off | 22.57 | 100 % | 32.81 | 7.00 / 6.92 |
| gate3 | on | 1.01 | 1.2 % (one auth response) | 1.00 | 1.08 / 1.00 |
| gate4 | off | 22.65 | 100 % | 32.94 | 6.92 / 7.00 |

- **Verdict: GO** [PROVEN: [data/2026-09-27-w0-ack-gate.csv](data/2026-09-27-w0-ack-gate.csv)].
  - With the hardware ACK armed, the AP's frames to our MAC arrive once with Retry = 0.
  - Without it, the AP's MAC retransmits every one up to its retry limit: ~7 for management, ~33 for data, ~13 for deauth.
  - The "degraded 8812AU responder" risk from the scope (97 % at ~7 retries against another devourer) does not show against hostapd on the 8812eu at this range.
- **Independent check on the air unit:** `logread` shows 48 × "associated" and 48 × "disassociated" for `02:42:75:05:d6:10` over the slot [PROVEN: OpenIPC session's report, epoch 1790506383]. That is the 44 counted cycles plus a few reassociations.
- **Limit:** the gate covers management and EAPOL frames only, sent at a low rate. The ACK for high-MCS video data is proven only in W1.
- **Data provenance:** the four `GATE` summaries were printed by the harness during the session and are transcribed into the CSV.
  - The raw run logs were lost. A `wsl.exe … bash -c '…$VAR…'` invocation from Git Bash expanded the variables to nothing, so the logs landed in WSL's `/` and were deleted by the follow-up command.
  - Next time put WSL commands in a `.sh` file (global escaping rule).

## W0 gate: procedure for the slot (slot 4 with the coordinator)

1. **Air unit on APFPV** (OpenIPC session: `linkmode-air.sh apfpv`). Check waybeam's bitrate after the switch (`wget -qO- http://127.0.0.1/api/v1/config.json | grep -o '"bitrate":[0-9]*'`): the switch restores `/opt/linkmode/.orig_bitrate`, which once held a stale 1000 ([correction](transport-choice.md#measured-apfpv-quest-internal-wi-fi-vs-wfb-ng-rtl8812au-2026-09-27)). The AP takes **one client** (`max_num_sta=1`), so the Quest must not be on `OpenIPC`: `adb shell cmd wifi connect-network Zeul36 …`, or any saved home network.
2. **RTL8812AU from the Quest to the PC**, then attach it to WSL (usbipd runs as a service; see the global `wsl-usb` rule).
   - **Blocked on PC-VLAD (2026-09-27):** `usbipd bind --busid 4-8` needed admin (one UAC, accepted; the adapter is now "Shared"). `usbipd attach` then fails: "The VBoxUsbMon driver is not correctly installed" [PROVEN].
   - The `VBoxUSBMon` service does not exist (`sc query` → 1060) and the `usbipd` service is stopped, although the driver files are in `C:/Program Files/usbipd-win/Drivers` [PROVEN]. VirtualBox is no longer installed. [INFERRED: its uninstall removed the shared `VBoxUSBMon` service; the `flash-usb` skill already notes "VBoxUSBMon broken" on this PC.]
   - Repair, user-approved:
     - `msiexec /fa` fails with **1706**: the original MSI source is gone [PROVEN: MSI log `SOURCEMGMT: Failed to resolve source`], even when a verified v5.3.0 MSI is supplied.
     - `msiexec /i usbipd-win_5.3.0_x64.msi REINSTALL=ALL REINSTALLMODE=vamus /qn /norestart` succeeded (exit 0, no reboot), and **`VBoxUSBMon` now runs** [PROVEN]. The MSI is the official release asset, SHA-256 `1c984914…` matching the published digest.
     - Run the elevated steps through a `.ps1` with forward-slash paths: `gsudo` called from Git Bash strips backslashes.
   - **Next blocker:** the `usbipd` service crashes at start with `SocketException 10013` binding TCP 3240. `netsh int ipv4 show excludedportrange protocol=tcp` shows **3202–3301 reserved** (WinNAT / Hyper-V dynamic range) [PROVEN: event log + netsh].
   - Proposed fix, pending the user: `net stop winnat`, `sc start usbipd`, `net start winnat`. Optionally reserve 3240 persistently with `netsh int ipv4 add excludedportrange`.

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
