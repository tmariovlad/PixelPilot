#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <exception>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "ChannelSurvey.h"

// The pre-flight channel survey's lifecycle (docs/xr/channel-survey-design.md §7): one run on its own thread, the
// device reached only through the injected SurveyOps, so the run is host-testable with a fake device.
// - The RX thread hands every received frame to frame() while active(); it is counted only inside a dwell.
// - done(outcome) is called once, on the survey thread, at the end: Completed (the caller starts the uplink),
//   Aborted (stopAndJoin(): no retune back, no uplink) or RetuneBackFailed (the retune back failed twice).
// - stopAndJoin() is the teardown barrier: when it returns, the thread has ended and no SurveyOps call follows.
//   WfbngLink::release_link calls it before the device goes (pixelpilot-xr-25's review, B1). Not from the survey
//   thread itself (done() must not call it).
struct SurveyOps {
    std::function<void(uint8_t)> to20;             // full retune to 20 MHz on a channel (SetMonitorChannel)
    std::function<void(uint8_t)> retune;           // the lean hop (FastRetune)
    std::function<survey::Energy(bool)> energy;    // GetRxEnergy(with_nhm), converted
    std::function<void()> back;                    // back to the link channel and width; throws on failure
};

struct SurveyTiming {
    int settle_ms = survey::kSettleMs;
    int dwell_ms = survey::kDwellMs;
    int rounds = survey::kRounds;
};

using SurveyOutcome = survey::Outcome;

class SurveyRunner {
  public:
    using Log = std::function<void(const std::string &)>;
    using Done = std::function<void(SurveyOutcome)>;

    ~SurveyRunner() { stopAndJoin(); }

    void start(SurveyOps ops, int link_channel, Log log, Done done, SurveyTiming timing = {}) {
        stopAndJoin();
        abort_ = false;
        active_ = true;
        thread_ = std::thread([this, ops = std::move(ops), link_channel, log = std::move(log), done = std::move(done),
                               timing] { run(ops, link_channel, log, done, timing); });
    }

    bool active() const { return active_.load(std::memory_order_acquire); }

    // RX thread: one decoded frame (own = one of our wfb channels).
    void frame(bool own, int rssi_raw, int snr_raw, uint16_t desc_rate, uint32_t len, uint8_t bw, bool sgi) {
        std::lock_guard<std::mutex> lock(mu_);
        if (observing_) dwell_.frame(own, rssi_raw, snr_raw, desc_rate, len, bw, sgi);
    }

    void stopAndJoin() {
        abort_ = true;
        if (thread_.joinable()) thread_.join();
        active_ = false;
    }

  private:
    static int64_t nowMs() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
                   std::chrono::steady_clock::now().time_since_epoch())
            .count();
    }

    bool cut() const { return abort_.load(); }

    void nap(int ms) const {
        for (int t = 0; t < ms && !cut(); t += 50)
            std::this_thread::sleep_for(std::chrono::milliseconds(std::min(50, ms - t)));
    }

    SurveyOutcome sweep(const SurveyOps &ops, const std::vector<survey::ChannelDef> &cands, uint32_t plan,
                        const Log &log, const SurveyTiming &t, std::vector<survey::SurveyDwell> &dwells) {
        ops.to20(cands.front().primary);
        uint64_t seq = 0;
        for (const survey::Visit &v : survey::schedule(cands.size(), t.rounds)) {
            if (cut()) return SurveyOutcome::Aborted;
            const auto &def = cands[v.idx];
            const int64_t t0 = nowMs();
            const auto r0 = std::chrono::steady_clock::now();
            uint16_t flags = 0;
            try {
                ops.retune(def.primary);
            } catch (const std::exception &) {
                flags |= devourer::chanmig::kFlagRetuneFailed;
            }
            const int64_t retune_us =
                std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - r0).count();
            nap(t.settle_ms);
            ops.energy(false);   // discard: resets the delta counters, drains the previous channel's frames
            const int64_t obs0 = nowMs();
            {
                std::lock_guard<std::mutex> lock(mu_);
                dwell_.begin(seq++, def, v.round, plan, t0);
                dwell_.retuned(retune_us, t.settle_ms);
                observing_ = true;
            }
            nap(t.dwell_ms);
            const survey::Energy e = ops.energy(true);
            const int64_t t1 = nowMs();
            survey::SurveyDwell d;
            {
                std::lock_guard<std::mutex> lock(mu_);
                observing_ = false;
                dwell_.energy(e);
                if (cut()) flags |= devourer::chanmig::kFlagTruncated;
                d = dwell_.finish(t1, t1 - obs0, flags);
            }
            dwells.push_back(d);
            log(survey::dwell_line(d));
        }
        return cut() ? SurveyOutcome::Aborted : SurveyOutcome::Completed;
    }

    // Back to the link channel, one retry.
    static bool retuneBack(const SurveyOps &ops) {
        for (int attempt = 0; attempt < 2; ++attempt) {
            try {
                ops.back();
                return true;
            } catch (const std::exception &) {
            }
        }
        return false;
    }

    void run(const SurveyOps &ops, int link_channel, const Log &log, const Done &done, SurveyTiming t) {
        const auto cands = survey::candidates();
        const uint32_t plan = survey::plan_hash(cands);
        std::vector<survey::SurveyDwell> dwells;
        log(survey::start_line(plan, cands.size(), link_channel));
        SurveyOutcome outcome;
        try {
            outcome = sweep(ops, cands, plan, log, t, dwells);
        } catch (const std::exception &) {
            outcome = SurveyOutcome::Aborted;
        }
        {
            std::lock_guard<std::mutex> lock(mu_);
            observing_ = false;
        }
        int recommended = 0;
        if (outcome == SurveyOutcome::Completed) {
            if (!retuneBack(ops)) outcome = SurveyOutcome::RetuneBackFailed;
            if (!dwells.empty()) {
                const survey::Result r = survey::recommend(dwells, cands, plan, link_channel, nowMs());
                log(survey::ranking_line(r.decision));
                recommended = r.recommended;
            }
        }
        log(survey::result_line(recommended, link_channel, dwells.size(), outcome));
        active_ = false;
        done(outcome);
    }

    std::atomic<bool> active_{false};
    std::atomic<bool> abort_{false};
    std::mutex mu_;   // guards dwell_ and observing_ (the RX thread's frame() vs the survey thread)
    survey::DwellBuilder dwell_;
    bool observing_ = false;
    std::thread thread_;
};
