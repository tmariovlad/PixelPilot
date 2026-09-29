#pragma once

#include <android/log.h>

#include <string>

#include "RtpHoleProbe.h"
#include "WfbPktLostTap.h"

extern "C" {
#include "wfb-ng/src/zfex.h"   // rx.hpp uses fec_t without including it
}
#include "wfb-ng/src/rx.hpp"

// The video channel's aggregator: wfb-ng's AggregatorUDPv4 unchanged, plus a look at every payload it delivers
// (send_to_socket is wfb-ng's virtual output hook, called from Aggregator::send_packet in wfb slot order, FEC-recovered
// fragments included) for RtpHoleProbe, with the slots wfb-ng reported lost just before it (WfbPktLostTap).
// Runs on the RX thread under the link's agg_mutex, like the aggregator itself.
class RtpHoleAggregator : public AggregatorUDPv4 {
  public:
    RtpHoleAggregator(const std::string &client_addr, int client_port, const std::string &keypair, uint64_t epoch,
                      uint32_t channel_id, int snd_buf_size, RtpHoleProbe &probe)
        : AggregatorUDPv4(client_addr, client_port, keypair, epoch, channel_id, snd_buf_size), probe_(probe) {}

    // The received frame's CLOCK_MONOTONIC time, set before each process_packet: the payloads it releases are
    // stamped with it (the same clock as PPXR_FECBLK's t_mono_ms).
    void setFrameTime(int64_t tNs) { frameNs_ = tNs; }

  protected:
    void send_to_socket(const uint8_t *payload, uint16_t packet_size) override {
        probe_.onSlotsLost(WfbPktLostTap::take());
        const std::string line = probe_.onDelivered(frameNs_, payload, packet_size);
        if (!line.empty()) __android_log_print(ANDROID_LOG_INFO, "PPXR_RTPHOLE", "%s", line.c_str());
        AggregatorUDPv4::send_to_socket(payload, packet_size);
    }

  private:
    RtpHoleProbe &probe_;
    int64_t frameNs_ = 0;
};
