#pragma once

#include <atomic>
#include <cstdint>
#include <string>

// Which codec the incoming stream carries, and when it changes.
//
// The air unit can switch H.264 <-> H.265 (RTP payload type 96 <-> 97, H26XParser::parse_rtp_stream) while the app
// runs, e.g. from the headset's codec menu. A MediaCodec cannot change its MIME type, so VideoDecoder rebuilds its
// decoders on the change, on the same output surface (the XR swapchain stays), and H26XParser drops any half-built
// NALU of the old codec. Before this, a switch needed an app restart (the old "TODO" in VideoDecoder::interpretNALU).
//
// Owned by one feeding thread (changed/reset); switches() and summary() may be read from the stats thread.
class CodecSwitch
{
  public:
    // Once per NALU (or RTP packet). True on the first one of a different codec; never on the very first NALU.
    bool changed(bool h265)
    {
        const State now  = h265 ? State::H265 : State::H264;
        const State prev = state_.exchange(now);
        if (prev == State::Unknown || prev == now) return false;
        ++switches_;
        return true;
    }

    // Forget the codec (the next NALU is not a change); the switch count stays.
    void reset() { state_ = State::Unknown; }

    bool     known() const { return state_ != State::Unknown; }
    bool     isH265() const { return state_ == State::H265; }
    uint32_t switches() const { return switches_; }

    // " | codec switch N (now H.26x)", empty until the first switch; for the decoder summary line.
    std::string summary() const
    {
        const auto n = switches_.load();
        if (n == 0) return "";
        return " | codec switch " + std::to_string(n) + (isH265() ? " (now H.265)" : " (now H.264)");
    }

  private:
    enum class State : uint8_t { Unknown, H264, H265 };
    std::atomic<State>    state_{State::Unknown};
    std::atomic<uint32_t> switches_{0};
};
