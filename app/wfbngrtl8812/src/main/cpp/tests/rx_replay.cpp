#include "rx_replay.h"

extern "C" {
#include "wfb-ng/src/zfex.h"
}
#include "wfb-ng/src/rx.hpp"

namespace {
class CapturingAggregator : public Aggregator {
  public:
    CapturingAggregator(const std::string &keypair, uint32_t channelId) : Aggregator(keypair, 0, channelId) {}
    std::vector<std::vector<uint8_t>> out;

  protected:
    void send_to_socket(const uint8_t *payload, uint16_t size) override { out.emplace_back(payload, payload + size); }
};
}  // namespace

struct RxReplay::Impl {
    CapturingAggregator agg;
    Impl(const std::string &k, uint32_t c) : agg(k, c) {}
};

RxReplay::RxReplay(const std::string &gsKeypair, uint32_t channelId) : impl_(new Impl(gsKeypair, channelId)) {}

RxReplay::~RxReplay() = default;

std::vector<std::vector<uint8_t>> RxReplay::feed(const std::vector<uint8_t> &packet) {
    int8_t rssi[4] = {-40, -40, 1, 1};
    int8_t noise[4] = {1, 1, 1, 1};
    uint8_t antenna[4] = {1, 1, 1, 1};
    impl_->agg.out.clear();
    impl_->agg.process_packet(packet.data(), packet.size(), 0, antenna, rssi, noise, 0, 0, 0, nullptr);
    return impl_->agg.out;
}

uint32_t RxReplay::fecRecovered() const { return impl_->agg.count_p_fec_recovered; }
