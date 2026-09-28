#ifndef PIXELPILOT_IDR_REQUEST_POLICY_H
#define PIXELPILOT_IDR_REQUEST_POLICY_H

#include <algorithm>
#include <cstdint>

// When a key-frame request may go to the air unit: at most one per interval. A loss inside the interval waits for its
// end rather than being dropped (the key frame asked for earlier may predate that loss). waybeam rate-limits on its
// side as well (idr_rate_limit, venc_api.c).
class IdrRequestPolicy
{
  public:
    static constexpr int kDefaultMinIntervalMs = 200;

    explicit IdrRequestPolicy(int min_interval_ms = kDefaultMinIntervalMs) : m_interval_ms(min_interval_ms) {}

    // Milliseconds until a pending request may be sent, at now_ms (0 = now).
    int64_t delayMs(int64_t now_ms) const
    {
        return m_last_ms < 0 ? 0 : std::max<int64_t>(0, m_last_ms + m_interval_ms - now_ms);
    }

    void sent(int64_t now_ms) { m_last_ms = now_ms; }

    // A new interval for later requests; <= 0 keeps the current one.
    void setIntervalMs(int ms)
    {
        if (ms > 0) m_interval_ms = ms;
    }

  private:
    int       m_interval_ms;
    int64_t   m_last_ms = -1;
};

#endif  // PIXELPILOT_IDR_REQUEST_POLICY_H
