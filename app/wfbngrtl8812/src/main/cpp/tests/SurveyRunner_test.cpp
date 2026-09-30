// The survey's lifecycle (SurveyRunner.h) against a fake device: the order of the device calls, stopAndJoin() as the
// guarantee that no device call follows it (release_link relies on it: pixelpilot-xr-25's review, B1), and the retune
// back to the link channel being retried once and otherwise reported instead of starting the uplink (B2).
#include "SurveyRunner.h"

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace
{
struct FakeDevice
{
    std::mutex mu;
    std::vector<std::string> calls;
    std::atomic<int> backFailures{0};   // how many times back() throws before it succeeds

    void note(const std::string& c)
    {
        std::lock_guard<std::mutex> l(mu);
        calls.push_back(c);
    }
    size_t count()
    {
        std::lock_guard<std::mutex> l(mu);
        return calls.size();
    }
    int countOf(const std::string& prefix)
    {
        std::lock_guard<std::mutex> l(mu);
        int n = 0;
        for (const auto& c : calls) n += c.rfind(prefix, 0) == 0;
        return n;
    }
    SurveyOps ops()
    {
        SurveyOps o;
        o.to20 = [this](uint8_t ch) { note("to20 " + std::to_string(ch)); };
        o.retune = [this](uint8_t ch) { note("retune " + std::to_string(ch)); };
        o.energy = [this](bool nhm) {
            note(nhm ? "energy nhm" : "energy");
            survey::Energy e;
            e.valid_fa = true;
            return e;
        };
        o.back = [this] {
            note("back");
            if (backFailures.load() > 0)
            {
                backFailures--;
                throw std::runtime_error("retune back failed");
            }
        };
        return o;
    }
};

struct Rig
{
    FakeDevice dev;
    std::mutex mu;
    std::vector<std::string> log;
    std::vector<SurveyOutcome> outcomes;
    SurveyRunner runner;

    void start(SurveyTiming t)
    {
        runner.start(
            dev.ops(), 165,
            [this](const std::string& l) {
                std::lock_guard<std::mutex> g(mu);
                log.push_back(l);
            },
            [this](SurveyOutcome o) {
                std::lock_guard<std::mutex> g(mu);
                outcomes.push_back(o);
            },
            t);
    }
    bool logged(const std::string& part)
    {
        std::lock_guard<std::mutex> g(mu);
        for (const auto& l : log)
            if (l.find(part) != std::string::npos) return true;
        return false;
    }
};

SurveyTiming fast(int dwell_ms = 2, int rounds = 1)
{
    SurveyTiming t;
    t.settle_ms = 0;
    t.dwell_ms = dwell_ms;
    t.rounds = rounds;
    return t;
}
}  // namespace

TEST(SurveyRunner, ACompleteRunRetunesEveryChannelComesBackAndReportsCompleted)
{
    Rig r;
    r.start(fast());
    for (int i = 0; i < 200 && r.runner.active(); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(5));
    ASSERT_FALSE(r.runner.active());
    r.runner.stopAndJoin();
    EXPECT_EQ(r.dev.countOf("to20"), 1);
    EXPECT_EQ(r.dev.countOf("retune"), 9);
    EXPECT_EQ(r.dev.countOf("energy nhm"), 9);   // the read closing each dwell
    EXPECT_EQ(r.dev.countOf("back"), 1);
    ASSERT_EQ(r.outcomes.size(), 1u);
    EXPECT_EQ(r.outcomes[0], SurveyOutcome::Completed);
    EXPECT_TRUE(r.logged("\"survey.start\""));
    EXPECT_TRUE(r.logged("\"channel.ranking\""));
    EXPECT_TRUE(r.logged("\"outcome\":\"completed\""));
}

TEST(SurveyRunner, StopAndJoinEndsTheRunAndNoDeviceCallFollowsIt)
{
    Rig r;
    r.start(fast(300, 3));   // a long run: 27 dwells of 300 ms
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    const auto t0 = std::chrono::steady_clock::now();
    r.runner.stopAndJoin();
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count();
    EXPECT_LT(ms, 200) << "the survey must notice the abort within its 50 ms slices";
    const size_t after = r.dev.count();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    EXPECT_EQ(r.dev.count(), after) << "a device call after stopAndJoin() returned: release_link would race it";
    EXPECT_EQ(r.dev.countOf("back"), 0);   // aborted: the device is being torn down, no retune back
    ASSERT_EQ(r.outcomes.size(), 1u);
    EXPECT_EQ(r.outcomes[0], SurveyOutcome::Aborted);
    EXPECT_FALSE(r.runner.active());
    r.runner.stopAndJoin();   // idempotent
}

TEST(SurveyRunner, ARetuneBackThatFailsTwiceIsReportedNotIgnored)
{
    Rig r;
    r.dev.backFailures = 2;
    r.start(fast());
    for (int i = 0; i < 200 && r.runner.active(); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(5));
    r.runner.stopAndJoin();
    EXPECT_EQ(r.dev.countOf("back"), 2);   // one retry
    ASSERT_EQ(r.outcomes.size(), 1u);
    EXPECT_EQ(r.outcomes[0], SurveyOutcome::RetuneBackFailed);
    EXPECT_TRUE(r.logged("\"outcome\":\"retune_back_failed\""));
}

TEST(SurveyRunner, ARetuneBackThatFailsOnceSucceedsOnTheRetry)
{
    Rig r;
    r.dev.backFailures = 1;
    r.start(fast());
    for (int i = 0; i < 200 && r.runner.active(); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(5));
    r.runner.stopAndJoin();
    EXPECT_EQ(r.dev.countOf("back"), 2);
    ASSERT_EQ(r.outcomes.size(), 1u);
    EXPECT_EQ(r.outcomes[0], SurveyOutcome::Completed);
}

TEST(SurveyRunner, FramesAreCountedOnlyInsideADwell)
{
    Rig r;
    r.runner.frame(false, 60, 30, 0x0B, 1500, 0, false);   // before any run: ignored, no crash
    EXPECT_FALSE(r.runner.active());
}
