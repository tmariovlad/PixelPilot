#pragma once

#include <cstdint>
#include <string>

// The per-second logcat budget of the diagnostic probes (PPXR_FECBLK, PPXR_RTPHOLE): at most maxPerSecond lines in
// one CLOCK_MONOTONIC second; the lines over budget are counted, and the first admitted line of a later second
// carries " suppressed=<n>" so nothing is silently lost from the totals. Not thread-safe.
class LineRateLimiter {
  public:
    explicit LineRateLimiter(int maxPerSecond) : max_(maxPerSecond) {}

    // True when a line may be written at tNs; false = counted as suppressed.
    bool admit(int64_t tNs) {
        const int64_t second = tNs / 1'000'000'000LL;
        if (second != second_) {
            second_ = second;
            linesThisSecond_ = 0;
            carry_ += suppressed_;
            suppressed_ = 0;
        }
        if (linesThisSecond_ >= max_) {
            ++suppressed_;
            return false;
        }
        ++linesThisSecond_;
        return true;
    }

    // " suppressed=<n>" for the admitted line when earlier seconds went over budget, else "". Reported once.
    std::string takeSuppressedSuffix() {
        if (carry_ == 0) return "";
        const std::string s = " suppressed=" + std::to_string(carry_);
        carry_ = 0;
        return s;
    }

  private:
    int max_;
    int64_t second_ = -1;
    int linesThisSecond_ = 0;
    int suppressed_ = 0;
    int carry_ = 0;
};
