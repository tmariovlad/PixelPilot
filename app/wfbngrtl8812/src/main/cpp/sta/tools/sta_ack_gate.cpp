// sta_ack_gate — go/no-go gate W0 for devourer station mode (docs/xr/research/2026-09-27-devourer-station-scope.md §8).
//
// Question: does the RTL8812AU's hardware ACK responder (IRtlDevice::SetAckResponder) acknowledge the
// frames a real AP (the OpenIPC air unit's hostapd on an RTL8822EU) sends to our station MAC? devourer
// documents the 8812AU as a degraded responder against another devourer (97 % delivery at ~7 retries,
// devourer docs/scheduled-mac.md:182-185); it was never tried against a third-party AP.
//
// Method: open-auth + associate to the AP (no crypto; WPA2 needs only the RSN element in the request),
// then stay silent. hostapd then retries EAPOL msg1 and finally deauthenticates, and we start over.
// Every frame the AP addresses to us is logged by (class, sequence number): how many copies arrive
// and whether the first copy already has the Retry bit. With a working ACK each MPDU arrives once,
// Retry = 0; without it the AP's MAC retransmits it (Retry = 1) up to its retry limit.
// Run with GATE_ACK=1 and GATE_ACK=0 alternately, N >= 2 each, the setup physically unchanged.
//
// Env: DEVOURER_VID/DEVOURER_PID (default 0bda:8812), DEVOURER_CHANNEL (157), GATE_SSID (OpenIPC),
//      GATE_STA (02:42:75:05:d6:10), GATE_ACK (1), GATE_HT / GATE_WMM (1), plus devourer's DEVOURER_* knobs.
// Usage: sta_ack_gate [seconds=60]   (as root; the air unit's AP must have no other client: max_num_sta=1)
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <libusb.h>

#include "DeviceConfig.h"
#include "RadiotapBuilder.h"
#include "RxPacket.h"
#include "SelectedChannel.h"
#include "TxMode.h"
#include "UsbOpen.h"
#include "WiFiDriver.h"
#include "env_config.h"
#include "logger.h"

#include "../StaFrames.h"

using Clock = std::chrono::steady_clock;

