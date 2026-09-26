#include "StaFrames.h"

#include <cstring>

namespace sta {
namespace {

constexpr size_t kHdr = 24;

Mac mac_at(const uint8_t* p) {
    Mac m;
    std::memcpy(m.data(), p, 6);
    return m;
}

// Management header: A1 = DA = BSSID, A2 = SA = us, A3 = BSSID. Duration and sequence are left 0; the
// hardware fills the sequence number on injection.
std::vector<uint8_t> mgmt_header(uint8_t subtype, const Mac& sta, const Mac& bssid) {
    std::vector<uint8_t> f(kHdr, 0);
    f[0] = static_cast<uint8_t>(subtype << 4);
    std::memcpy(&f[4], bssid.data(), 6);
    std::memcpy(&f[10], sta.data(), 6);
    std::memcpy(&f[16], bssid.data(), 6);
    return f;
}

void put_le16(std::vector<uint8_t>& f, uint16_t v) {
    f.push_back(static_cast<uint8_t>(v & 0xff));
    f.push_back(static_cast<uint8_t>(v >> 8));
}

void put_ie(std::vector<uint8_t>& f, uint8_t id, std::initializer_list<uint8_t> body) {
    f.push_back(id);
    f.push_back(static_cast<uint8_t>(body.size()));
    f.insert(f.end(), body);
}

}  // namespace

std::optional<FrameHeader> parse_header(const uint8_t* f, size_t len) {
    if (len < kHdr)
        return std::nullopt;
    FrameHeader h;
    h.type = static_cast<FrameType>((f[0] >> 2) & 0x3);
    if (h.type != FrameType::Mgmt && h.type != FrameType::Data)
        return std::nullopt;
    h.subtype = f[0] >> 4;
    h.to_ds = f[1] & 0x01;
    h.from_ds = f[1] & 0x02;
    h.retry = f[1] & 0x08;
    h.protected_frame = f[1] & 0x40;
    h.a1 = mac_at(f + 4);
    h.a2 = mac_at(f + 10);
    h.a3 = mac_at(f + 16);
    h.seq = static_cast<uint16_t>((f[22] | (f[23] << 8)) >> 4);
    return h;
}

std::optional<BssInfo> parse_bss(const uint8_t* f, size_t len) {
    auto h = parse_header(f, len);
    if (!h || h->type != FrameType::Mgmt || (h->subtype != mgmt::kBeacon && h->subtype != mgmt::kProbeResp))
        return std::nullopt;
    constexpr size_t kIes = kHdr + 12;   // timestamp 8, beacon interval 2, capability 2
    if (len < kIes)
        return std::nullopt;
    BssInfo b;
    bool have_ssid = false;
    for (size_t i = kIes; i + 2 <= len;) {
        uint8_t id = f[i], l = f[i + 1];
        if (i + 2 + l > len)
            return std::nullopt;
        if (id == 0) {
            b.ssid.assign(reinterpret_cast<const char*>(f + i + 2), l);
            have_ssid = true;
        } else if (id == 3 && l == 1) {
            b.channel = f[i + 2];
        }
        i += 2 + l;
    }
    if (!have_ssid)
        return std::nullopt;
    return b;
}

std::optional<uint16_t> response_status(const uint8_t* f, size_t len) {
    auto h = parse_header(f, len);
    if (!h || h->type != FrameType::Mgmt)
        return std::nullopt;
    size_t off;
    if (h->subtype == mgmt::kAuth)
        off = kHdr + 4;   // algorithm 2, transaction sequence 2, status 2
    else if (h->subtype == mgmt::kAssocResp)
        off = kHdr + 2;   // capability 2, status 2, AID 2
    else
        return std::nullopt;
    if (len < off + 2)
        return std::nullopt;
    return static_cast<uint16_t>(f[off] | (f[off + 1] << 8));
}

std::vector<uint8_t> build_auth_open(const Mac& sta, const Mac& bssid) {
    auto f = mgmt_header(mgmt::kAuth, sta, bssid);
    put_le16(f, 0);   // Open System
    put_le16(f, 1);   // transaction sequence 1
    put_le16(f, 0);   // status
    return f;
}

std::vector<uint8_t> build_assoc_req(const Mac& sta, const Mac& bssid, const std::string& ssid, const StaCaps& caps) {
    auto f = mgmt_header(mgmt::kAssocReq, sta, bssid);
    put_le16(f, caps.rsn ? 0x0011 : 0x0001);   // ESS (+ Privacy for an RSN BSS)
    put_le16(f, 10);                           // listen interval (beacons)
    f.push_back(0);
    f.push_back(static_cast<uint8_t>(ssid.size()));
    f.insert(f.end(), ssid.begin(), ssid.end());
    if (caps.channel <= 14)   // CCK + OFDM, basic 1/2/5.5/11
        put_ie(f, 1, {0x82, 0x84, 0x8b, 0x96, 0x24, 0x30, 0x48, 0x6c});
    else                      // OFDM only; CCK rates do not exist on 5 GHz
        put_ie(f, 1, {0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c});
    if (caps.rsn)   // version 1, group CCMP, 1 pairwise CCMP, 1 AKM PSK, capabilities 0
        put_ie(f, 48, {0x01, 0x00, 0x00, 0x0f, 0xac, 0x04, 0x01, 0x00, 0x00, 0x0f, 0xac, 0x04,
                       0x01, 0x00, 0x00, 0x0f, 0xac, 0x02, 0x00, 0x00});
    if (caps.ht)
        // HT Capabilities (26 bytes): info 0x002c = 20 MHz only, SM power save disabled, SGI20;
        // A-MPDU parameters 0; RX MCS 0-15; everything else 0.
        put_ie(f, 45, {0x2c, 0x00, 0x00, 0xff, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                       0x00, 0x00, 0, 0, 0, 0, 0x00});
    if (caps.wmm)   // WMM information element: OUI 00:50:f2, type 2, subtype 0, version 1, QoS info 0
        put_ie(f, 221, {0x00, 0x50, 0xf2, 0x02, 0x00, 0x01, 0x00});
    return f;
}

std::vector<uint8_t> build_deauth(const Mac& sta, const Mac& bssid, uint16_t reason) {
    auto f = mgmt_header(mgmt::kDeauth, sta, bssid);
    put_le16(f, reason);
    return f;
}

}  // namespace sta
