#ifndef PIXELPILOT_IDR_REQUESTER_H
#define PIXELPILOT_IDR_REQUESTER_H

#include "IdrRequestPolicy.h"

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <thread>

// Asks the air unit's encoder for a key frame (waybeam HTTP GET /request/idr, through the wfb tunnel) after the video
// lost an RTP packet, so a frame the parser dropped, or fed incomplete, stops corrupting the picture before the 2 s
// GOP ends. Off until setEnabled(true) (LatencyExperiments request_idr_on_loss). notifyLoss() never blocks: the HTTP
// request runs on this object's own thread, paced by IdrRequestPolicy.
class IdrRequester
{
  public:
    // The air unit's end of the wfb tunnel (WfbNgVpnService routes 10.5.0.0/24) and waybeam's HTTP port.
    static constexpr const char* kAirHost = "10.5.0.10";
    static constexpr uint16_t    kAirPort = 80;
    static constexpr const char* kPath    = "/request/idr";

    IdrRequester(std::string host = kAirHost, uint16_t port = kAirPort,
                 int min_interval_ms = IdrRequestPolicy::kDefaultMinIntervalMs);
    ~IdrRequester();
    IdrRequester(const IdrRequester&)            = delete;
    IdrRequester& operator=(const IdrRequester&) = delete;

    void setEnabled(bool enabled) { m_enabled = enabled; }
    // Called on this object's thread after each request, true = the air answered 200. Set before enabling.
    void setOnResult(std::function<void(bool)> cb) { m_on_result = std::move(cb); }
    // Minimum time between requests; <= 0 keeps the current one. Safe from any thread.
    void setMinIntervalMs(int ms);
    bool enabled() const { return m_enabled; }

    // A packet was lost; safe from any thread, returns at once.
    void notifyLoss();

    uint32_t requestsOk() const { return m_ok; }
    uint32_t requestsFailed() const { return m_failed; }

  private:
    void run();
    // One HTTP/1.0 GET of kPath; true on a "200" status line. Bounded by kTimeoutMs for connect and for the reply.
    bool requestOnce() const;

    static constexpr int kTimeoutMs = 300;

    const std::string       m_host;
    const uint16_t          m_port;
    IdrRequestPolicy        m_policy;
    std::function<void(bool)> m_on_result;
    std::atomic<bool>       m_enabled{false};
    std::atomic<uint32_t>   m_ok{0};
    std::atomic<uint32_t>   m_failed{0};
    std::mutex              m_mutex;
    std::condition_variable m_cv;
    bool                    m_pending = false;
    bool                    m_stop    = false;
    std::thread             m_thread;
};

#endif  // PIXELPILOT_IDR_REQUESTER_H
