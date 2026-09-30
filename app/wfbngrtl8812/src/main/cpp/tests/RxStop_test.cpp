// devourer's RX-loop stop contract (devourer/src/RxStop.h): a stop requested before or while the loop runs ends it,
// and each loop exit consumes the request (the device stays restartable). The old contract, where each StartRxLoop
// cleared the request on entry, lost a stop that landed between a caller's "should I still start?" check
// (WfbngLink::run's stop_requested) and the clear, and the loop then ran on (pixelpilot-xr-66's item, 2026-10-01).
// A loop that does not return in time fails the test and is then released with a second request, so a broken
// contract cannot hang the test binary.
#include "RxStop.h"
#include "SignalStop.h"

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <functional>
#include <future>
#include <stdexcept>
#include <thread>

using devourer::RxStopLatch;
using namespace std::chrono_literals;

namespace
{
// A stand-in for bulk_read_async_loop: polls the stop predicate like the real transport loop, packets or not.
struct FakeLoop
{
    std::atomic<int> polls{0};
    void operator()(const std::function<bool()>& stop)
    {
        while (!stop())
        {
            polls++;
            std::this_thread::sleep_for(1ms);
        }
    }
};

// Runs latch.run(loop) on a thread; true when it returned within `within`. On a timeout the loop is released
// (another request) and joined, so the test can fail cleanly.
bool returnsWithin(RxStopLatch& latch, FakeLoop& loop, std::chrono::milliseconds within,
                   const std::function<void()>& before = [] {})
{
    std::promise<void> done;
    auto f = done.get_future();
    std::thread t([&] {
        before();
        latch.run([&](const std::function<bool()>& stop) { loop(stop); });
        done.set_value();
    });
    const bool ok = f.wait_for(within) == std::future_status::ready;
    if (!ok)
        while (f.wait_for(10ms) != std::future_status::ready) latch.request();
    t.join();
    return ok;
}
}  // namespace

TEST(RxStop, AStopBetweenTheCallersCheckAndTheLoopStartEndsTheLoop)
{
    // The lost-stop interleaving, forced: the run thread passes its "stop requested?" check, then the stop lands,
    // then the loop starts.
    RxStopLatch latch;
    FakeLoop loop;
    std::atomic<bool> app_stop{false};   // WfbngLink's stop_requested(fd)
    std::promise<void> checked, stopped;
    auto checkedF = checked.get_future();
    auto stoppedF = stopped.get_future();
    std::thread jni([&] {
        checkedF.wait();
        app_stop = true;   // note_stop_requested(fd)
        latch.request();   // devctl.stopRxLoop(fd) -> StopRxLoop()
        stopped.set_value();
    });
    const bool ok = returnsWithin(latch, loop, 500ms, [&] {
        ASSERT_FALSE(app_stop.load());   // the check passes: the stop has not happened yet
        checked.set_value();
        stoppedF.wait();                 // ...and lands before the loop starts
    });
    jni.join();
    EXPECT_TRUE(ok) << "the stop requested before the loop started was lost";
}

TEST(RxStop, AStopRequestedBeforeStartEndsTheLoopAtOnce)
{
    RxStopLatch latch;
    FakeLoop loop;
    latch.request();
    EXPECT_TRUE(returnsWithin(latch, loop, 500ms));
    EXPECT_EQ(loop.polls.load(), 0);
}

TEST(RxStop, AStopWhileRunningEndsTheLoop)
{
    RxStopLatch latch;
    FakeLoop loop;
    std::thread stopper([&] {
        while (loop.polls.load() < 5) std::this_thread::sleep_for(1ms);
        latch.request();
    });
    EXPECT_TRUE(returnsWithin(latch, loop, 2000ms));
    stopper.join();
    EXPECT_GE(loop.polls.load(), 5);
}

TEST(RxStop, TheExitConsumesTheStopSoTheDeviceIsRestartable)
{
    RxStopLatch latch;
    FakeLoop first, second;
    latch.request();
    ASSERT_TRUE(returnsWithin(latch, first, 500ms));
    EXPECT_FALSE(latch.requested());
    // The next run keeps running until a new stop.
    std::thread stopper([&] {
        std::this_thread::sleep_for(100ms);
        latch.request();
    });
    const auto t0 = std::chrono::steady_clock::now();
    EXPECT_TRUE(returnsWithin(latch, second, 2000ms));
    stopper.join();
    EXPECT_GE(std::chrono::steady_clock::now() - t0, 90ms) << "a consumed stop ended the next run early";
}

TEST(RxStop, ALoopThatThrowsStillConsumesTheStopSoTheNextRunIsNotCutShort)
{
    // 25's note: consume on every way out, not only a normal return, or "restartable" breaks for other embedders.
    RxStopLatch latch;
    latch.request();
    EXPECT_THROW(latch.run([](const std::function<bool()>&) { throw std::runtime_error("usb gone"); }),
                 std::runtime_error);
    EXPECT_FALSE(latch.requested());
    FakeLoop next;
    std::thread stopper([&] {
        std::this_thread::sleep_for(100ms);
        latch.request();
    });
    const auto t0 = std::chrono::steady_clock::now();
    EXPECT_TRUE(returnsWithin(latch, next, 2000ms));
    stopper.join();
    EXPECT_GE(std::chrono::steady_clock::now() - t0, 90ms) << "a stop left latched by the throw ended the next run";
}

TEST(RxStop, TheProcessWideSignalFlagStillEndsTheLoop)
{
    RxStopLatch latch;
    FakeLoop loop;
    g_devourer_should_stop = true;
    const bool ok = returnsWithin(latch, loop, 500ms);
    g_devourer_should_stop = false;
    EXPECT_TRUE(ok);
}
