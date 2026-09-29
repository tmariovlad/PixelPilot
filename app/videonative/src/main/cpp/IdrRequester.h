#ifndef PIXELPILOT_IDR_REQUESTER_H
#define PIXELPILOT_IDR_REQUESTER_H

#include "IdrRequestPolicy.h"

#include <array>
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
//
// While setStillNeeded() says the key frame has not arrived yet (a freeze waiting for it), the request is repeated every
// interval for up to the retry window: a request lost on the tunnel, or a lost IDR, would otherwise hold the picture
// until the next loss or the freeze timeout (docs/xr/link-envelope.md: 24 of 76 requests never reached the air).
class IdrRequester
{
  public:
    // The air unit's end of the wfb tunnel (WfbNgVpnService routes 10.5.0.0/24) and waybeam's HTTP port.
    static constexpr const char* kAirHost = "10.5.0.10";
    static constexpr uint16_t    kAirPort = 80;
    static constexpr const char* kPath    = "/request/idr";
    static constexpr int         kDefaultRetryWindowMs = 2000;
    // A TCP SYN lost on the tunnel is retransmitted after ~1 s, so a shorter connect timeout turns it into a failure.
    static constexpr int kConnectTimeoutMs = 1000;
    static constexpr int kReplyTimeoutMs   = 500;

    // Outcome of one request; also the order of the per-result counters.
    enum class Result { Ok, Refused, ConnectTimeout, ReplyTimeout, BadStatus, Error };
    static constexpr int kResults = 6;
    static const char*   name(Result r);

    IdrRequester(std::string host = kAirHost, uint16_t port = kAirPort,
                 int min_interval_ms = IdrRequestPolicy::kDefaultMinIntervalMs,
                 int retry_window_ms = kDefaultRetryWindowMs);
    ~IdrRequester();
    IdrRequester(const IdrRequester&)            = delete;
    IdrRequester& operator=(const IdrRequester&) = delete;

    void setEnabled(bool enabled) { m_enabled = enabled; }
    // Called on this object's thread after each request. Set before enabling.
    void setOnResult(std::function<void(Result)> cb) { m_on_result = std::move(cb); }
    // True while the key frame asked for has not arrived; read on this object's thread. Set before enabling.
    void setStillNeeded(std::function<bool()> stillNeeded) { m_still_needed = std::move(stillNeeded); }
    // Minimum time between requests; <= 0 keeps the current one. Safe from any thread.
    void setMinIntervalMs(int ms);
    bool enabled() const { return m_enabled; }

    // A packet was lost; safe from any thread, returns at once.
    void notifyLoss();

    uint32_t requests(Result r) const { return m_counts[static_cast<int>(r)]; }
    uint32_t requestsOk() const { return requests(Result::Ok); }
    uint32_t requestsFailed() const;

  private:
    void   run();
    // One HTTP/1.0 GET of kPath.
    Result requestOnce() const;

    const std::string                              m_host;
    const uint16_t                                 m_port;
    const int                                      m_retry_window_ms;
    IdrRequestPolicy                               m_policy;
    std::function<void(Result)>                    m_on_result;
    std::function<bool()>                          m_still_needed;
    std::atomic<bool>                              m_enabled{false};
    std::array<std::atomic<uint32_t>, kResults>    m_counts{};
    std::mutex                                     m_mutex;
    std::condition_variable                        m_cv;
    bool                                           m_pending    = false;
    bool                                           m_stop       = false;
    bool                                           m_in_burst   = false;   // requests since a loss, repeated while needed
    int64_t                                        m_burst_ms   = 0;       // when that burst's first request went out
    std::thread                                    m_thread;
};

#endif  // PIXELPILOT_IDR_REQUESTER_H
