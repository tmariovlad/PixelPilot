#include "IdrRequestPolicy.h"
#include "IdrRequester.h"

#include <arpa/inet.h>
#include <gtest/gtest.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

// Request a key frame from the air unit (waybeam GET /request/idr) when the video loses an RTP packet: at most one
// request per interval, and a loss inside the interval is served at its end (docs/xr/link-envelope.md "frame fate").

TEST(IdrRequestPolicy, FirstRequestGoesAtOnceThenOnePerInterval)
{
    IdrRequestPolicy p(200);
    EXPECT_EQ(0, p.delayMs(1000));
    p.sent(1000);
    EXPECT_EQ(150, p.delayMs(1050));
    EXPECT_EQ(0, p.delayMs(1200));
    EXPECT_EQ(0, p.delayMs(5000));
}

TEST(IdrRequestPolicy, DefaultIntervalIs200Ms)
{
    IdrRequestPolicy p;
    p.sent(0);
    EXPECT_EQ(200, p.delayMs(0));
}

TEST(IdrRequestPolicy, IntervalCanBeChangedAndNonPositiveKeepsIt)
{
    IdrRequestPolicy p(200);
    p.setIntervalMs(1000);
    p.sent(0);
    EXPECT_EQ(800, p.delayMs(200));
    p.setIntervalMs(0);
    EXPECT_EQ(800, p.delayMs(200));
}

namespace {
using Clock = std::chrono::steady_clock;

// A one-connection-at-a-time HTTP server on 127.0.0.1 that records each request line and its arrival time.
struct FakeAir
{
    int                      fd = -1;
    uint16_t                 port = 0;
    std::thread              th;
    std::atomic<bool>        stop{false};
    std::atomic<int>         status{200};
    std::mutex               m;
    std::vector<std::string> lines;
    std::vector<Clock::time_point> times;

    enum class Listen { Now, Deferred };

    explicit FakeAir(Listen when = Listen::Now)
    {
        fd = socket(AF_INET, SOCK_STREAM, 0);
        int one = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
        sockaddr_in a{};
        a.sin_family = AF_INET;
        a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        a.sin_port = 0;
        bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof(a));
        socklen_t len = sizeof(a);
        getsockname(fd, reinterpret_cast<sockaddr*>(&a), &len);
        port = ntohs(a.sin_port);
        if (when == Listen::Deferred) return;
        listen(fd, 8);
        start(0);
    }

    // Serve requests; with drop_ms > 0, first wait that long, then take one parked connection off the queue unserved.
    void start(int drop_ms)
    {
        timeval tv{0, 50000};
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        th = std::thread([this, drop_ms] {
            for (int waited = 0; waited < drop_ms && !stop; waited += 5)
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            if (drop_ms > 0 && !stop)
            {
                const int parked = accept(fd, nullptr, nullptr);
                if (parked >= 0) close(parked);
            }
            while (!stop)
            {
                int c = accept(fd, nullptr, nullptr);
                if (c < 0) continue;
                char buf[512];
                ssize_t n = recv(c, buf, sizeof(buf) - 1, 0);
                std::string req = n > 0 ? std::string(buf, static_cast<size_t>(n)) : std::string();
                {
                    std::lock_guard<std::mutex> l(m);
                    lines.push_back(req.substr(0, req.find("\r\n")));
                    times.push_back(Clock::now());
                }
                const std::string reply =
                    "HTTP/1.0 " + std::to_string(status.load()) + " X\r\nContent-Length: 2\r\n\r\nok";
                send(c, reply.data(), reply.size(), 0);
                close(c);
            }
        });
    }
    ~FakeAir()
    {
        stop = true;
        th.join();
        close(fd);
    }
    size_t count()
    {
        std::lock_guard<std::mutex> l(m);
        return lines.size();
    }
    bool waitFor(size_t n, int ms)
    {
        auto end = Clock::now() + std::chrono::milliseconds(ms);
        while (Clock::now() < end)
        {
            if (count() >= n) return true;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        return count() >= n;
    }
};

void sleepMs(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
}  // namespace

TEST(IdrRequester, OffByDefaultSendsNothing)
{
    FakeAir      air;
    IdrRequester r("127.0.0.1", air.port, 200);
    r.notifyLoss();
    sleepMs(300);
    EXPECT_EQ(0u, air.count());
    EXPECT_EQ(0u, r.requestsOk());
}

TEST(IdrRequester, OneLossSendsOneGetOfTheIdrPath)
{
    FakeAir      air;
    IdrRequester r("127.0.0.1", air.port, 200);
    std::atomic<int> okResults{0}, failedResults{0};
    r.setOnResult([&](const IdrRequester::Outcome& o) { (o.result == IdrRequester::Result::Ok ? okResults : failedResults)++; });
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1000));
    sleepMs(300);
    EXPECT_EQ(1, okResults.load());
    EXPECT_EQ(0, failedResults.load());
    EXPECT_EQ(1u, air.count());
    EXPECT_EQ("GET /request/idr HTTP/1.0", air.lines[0]);
    EXPECT_EQ(1u, r.requestsOk());
    EXPECT_EQ(0u, r.requestsFailed());
}

