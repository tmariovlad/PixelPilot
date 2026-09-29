#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <string>

// When VideoDecoder rebuilds its decoder after a failure (audit X23, docs/xr/research/2026-09-27-xr-ux-audit.md).
//
// (a) configure failure: the saved SPS/PPS stayed in the KeyFrameFinder, so every following NALU tried again and
//     created (and failed) a MediaCodec per NALU. Now a failed attempt forgets the key frames, so the next attempt
//     comes with the next SPS/PPS (the next key frame).
// (b) a codec that errors out ends its output thread while `configured` stayed true, and the picture froze until
//     the XR session cycled. The output thread now flags the failure; the feeding thread sees it and rebuilds the
//     decoder at the next key frame.
// Counters are shown in the decoder summary line. Thread-safe: the output thread flags, the feed thread decides.
class DecoderRecovery {
  public:
    // Feed thread, after configuring from the saved key frames. True: forget them and wait for the next ones.
    bool configureFailed(bool anyConfigured, bool anyWindow) {
        if (anyConfigured || !anyWindow) return false;   // no window yet is not a failure
        ++configureFailures_;
        return true;
    }

    // Output thread: its loop ended while the codec was still in place (an error, not a release).
    void outputFailed(int idx) { outputFailed_[idx] = true; }

    // Feed thread, before feeding a configured decoder. True: release it and rebuild at the next key frame.
    bool shouldRebuild(int idx, bool configured) {
        if (!configured || !outputFailed_[idx].exchange(false)) return false;
        ++rebuilds_;
        return true;
    }

    // A fresh decoder starts clean (a release also ends the output loop, which may have flagged it).
    void configured(int idx) { outputFailed_[idx] = false; }

    // Cumulative, for the health log (PPXR_EVENT DECODER_REBUILD); safe from the stats thread.
    uint32_t rebuilds() const { return rebuilds_; }
    uint32_t configureFailures() const { return configureFailures_; }

    // " | cfg-fail N | rebuilt M", empty while nothing went wrong.
    std::string summary() const {
        std::string s;
        if (const auto f = configureFailures_.load()) s += " | cfg-fail " + std::to_string(f);
        if (const auto r = rebuilds_.load()) s += " | rebuilt " + std::to_string(r);
        return s;
    }

  private:
    std::array<std::atomic<bool>, 2> outputFailed_{};
    std::atomic<uint32_t> configureFailures_{0};
    std::atomic<uint32_t> rebuilds_{0};
};
