#pragma once
// Quest-side RX loss attribution for the link-25mbit audit (T6): separates frames the radio received with a bad
// FCS/ICV (RF bit errors, visible only with devourer's keep_corrupted on) from host-side USB ring trouble (the
// devourer RX ring telemetry: starvation, host drops). Both are summed per wfb stats window (~300 ms) and written as
// ppxr_rx_* / ppxr_usb_* trace counters next to the ppxr_wfb_* ones. Tests: tests/RxDiag_test.cpp.
#include <atomic>
#include <cstdint>
#include <mutex>

#include "devourer/src/RxRingStats.h"

class RxDiag {
public:
    // One stats window. crc_err / icv_err / clean count the frames seen in the window (only when keep_corrupted is
    // on; a corrupted frame can carry both flags). The ring values are present only if at least one ring snapshot
    // arrived in the window: completions / empties / dropped / resubmit_fail are deltas of devourer's cumulative
    // counters, min_armed the lowest armed-URB depth, cb_max_us the worst inline consume, qdepth_max the largest
    // spsc backlog.
    struct Window {
        uint32_t crc_err = 0;
        uint32_t icv_err = 0;
        uint32_t clean = 0;
        bool ring_valid = false;
        uint64_t completions = 0;
        uint64_t empties = 0;
        uint64_t dropped = 0;
        uint64_t resubmit_fail = 0;
        int min_armed = 0;
        long long cb_max_us = 0;
        long long qdepth_max = 0;
    };

    // RX thread, per frame. Returns whether the frame should go on to wfb-ng: a frame with a bad FCS or ICV is
    // counted and dropped here, so every downstream counter means the same as with keep_corrupted off.
    bool on_frame(bool crc_err, bool icv_err) {
        if (crc_err) m_crc.fetch_add(1, std::memory_order_relaxed);
        if (icv_err) m_icv.fetch_add(1, std::memory_order_relaxed);
        if (crc_err || icv_err) return false;
        m_clean.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    // devourer RX pump thread, once per ring telemetry window (DeviceConfig::Rx::on_ring).
    void on_ring(const devourer::RxRingStats &s) {
        std::lock_guard<std::mutex> lock(m_mu);
        if (!m_have) {
            m_min_armed = s.min_armed;
            m_cb_max_us = s.cb_max_us;
            m_qdepth_max = s.qdepth;
        } else {
            if (s.min_armed < m_min_armed) m_min_armed = s.min_armed;
            if (s.cb_max_us > m_cb_max_us) m_cb_max_us = s.cb_max_us;
            if (s.qdepth > m_qdepth_max) m_qdepth_max = s.qdepth;
        }
        m_have = true;
        m_last = s;
    }

    // Stats thread, once per window: read the window and start the next one.
    Window take() {
        Window w;
        w.crc_err = m_crc.exchange(0, std::memory_order_relaxed);
        w.icv_err = m_icv.exchange(0, std::memory_order_relaxed);
        w.clean = m_clean.exchange(0, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(m_mu);
        if (m_have) {
            w.ring_valid = true;
            w.completions = m_last.completions - m_prev.completions;
            w.empties = m_last.empties - m_prev.empties;
            w.dropped = m_last.dropped - m_prev.dropped;
            w.resubmit_fail = m_last.resubmit_fail - m_prev.resubmit_fail;
            w.min_armed = m_min_armed;
            w.cb_max_us = m_cb_max_us;
            w.qdepth_max = m_qdepth_max;
            m_prev = m_last;
            m_have = false;
        }
        return w;
    }

    // Writes one window as trace counters; the ring counters only when a ring snapshot arrived in the window.
    // Sink: void(const char *name, long long value) — ATrace_setCounter in the app, a map in tests.
    template <class Sink>
    static void emit(const Window &w, Sink &&sink) {
        sink("ppxr_rx_crc_err", w.crc_err);
        sink("ppxr_rx_icv_err", w.icv_err);
        sink("ppxr_rx_clean", w.clean);
        if (!w.ring_valid) return;
        sink("ppxr_usb_completions", static_cast<long long>(w.completions));
        sink("ppxr_usb_empties", static_cast<long long>(w.empties));
        sink("ppxr_usb_dropped", static_cast<long long>(w.dropped));
        sink("ppxr_usb_resubmit_fail", static_cast<long long>(w.resubmit_fail));
        sink("ppxr_usb_min_armed", w.min_armed);
        sink("ppxr_usb_cb_max_us", w.cb_max_us);
        sink("ppxr_usb_qdepth", w.qdepth_max);
    }

private:
    std::atomic<uint32_t> m_crc{0};
    std::atomic<uint32_t> m_icv{0};
    std::atomic<uint32_t> m_clean{0};
    std::mutex m_mu;
    bool m_have = false;
    devourer::RxRingStats m_last;
    devourer::RxRingStats m_prev;  // cumulative values at the previous take
    int m_min_armed = 0;
    long long m_cb_max_us = 0;
    long long m_qdepth_max = 0;
};
