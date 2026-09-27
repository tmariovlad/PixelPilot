#include "ListenerLifecycle.h"

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <thread>

namespace {
using namespace std::chrono_literals;

// A loop that counts how often it was started and runs until told to stop (or returns at once if asked).
struct FakeLoop {
    std::atomic<int> starts{0};
    std::atomic<int> alive{0};
    std::atomic<bool> exitAtOnce{false};
    ListenerLifecycle::Loop fn() {
        return [this](const std::atomic<bool> &stop) {
            ++starts;
            ++alive;
            while (!stop && !exitAtOnce) std::this_thread::sleep_for(1ms);
            --alive;
        };
    }
};

bool waitFor(const std::function<bool()> &cond) {
    for (int i = 0; i < 2000 && !cond(); ++i) std::this_thread::sleep_for(1ms);
    return cond();
}
}  // namespace

TEST(ListenerLifecycle, OneListenerForSeveralUsers) {
    FakeLoop f;
    ListenerLifecycle l(f.fn());
    l.start();
    l.start();                                        // XR resumes while 2D still holds it
    ASSERT_TRUE(waitFor([&] { return f.alive == 1; }));
    EXPECT_EQ(1, f.starts);
    l.stop();                                         // 2D onStop: XR still needs it
    std::this_thread::sleep_for(20ms);
    EXPECT_EQ(1, f.alive);
    l.stop();                                         // last user: stopped and joined
    EXPECT_EQ(0, f.alive);
    EXPECT_EQ(0, l.users());
}

TEST(ListenerLifecycle, RestartsAfterAFullStop) {
    // the old global flag was never reset, so every listener after the first stop exited immediately
    FakeLoop f;
    ListenerLifecycle l(f.fn());
    l.start();
    l.stop();
    l.start();
    ASSERT_TRUE(waitFor([&] { return f.alive == 1; }));
    EXPECT_EQ(2, f.starts);
    l.stop();
}

TEST(ListenerLifecycle, ExtraStopsAreIgnored) {
    FakeLoop f;
    ListenerLifecycle l(f.fn());
    l.stop();                                         // 2D onStop without a matching start
    l.start();
    ASSERT_TRUE(waitFor([&] { return f.alive == 1; }));
    EXPECT_EQ(1, l.users());
    l.stop();
    EXPECT_EQ(0, f.alive);
}

TEST(ListenerLifecycle, ALoopThatEndedOnItsOwnIsReplacedOnTheNextStart) {
    FakeLoop f;
    f.exitAtOnce = true;                              // e.g. bind() failed
    ListenerLifecycle l(f.fn());
    l.start();
    ASSERT_TRUE(waitFor([&] { return !l.running(); }));
    f.exitAtOnce = false;
    l.start();
    ASSERT_TRUE(waitFor([&] { return f.alive == 1; }));
    EXPECT_EQ(2, f.starts);
    l.stop();
    l.stop();
    EXPECT_EQ(0, f.alive);
}
