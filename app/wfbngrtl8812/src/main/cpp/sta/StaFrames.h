// StaFrames — 802.11 frame builders and parsers for a Wi-Fi *station* (client) on top of devourer.
//
// Pure byte handling, no devourer or libusb dependency, so it runs in host unit tests and is shared by
// the go/no-go harness (tools/sta_ack_gate.cpp) and, later, the app's station session. Scope and plan:
// docs/xr/research/2026-09-27-devourer-station-scope.md.
//
// Frames here carry no FCS; devourer's RX Packet::Data keeps the 4-byte FCS, so strip it first
// (payload_len()).
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace sta {

using Mac = std::array<uint8_t, 6>;

// Frame control, IEEE 802.11-2020 9.2.4.1.
enum class FrameType : uint8_t { Mgmt = 0, Ctrl = 1, Data = 2, Ext = 3 };
namespace mgmt {
constexpr uint8_t kAssocReq = 0, kAssocResp = 1, kProbeResp = 5, kBeacon = 8, kDisassoc = 10, kAuth = 11,
                  kDeauth = 12, kAction = 13;
}

struct FrameHeader {
    FrameType type = FrameType::Mgmt;
    uint8_t subtype = 0;
    bool to_ds = false, from_ds = false, retry = false, protected_frame = false;
    Mac a1{}, a2{}, a3{};
    uint16_t seq = 0;   // sequence number (12 bits), fragment number dropped
};

// Parses the 3-address header of a management or data frame (>= 24 bytes). Control frames and short
// buffers return nullopt.
std::optional<FrameHeader> parse_header(const uint8_t* f, size_t len);

// Length of a devourer RX frame without its trailing 4-byte FCS (0 if shorter than that).
inline size_t payload_len(size_t rx_len) { return rx_len >= 4 ? rx_len - 4 : 0; }

// SSID and DS channel from a beacon or probe response (nullopt if it is not one or is malformed).
struct BssInfo {
    std::string ssid;
    int channel = -1;   // from the DS Parameter Set element; -1 if absent
};
std::optional<BssInfo> parse_bss(const uint8_t* f, size_t len);

// Status code of an authentication or association response addressed to us (nullopt otherwise).
std::optional<uint16_t> response_status(const uint8_t* f, size_t len);

// What the station advertises in its association request.
struct StaCaps {
    int channel = 157;   // selects the 5 GHz (OFDM-only) or 2.4 GHz supported-rates set
    bool rsn = true;     // WPA2-PSK / CCMP RSN element
    bool ht = true;      // HT Capabilities, 20 MHz only, no aggregation promised
    bool wmm = true;     // WMM information element (QoS; an AP needs it before it uses HT)
};

std::vector<uint8_t> build_auth_open(const Mac& sta, const Mac& bssid);
std::vector<uint8_t> build_assoc_req(const Mac& sta, const Mac& bssid, const std::string& ssid, const StaCaps& caps);
std::vector<uint8_t> build_deauth(const Mac& sta, const Mac& bssid, uint16_t reason);

}  // namespace sta
