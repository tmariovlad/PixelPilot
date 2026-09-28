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
    std::mutex               m;
    std::vector<std::string> lines;
    std::vector<Clock::time_point> times;

    FakeAir()
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
        listen(fd, 8);
        timeval tv{0, 50000};
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        th = std::thread([this] {
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
                const char ok[] = "HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok";
                send(c, ok, sizeof(ok) - 1, 0);
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
    r.setOnResult([&](bool ok) { (ok ? okResults : failedResults)++; });
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