namespace {

const char* env_or(const char* name, const char* def) {
    const char* v = std::getenv(name);
    return v && *v ? v : def;
}

std::string mac_str(const sta::Mac& m) {
    char b[18];
    std::snprintf(b, sizeof b, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
    return b;
}

// What an AP-to-us frame is, for the report.
const char* frame_class(const sta::FrameHeader& h) {
    if (h.type == sta::FrameType::Data)
        return h.subtype & 0x8 ? "qos-data" : "data";
    switch (h.subtype) {
        case sta::mgmt::kAuth: return "auth-resp";
        case sta::mgmt::kAssocResp: return "assoc-resp";
        case sta::mgmt::kDeauth: return "deauth";
        case sta::mgmt::kDisassoc: return "disassoc";
        case sta::mgmt::kAction: return "action";
        case sta::mgmt::kProbeResp: return "probe-resp";
        default: return "mgmt-other";
    }
}

struct MpduStat {
    int copies = 0;
    bool first_retry = false;
};

struct Shared {
    std::mutex mu;
    sta::Mac sta{};
    std::string ssid;
    std::atomic<bool> have_bss{false};
    sta::Mac bssid{};
    int beacons = 0;
    int rssi_sum = 0;
    // (class, seq, cycle) -> stats; the cycle keeps a new association's frames apart from the last one's
    std::map<std::tuple<std::string, int, int>, MpduStat> mpdus;
    std::atomic<int> cycle{0};
    std::atomic<bool> auth_ok{false}, assoc_ok{false}, kicked{false};
    std::atomic<int> auth_status{-1}, assoc_status{-1};
    int logged = 0;
};

Shared g;

void on_rx(const Packet& p) {
    if (p.RxAtrib.crc_err)
        return;
    const uint8_t* f = p.Data.data();
    size_t len = sta::payload_len(p.Data.size());
    auto h = sta::parse_header(f, len);
    if (!h)
        return;
    if (!g.have_bss) {
        if (auto b = sta::parse_bss(f, len); b && b->ssid == g.ssid) {
            std::lock_guard<std::mutex> lk(g.mu);
            g.bssid = h->a3;
            g.have_bss = true;
            std::fprintf(stderr, "found %s bssid %s ch %d\n", g.ssid.c_str(), mac_str(g.bssid).c_str(), b->channel);
        }
        return;
    }
    std::lock_guard<std::mutex> lk(g.mu);
    if (h->a2 == g.bssid && h->type == sta::FrameType::Mgmt && h->subtype == sta::mgmt::kBeacon) {
        g.beacons++;
        g.rssi_sum += p.RxAtrib.rssi[0];
        return;
    }
    if (h->a1 != g.sta || h->a2 != g.bssid)
        return;
    const char* cls = frame_class(*h);
    auto& s = g.mpdus[{cls, h->seq, g.cycle.load()}];
    if (s.copies++ == 0)
        s.first_retry = h->retry;
    if (g.logged < 40) {
        g.logged++;
        std::fprintf(stderr, "  rx %-10s seq %4u retry %d rssi %u cycle %d\n", cls, h->seq, h->retry,
                     p.RxAtrib.rssi[0], g.cycle.load());
    }
    if (auto st = sta::response_status(f, len)) {
        if (h->subtype == sta::mgmt::kAuth) {
            g.auth_status = *st;
            g.auth_ok = *st == 0;
        } else {
            g.assoc_status = *st;
            g.assoc_ok = *st == 0;
        }
    }
    if (h->type == sta::FrameType::Mgmt && (h->subtype == sta::mgmt::kDeauth || h->subtype == sta::mgmt::kDisassoc))
        g.kicked = true;
}

void report(bool ack) {
    std::lock_guard<std::mutex> lk(g.mu);
    struct Agg { int uniq = 0, copies = 0, first_retry = 0, multi = 0; };
    std::map<std::string, Agg> by;
    Agg all;
    for (auto& [k, s] : g.mpdus) {
        for (Agg* a : {&by[std::get<0>(k)], &all}) {
            a->uniq++;
            a->copies += s.copies;
            a->first_retry += s.first_retry;
            a->multi += s.copies > 1;
        }
    }
    std::printf("GATE ack=%d cycles=%d beacons=%d mean_rssi_raw=%.1f auth_status=%d assoc_status=%d\n", ack,
                g.cycle.load(), g.beacons, g.beacons ? double(g.rssi_sum) / g.beacons : 0.0, g.auth_status.load(),
                g.assoc_status.load());
    auto line = [](const std::string& name, const Agg& a) {
        if (!a.uniq)
            return;
        std::printf("  %-10s mpdus=%4d copies=%5d copies/mpdu=%.2f first_copy_retry=%5.1f%% repeated=%5.1f%%\n",
                    name.c_str(), a.uniq, a.copies, double(a.copies) / a.uniq, 100.0 * a.first_retry / a.uniq,
                    100.0 * a.multi / a.uniq);
    };
    for (auto& [n, a] : by)
        line(n, a);
    line("ALL", all);
}

}  // namespace

int main(int argc, char** argv) {
    int secs = argc > 1 ? std::atoi(argv[1]) : 60;
    int chan = std::atoi(env_or("DEVOURER_CHANNEL", "157"));
    bool ack = std::atoi(env_or("GATE_ACK", "1")) != 0;
    g.ssid = env_or("GATE_SSID", "OpenIPC");
    auto sm = devourer::parse_mac(env_or("GATE_STA", "02:42:75:05:d6:10"));
    if (!sm || (sm->bytes[0] & 1)) {
        std::fprintf(stderr, "GATE_STA must be a unicast MAC\n");
        return 2;
    }
    g.sta = sm->bytes;
    sta::StaCaps caps;
    caps.channel = chan;
    caps.ht = std::atoi(env_or("GATE_HT", "1")) != 0;
    caps.wmm = std::atoi(env_or("GATE_WMM", "1")) != 0;

    auto logger = std::make_shared<Logger>();
    apply_logging_env(*logger);
    libusb_context* ctx = nullptr;
    libusb_init(&ctx);
    uint16_t vid = static_cast<uint16_t>(std::strtoul(env_or("DEVOURER_VID", "0x0bda"), nullptr, 0));
    uint16_t pid = static_cast<uint16_t>(std::strtoul(env_or("DEVOURER_PID", "0x8812"), nullptr, 0));
    auto* h = libusb_open_device_with_vid_pid(ctx, vid, pid);
    if (!h) {
        std::fprintf(stderr, "open %04x:%04x failed\n", vid, pid);
        return 1;
    }
    std::shared_ptr<devourer::UsbDeviceLock> lk;
    if (devourer::claim_interface_then_reset(h, devourer::find_wifi_interface(h), logger, true, lk) != 0)
        return 1;
    WiFiDriver wifi(logger);
    auto dev = wifi.CreateRtlDevice(h, ctx, lk, devourer_config_from_env());
    if (!dev)
        return 1;
    dev->InitWrite(SelectedChannel{static_cast<uint8_t>(chan), 0, CHANNEL_WIDTH_20});
    if (ack && !dev->SetAckResponder(devourer::MacAddr{g.sta})) {
        std::fprintf(stderr, "SetAckResponder not supported on this adapter\n");
        return 1;
    }
    auto rt = devourer::build_stream_radiotap(devourer::parse_tx_mode_str("6M"));
    auto send = [&](const std::vector<uint8_t>& mpdu) {
        std::vector<uint8_t> fr(rt);
        fr.insert(fr.end(), mpdu.begin(), mpdu.end());
        return dev->send_packet(fr.data(), fr.size());
    };
    std::thread rx([&] { dev->StartRxLoop(on_rx); });
    std::fprintf(stderr, "sta_ack_gate: ch %d sta %s ack=%d ht=%d wmm=%d, %d s\n", chan, mac_str(g.sta).c_str(), ack,
                 caps.ht, caps.wmm, secs);

    const auto end = Clock::now() + std::chrono::seconds(secs);
    const auto step = std::chrono::milliseconds(300);
    enum { Scan, Auth, Assoc, Hold } phase = Scan;
    int tries = 0;
    auto hold_since = Clock::now();
    while (Clock::now() < end) {
        switch (phase) {
            case Scan:
                if (g.have_bss) {
                    phase = Auth;
                    tries = 0;
                }
                break;
            case Auth:
                if (g.auth_ok) { phase = Assoc; tries = 0; break; }
                if (tries++ < 20) send(sta::build_auth_open(g.sta, g.bssid));
                break;
            case Assoc:
                if (g.assoc_ok) { phase = Hold; hold_since = Clock::now(); break; }
                if (tries++ < 20) send(sta::build_assoc_req(g.sta, g.bssid, g.ssid, caps));
                break;
            case Hold:   // silent: hostapd retries EAPOL msg1, then deauths (4-way timeout)
                if (g.kicked || Clock::now() - hold_since > std::chrono::seconds(10)) {
                    std::lock_guard<std::mutex> l(g.mu);
                    g.cycle++;
                    g.kicked = g.auth_ok = g.assoc_ok = false;
                    phase = Auth;
                    tries = 0;
                }
                break;
        }
        std::this_thread::sleep_for(step);
    }
    if (g.have_bss)
        send(sta::build_deauth(g.sta, g.bssid, 3));   // leaving
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    report(ack);
    std::fflush(stdout);
    _exit(0);
}