TEST(IdrRequester, LossesInsideTheIntervalAreServedOnceAtItsEnd)
{
    FakeAir      air;
    IdrRequester r("127.0.0.1", air.port, 200);
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1000));
    r.notifyLoss();
    r.notifyLoss();
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(2, 1000));
    sleepMs(400);
    EXPECT_EQ(2u, air.count());
    const auto gap = std::chrono::duration_cast<std::chrono::milliseconds>(air.times[1] - air.times[0]).count();
    EXPECT_GE(gap, 180);
    EXPECT_LE(gap, 400);
}

TEST(IdrRequester, NotifyNeverBlocksAndAnUnreachableAirCountsAsFailed)
{
    uint16_t closedPort;
    {
        FakeAir air;   // take a free port, then close it
        closedPort = air.port;
    }
    IdrRequester r("127.0.0.1", closedPort, 200);
    r.setEnabled(true);
    const auto t0 = Clock::now();
    for (int i = 0; i < 1000; i++) r.notifyLoss();
    EXPECT_LT(std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count(), 50);
    sleepMs(500);
    EXPECT_GE(r.requestsFailed(), 1u);
    EXPECT_EQ(0u, r.requestsOk());
}

TEST(IdrRequester, ALongerIntervalSpacesTheRequests)
{
    FakeAir      air;
    IdrRequester r("127.0.0.1", air.port, 200);
    r.setMinIntervalMs(600);
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1000));
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(2, 1500));
    const auto gap = std::chrono::duration_cast<std::chrono::milliseconds>(air.times[1] - air.times[0]).count();
    EXPECT_GE(gap, 570);
}

// While the key frame is still needed (a freeze waiting for it), the request is repeated every interval, not only on the
// next loss: a lost request or a lost IDR would otherwise hold the picture until the 1 s freeze timeout.
TEST(IdrRequester, RepeatsWhileStillNeededThenStops)
{
    FakeAir           air;
    IdrRequester      r("127.0.0.1", air.port, 150);
    std::atomic<bool> need{true};
    r.setStillNeeded([&] { return need.load(); });
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(3, 1500));
    need = false;
    const size_t n = air.count();
    sleepMs(500);
    EXPECT_LE(air.count(), n + 1);
}

TEST(IdrRequester, RepeatsStopAfterTheRetryWindow)
{
    FakeAir      air;
    IdrRequester r("127.0.0.1", air.port, 100, 400);
    r.setStillNeeded([] { return true; });
    r.setEnabled(true);
    r.notifyLoss();
    sleepMs(1200);
    EXPECT_GE(air.count(), 3u);
    EXPECT_LE(air.count(), 6u);
}

TEST(IdrRequester, AClosedPortCountsAsRefused)
{
    uint16_t closedPort;
    {
        FakeAir air;
        closedPort = air.port;
    }
    IdrRequester r("127.0.0.1", closedPort, 200);
    r.setEnabled(true);
    r.notifyLoss();
    sleepMs(400);
    EXPECT_EQ(1u, r.requests(IdrRequester::Result::Refused));
    EXPECT_EQ(0u, r.requests(IdrRequester::Result::Ok));
    // refused ends the race: one result and one attempt, not one per attempt
    EXPECT_EQ(1u, r.requestsFailed());
    EXPECT_EQ(1u, r.attemptsStarted());
}

TEST(IdrRequester, ANon200ReplyCountsAsBadStatus)
{
    FakeAir air;
    air.status = 429;
    IdrRequester r("127.0.0.1", air.port, 200);
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1000));
    sleepMs(200);
    EXPECT_EQ(1u, r.requests(IdrRequester::Result::BadStatus));
    EXPECT_EQ(0u, r.requests(IdrRequester::Result::Ok));
}

namespace {
// A FakeAir whose first SYNs are lost, as on the wfb tunnel (docs/xr/link-envelope.md FRZ: 17 of 19 failed requests
// were connect_timeout). listen(fd, 0) plus one parked connection fills the accept queue, and with
// tcp_abort_on_overflow=0 Linux then drops every new SYN; the client's kernel retransmits it only after the ~1 s initial
// RTO. At drop_ms the parked connection is taken off the queue and closed, so the next SYN gets through.
struct SynDroppingAir : FakeAir
{
    int parked = -1;

