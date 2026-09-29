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
//
// Each request races TCP connects: a new SYN every kAttemptSpacingMs within the kConnectTimeoutMs budget, the GET on
// the first socket that connects, the others closed before it is sent (one request = one key frame). A lost SYN or
// SYN-ACK is only retransmitted after the kernel's ~1 s initial RTO, so with a single socket one lost handshake packet
// failed the request (17 of 19 failures in capture B were connect_timeout, docs/xr/link-envelope.md FRZ).
class IdrRequester
{
  public:
    // The air unit's end of the wfb tunnel (WfbNgVpnService routes 10.5.0.0/24) and waybeam's HTTP port.
    static constexpr const char* kAirHost = "10.5.0.10";
    static constexpr uint16_t    kAirPort = 80;
    static constexpr const char* kPath    = "/request/idr";
    static constexpr int         kDefaultRetryWindowMs = 2000;
    // Budget for the handshake of one request, over all its attempts.
    static constexpr int kConnectTimeoutMs = 1000;
    // A new connect attempt (SYN) this often while none has connected: a later attempt overtakes a lost SYN long
    // before the kernel's ~1 s retransmit.
    static constexpr int kAttemptSpacingMs = 150;
    static constexpr int kMaxAttempts      = (kConnectTimeoutMs + kAttemptSpacingMs - 1) / kAttemptSpacingMs;
    static constexpr int kReplyTimeoutMs   = 500;

    // Outcome of one request; also the order of the per-result counters.
    enum class Result { Ok, Refused, ConnectTimeout, ReplyTimeout, BadStatus, Error };
    static constexpr int kResults = 6;
    static const char*   name(Result r);

    // One request as it went: the result, and how its handshake went.
    struct Outcome
    {
        Result result     = Result::Error;
        int    attempts   = 0;    // connect attempts started (SYNs)
        int    attempt    = 0;    // 1-based index of the attempt that connected; 0 = none did
        int    connect_ms = -1;   // request start -> the winner connected; -1 = none did
    };

    IdrRequester(std::string host = kAirHost, uint16_t port = kAirPort,
                 int min_interval_ms = IdrRequestPolicy::kDefaultMinIntervalMs,
                 int retry_window_ms = kDefaultRetryWindowMs);
    ~IdrRequester();
    IdrRequester(const IdrRequester&)            = delete;
    IdrRequester& operator=(const IdrRequester&) = delete;

    void setEnabled(bool enabled) { m_enabled = enabled; }
    // Called on this object's thread after each request. Set before enabling.
    void setOnResult(std::function<void(const Outcome&)> cb) { m_on_result = std::move(cb); }
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
    // Handshake counters over all requests: attempts started, requests won by attempt >= 2, and the sum/number of
    // connect times of the requests that connected (for a mean).
    uint32_t attemptsStarted() const { return m_attempts; }
    uint32_t wonByLaterAttempt() const { return m_won_late; }
    uint64_t connectMsSum() const { return m_connect_ms_sum; }
    uint32_t connected() const { return m_connected; }

  private:
    void   run();
    // One HTTP/1.0 GET of kPath.
    Outcome requestOnce() const;
    // The connect race: the connected socket (or -1), filling in how the handshake went.
    int connectRace(Outcome& out) const;

    const std::string                              m_host;
    const uint16_t                                 m_port;
    const int                                      m_retry_window_ms;
    IdrRequestPolicy                               m_policy;
    std::function<void(const Outcome&)>            m_on_result;
    std::function<bool()>                          m_still_needed;
    std::atomic<bool>                              m_enabled{false};
    std::array<std::atomic<uint32_t>, kResults>    m_counts{};
    std::atomic<uint32_t>                          m_attempts{0};
    std::atomic<uint32_t>                          m_won_late{0};
    std::atomic<uint64_t>                          m_connect_ms_sum{0};
    std::atomic<uint32_t>                          m_connected{0};
    std::mutex                                     m_mutex;
    std::condition_variable                        m_cv;
    bool                                           m_pending    = false;
    bool                                           m_stop       = false;
    bool                                           m_in_burst   = false;   // requests since a loss, repeated while needed
    int64_t                                        m_burst_ms   = 0;       // when that burst's first request went out
    std::thread                                    m_thread;
};

#endif  // PIXELPILOT_IDR_REQUESTER_H
