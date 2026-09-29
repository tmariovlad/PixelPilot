#ifndef PIXELPILOT_FREEZE_UNTIL_IDR_H
#define PIXELPILOT_FREEZE_UNTIL_IDR_H

#include <atomic>
#include <cstdint>

// After a lost RTP packet, the frames that follow are predicted from a frame the decoder never got whole, so they show
// smears until the next key frame (GOP 2 s on the air). With this on, every non-key slice is dropped from the loss
// until the next key frame, so the picture holds on the last good frame instead; request_idr_on_loss makes that key
// frame come within ~0.1-0.3 s. A timeout resumes anyway if no key frame comes. Parameter sets, SEI and other non-slice
// NAL units always pass. LatencyExperiments freeze_until_idr; docs/xr/link-envelope.md.
//
// onLoss/admit run on the parsing thread; setEnabled may come from another thread.
class FreezeUntilIdr
{
  public:
    static constexpr int kDefaultTimeoutMs = 1000;

    explicit FreezeUntilIdr(int timeout_ms = kDefaultTimeoutMs) : m_timeout_ms(timeout_ms) {}

    void setEnabled(bool enabled) { m_enabled = enabled; }

    void onLoss(int64_t now_ms)
    {
        if (!m_enabled || m_frozen) return;
        m_frozen   = true;
        m_since_ms = now_ms;
    }

    // False = drop this NAL unit (a non-key slice during a freeze).
    bool admit(int nal_unit_type, bool h265, int64_t now_ms)
    {
        if (!m_enabled)
        {
            m_frozen = false;
            return true;
        }
        if (!m_frozen) return true;
        if (isKeySlice(nal_unit_type, h265) || now_ms - m_since_ms >= m_timeout_ms)
        {
            m_frozen = false;
            return true;
        }
        if (!isSlice(nal_unit_type, h265)) return true;
        m_dropped++;
        return false;
    }

    bool     frozen() const { return m_frozen; }
    uint32_t dropped() const { return m_dropped; }

    // H.264: IDR slice (5). H.265: IRAP pictures (BLA/IDR/CRA, 16-21).
    static bool isKeySlice(int t, bool h265) { return h265 ? (t >= 16 && t <= 21) : t == 5; }
    // H.264: coded slices 1-5. H.265: VCL types 0-9 and IRAP 16-21.
    static bool isSlice(int t, bool h265) { return h265 ? ((t >= 0 && t <= 9) || isKeySlice(t, true)) : (t >= 1 && t <= 5); }

  private:
    const int             m_timeout_ms;
    std::atomic<bool>     m_enabled{false};
    std::atomic<bool>     m_frozen{false};   // read by the UI thread (SignalState HOLD)
    int64_t               m_since_ms = 0;
    std::atomic<uint32_t> m_dropped{0};
};

#endif  // PIXELPILOT_FREEZE_UNTIL_IDR_H
