#pragma once

#include <cstdint>
#include <mutex>
#include <unordered_map>

// RX rate of the video packets over one stats window, for the Stats page: the most frequent (rate code, bandwidth,
// STBC, LDPC, short GI) and its share. The rate code is devourer's rx_pkt_attrib::data_rate, raw (Realtek descriptor
// rate: 7-bit on Jaguar1 / RTL8812AU, 9-bit halmac on newer chips); decoding it into MCS/NSS is the app's job
// (stats.RxRate). Written by the RX thread, taken by the stats thread.
class RxRateHistogram {
  public:
    struct Top {
        uint16_t rateCode = 0;
        uint8_t bw = 0;  // devourer rx_pkt_attrib::bw (0 = 20 MHz)
        uint8_t stbc = 0, ldpc = 0, sgi = 0;
        uint32_t packets = 0;  // packets at this rate
        uint32_t total = 0;    // packets in the window
    };

    void add(uint16_t rateCode, uint8_t bw, uint8_t stbc, uint8_t ldpc, uint8_t sgi) {
        const uint32_t key = static_cast<uint32_t>(rateCode) | static_cast<uint32_t>(bw & 0x0F) << 16 |
                             static_cast<uint32_t>(stbc ? 1 : 0) << 20 | static_cast<uint32_t>(ldpc ? 1 : 0) << 21 |
                             static_cast<uint32_t>(sgi ? 1 : 0) << 22;
        std::lock_guard<std::mutex> lock(mutex_);
        ++counts_[key];
        ++total_;
    }

    // The window's most frequent rate; starts a new window.
    Top take() {
        std::lock_guard<std::mutex> lock(mutex_);
        Top t;
        uint32_t bestKey = 0;
        for (const auto &kv : counts_) {
            if (kv.second > t.packets) {
                t.packets = kv.second;
                bestKey = kv.first;
            }
        }
        t.total = total_;
        t.rateCode = static_cast<uint16_t>(bestKey & 0xFFFF);
        t.bw = static_cast<uint8_t>((bestKey >> 16) & 0x0F);
        t.stbc = static_cast<uint8_t>((bestKey >> 20) & 1);
        t.ldpc = static_cast<uint8_t>((bestKey >> 21) & 1);
        t.sgi = static_cast<uint8_t>((bestKey >> 22) & 1);
        counts_.clear();
        total_ = 0;
        return t;
    }

  private:
    std::mutex mutex_;
    std::unordered_map<uint32_t, uint32_t> counts_;
    uint32_t total_ = 0;
};
