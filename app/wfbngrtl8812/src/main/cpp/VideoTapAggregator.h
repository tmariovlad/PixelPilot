#pragma once

#include <android/log.h>

#include <string>

#include "ReleaseProbe.h"
#include "RtpHoleProbe.h"
#include "WfbPktLostTap.h"

extern "C" {
#include "wfb-ng/src/zfex.h"   // rx.hpp uses fec_t without including it
}
#include "wfb-ng/src/rx.hpp"

// The video channel's aggregator: wfb-ng's AggregatorUDPv4 unchanged, plus a look at every payload it delivers
// (send_to_socket is wfb-ng's virtual output hook, called from Aggregator::send_packet in wfb slot order, FEC-recovered
// fragments included) for two probes (docs/xr/fec-block-probe.md §6, §7):
// - RtpHoleProbe (PPXR_RTPHOLE): RTP holes, with the slots wfb-ng reported lost just before them (WfbPktLostTap);
// - ReleaseProbe (PPXR_RELEASE): what each process_packet call released, bracketed by beginCall() / endCall().
// Runs on the RX thread under the link's agg_mutex, like the aggregator itself.
class VideoTapAggregator : public AggregatorUDPv4 {
  public:
    VideoTapAggregator(const std::string &client_addr, int client_port, const std::string &keypair, uint64_t epoch,
                       uint32_t channel_id, int snd_buf_size, RtpHoleProbe &holes)
        : AggregatorUDPv4(client_addr, client_port, keypair, epoch, channel_id, snd_buf_size), holes_(holes) {}

    // Before each process_packet: the received frame's CLOCK_MONOTONIC time, which stamps what the call releases
    // (the same clock as PPXR_FECBLK's t_mono_ms).
    void beginCall(int64_t tNs) {
        frameNs_ = tNs;
        releases_.begin(tNs, count_p_fec_recovered);
    }

    // After each process_packet.
    void endCall() {
        const std::string line = releases_.end(count_p_fec_recovered);
        if (!line.empty()) __android_log_print(ANDROID_LOG_INFO, "PPXR_RELEASE", "%s", line.c_str());
    }

  protected:
    void send_to_socket(const uint8_t *payload, uint16_t packet_size) override {
        holes_.onSlotsLost(WfbPktLostTap::take());
        const std::string line = holes_.onDelivered(frameNs_, payload, packet_size);
        if (!line.empty()) __android_log_print(ANDROID_LOG_INFO, "PPXR_RTPHOLE", "%s", line.c_str());
        releases_.onDelivered(payload, packet_size);
        AggregatorUDPv4::send_to_socket(payload, packet_size);
    }

  private:
    RtpHoleProbe &holes_;
    ReleaseProbe releases_;
    int64_t frameNs_ = 0;
};