    explicit SynDroppingAir(int drop_ms)
        : FakeAir(Listen::Deferred)
    {
        listen(fd, 0);
        parked = socket(AF_INET, SOCK_STREAM, 0);
        sockaddr_in a{};
        a.sin_family      = AF_INET;
        a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        a.sin_port        = htons(port);
        connect(parked, reinterpret_cast<sockaddr*>(&a), sizeof(a));
        sleepMs(20);   // the parked handshake completes; from here new SYNs are dropped
        start(drop_ms);
    }
    ~SynDroppingAir() { close(parked); }
};
}  // namespace

// One lost SYN must not cost the request: before, a request opened one socket and waited 1 s for it, so a lost SYN (or
// SYN-ACK) was retransmitted just as the connect timeout expired, and the request failed as connect_timeout.
TEST(IdrRequester, ALostSynIsOvertakenByALaterAttempt)
{
    SynDroppingAir          air(100);
    IdrRequester            r("127.0.0.1", air.port, 200);
    std::atomic<int>        results{0};
    IdrRequester::Outcome   seen;
    r.setOnResult([&](const IdrRequester::Outcome& o) { seen = o; results++; });
    r.setEnabled(true);
    const auto t0 = Clock::now();
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1500));
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(air.times[0] - t0).count();
    EXPECT_LT(ms, 500) << "the request waited for the kernel's SYN retransmit";
    for (int i = 0; i < 100 && results == 0; i++) sleepMs(10);
    ASSERT_EQ(1, results.load());
    EXPECT_EQ(1u, r.requestsOk());
    EXPECT_EQ(0u, r.requestsFailed());
    // attempt 1's SYN was dropped; attempt 2 (at 150 ms) found the queue drained at 100 ms
    EXPECT_EQ(2, seen.attempt);
    EXPECT_EQ(2, seen.attempts);
    EXPECT_GE(seen.connect_ms, IdrRequester::kAttemptSpacingMs - 10);
    EXPECT_LT(seen.connect_ms, 400);
    EXPECT_EQ(1u, r.wonByLaterAttempt());
    EXPECT_EQ(2u, r.attemptsStarted());
    EXPECT_EQ(1u, r.connected());
    EXPECT_EQ(static_cast<uint64_t>(seen.connect_ms), r.connectMsSum());
}

// The attempts race, but only the first to connect carries the GET: one request asks for one key frame.
TEST(IdrRequester, RacingAttemptsSendOneGet)
{
    SynDroppingAir air(100);
    IdrRequester   r("127.0.0.1", air.port, 200);
    r.setEnabled(true);
    r.notifyLoss();
    ASSERT_TRUE(air.waitFor(1, 1500));
    sleepMs(1500);   // past the lost SYN's retransmit, which completes a losing attempt's handshake
    EXPECT_EQ(1u, air.count());
}

// With every SYN lost for longer than the connect budget, the request still ends as connect_timeout, on time.
TEST(IdrRequester, AllSynsLostIsAConnectTimeoutWithinTheBudget)
{
    SynDroppingAir   air(5000);
    IdrRequester     r("127.0.0.1", air.port, 200);
    std::atomic<int> results{0};
    r.setOnResult([&](const IdrRequester::Outcome&) { results++; });
    r.setEnabled(true);
    const auto t0 = Clock::now();
    r.notifyLoss();
    for (int i = 0; i < 200 && results == 0; i++) sleepMs(10);
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count();
    EXPECT_EQ(1u, r.requests(IdrRequester::Result::ConnectTimeout));
    EXPECT_LT(ms, IdrRequester::kConnectTimeoutMs + 300);
    EXPECT_EQ(static_cast<uint32_t>(IdrRequester::kMaxAttempts), r.attemptsStarted());
    EXPECT_EQ(0u, r.connected());
}

// A clean handshake is won by the first attempt, at once.
TEST(IdrRequester, ACleanHandshakeIsWonByTheFirstAttempt)
{
    FakeAir               air;
    IdrRequester          r("127.0.0.1", air.port, 200);
    std::atomic<int>      results{0};
    IdrRequester::Outcome seen;
    r.setOnResult([&](const IdrRequester::Outcome& o) { seen = o; results++; });
    r.setEnabled(true);
    r.notifyLoss();
    for (int i = 0; i < 100 && results == 0; i++) sleepMs(10);
    ASSERT_EQ(1, results.load());
    EXPECT_EQ(IdrRequester::Result::Ok, seen.result);
    EXPECT_EQ(1, seen.attempt);
    EXPECT_EQ(1, seen.attempts);
    EXPECT_LT(seen.connect_ms, 50);
    EXPECT_EQ(0u, r.wonByLaterAttempt());
}
