#pragma once

// Test helper: wfb-ng's real rx Aggregator (wfb-ng/src/rx.cpp) fed one radio packet at a time, with every payload it
// hands to the video socket captured. A separate translation unit from the TX side because rx.hpp and TxFrame.h
// should not share one (both pull in wifibroadcast.hpp with their own macros).
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

class RxReplay {
  public:
    // gsKeypair: a wfb-ng gs.key (rx secret key + tx public key).
    RxReplay(const std::string &gsKeypair, uint32_t channelId);
    ~RxReplay();

    // Feeds one wfb packet (as the radio delivers it after the 802.11 header). Returns the payloads the Aggregator
    // released during this call, in order.
    std::vector<std::vector<uint8_t>> feed(const std::vector<uint8_t> &packet);

    uint32_t fecRecovered() const;
    uint32_t lost() const;   // count_p_lost: data slots wfb-ng gave up on

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
