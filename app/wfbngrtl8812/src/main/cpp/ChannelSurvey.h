#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string>
#include <vector>

#include "Event.h"
#include "chanmig/ChannelDef.h"
#include "chanmig/ChannelEvents.h"
#include "chanmig/ChannelScore.h"
#include "chanmig/ScanPlan.h"
#include "chanmig/SurveyJsonl.h"
#include "chanmig/SurveyRecord.h"

// The app side of the pre-flight channel survey (docs/xr/channel-survey-design.md, phase 1), built on devourer's
// chanmig library: the candidate plan, the dwell schedule, the per-dwell record (chanmig::SurveyDwell) filled from the
// frames and the energy reads WfbngLink takes during a dwell, the recommendation through chanmig::RecommendEngine, and
// the JSONL lines (chanmig's own emitters) that WfbngLink logs as PPXR_SURVEY. Pure: WfbngLink owns the retunes and
// the device reads. Not thread-safe (DwellBuilder is fed under the link's lock).
namespace survey {

using devourer::chanmig::ChannelDef;
using devourer::chanmig::Decision;
using devourer::chanmig::SurveyDwell;

// UNII-1 36-48 and UNII-3 149-165; DFS 52-144 is excluded (the air has no radar detection).
inline constexpr const char *kDefaultPlan = "36,40,44,48,149,153,157,161,165";
inline constexpr int kRounds = 3;
inline constexpr int kDwellMs = 1000;
inline constexpr int kSettleMs = 30;

inline std::vector<ChannelDef> candidates(const char *plan = kDefaultPlan) {
    std::vector<ChannelDef> out;
    std::vector<devourer::chanmig::PlanParseError> errors;
    devourer::chanmig::parse_scan_plan(plan, out, errors);
    return out;
}

// The plan's identity, stamped into every dwell and required by the engine (chanmig ScanPlanConfig::plan_hash).
inline uint32_t plan_hash(const std::vector<ChannelDef> &c) {
    devourer::chanmig::ScanPlanConfig cfg;
    cfg.candidates = c;
    cfg.dwell_ms = kDwellMs;
    cfg.settle_ms = kSettleMs;
    return cfg.plan_hash();
}

struct Visit {
    uint64_t round;
    size_t idx;
};

// Round-major: every channel once per round, so a neighbour's burst does not land on one channel only.
inline std::vector<Visit> schedule(size_t channels, int rounds) {
    std::vector<Visit> out;
    for (int r = 0; r < rounds; ++r)
        for (size_t i = 0; i < channels; ++i) out.push_back({static_cast<uint64_t>(r), i});
    return out;
}

// NHM: percent of samples above the lowest bucket, and the fullest bucket (devourer docs/rx-spectrum-sensing.md, rx.nhm).
inline uint8_t nhm_busy_pct(const uint8_t h[12]) {
    unsigned total = 0;
    for (int i = 0; i < 12; ++i) total += h[i];
    return total ? static_cast<uint8_t>((100u * (total - h[0]) + total / 2) / total) : 0;
}

inline uint8_t nhm_peak(const uint8_t h[12]) {
    int best = 0;
    for (int i = 1; i < 12; ++i)
        if (h[i] > h[best]) best = i;
    return static_cast<uint8_t>(best);
}

// One energy read (devourer RxEnergy's fields, copied by WfbngLink so this header needs no device).
struct Energy {
    bool valid_fa = false;
    uint32_t fa_ofdm = 0, fa_cck = 0, cca_ofdm = 0, cca_cck = 0;
    bool valid_igi = false;
    uint8_t igi = 0;
    bool valid_nhm = false;
    uint8_t nhm[12] = {};
    uint16_t nhm_dur = 0;
};

// Fills one chanmig::SurveyDwell: begin() at the dwell start, retuned() after the retune, frame() per received frame
// during the observe window (own = a valid wfb frame of our link), energy() with the read that closes the window (its
// FA/CCA deltas span the window: the caller discards a read just before opening it), finish().
class DwellBuilder {
  public:
    void begin(uint64_t seq, const ChannelDef &def, uint64_t round, uint32_t plan, int64_t t_start_ms) {
        d_ = SurveyDwell{};
        d_.seq = seq;
        d_.def = def;
        d_.round = round;
        d_.plan_hash = plan;
        d_.t_start_ms = t_start_ms;
        rssi_sum_ = snr_sum_ = 0;
        d_.rssi_max_raw = std::numeric_limits<int>::min();
        d_.snr_min_raw = std::numeric_limits<int>::max();
    }

    void retuned(int64_t retune_us, int settle_ms) {
        d_.retune_us = retune_us;
        d_.settle_ms = settle_ms;
    }

    void frame(bool own, int rssi_raw, int snr_raw, uint16_t desc_rate, uint32_t len, uint8_t bw, bool sgi) {
        ++d_.frames;
        rssi_sum_ += rssi_raw;
        snr_sum_ += snr_raw;
        if (rssi_raw > d_.rssi_max_raw) d_.rssi_max_raw = rssi_raw;
        if (snr_raw < d_.snr_min_raw) d_.snr_min_raw = snr_raw;
        const uint32_t us = devourer::chanmig::frame_airtime_us(desc_rate, len, bw, sgi);
        if (own) {
            ++d_.dvr_frames;
            d_.dvr_air_us += us;
        } else {
            d_.oth_air_us += us;
        }
    }

    void energy(const Energy &e) {
        d_.valid_fa = e.valid_fa;
        d_.fa_ofdm = e.fa_ofdm;
        d_.fa_cck = e.fa_cck;
        d_.cca_ofdm = e.cca_ofdm;
        d_.cca_cck = e.cca_cck;
        d_.valid_igi = e.valid_igi;
        d_.igi = e.igi;
        d_.valid_nhm = e.valid_nhm;
        for (int i = 0; i < 12; ++i) d_.nhm[i] = e.nhm[i];
        d_.nhm_dur = e.nhm_dur;
        d_.nhm_busy_pct = e.valid_nhm ? nhm_busy_pct(e.nhm) : 0;
        d_.nhm_peak = e.valid_nhm ? nhm_peak(e.nhm) : 0;
        if (!e.valid_nhm) d_.flags |= devourer::chanmig::kFlagNhmMissing;
    }

    SurveyDwell finish(int64_t t_end_ms, int64_t observe_ms, uint16_t flags) {
        d_.t_end_ms = t_end_ms;
        d_.observe_ms = observe_ms;
        d_.flags |= flags;
        if (d_.frames) {
            d_.rssi_mean_raw = static_cast<int>(rssi_sum_ / static_cast<int64_t>(d_.frames));
            d_.snr_mean_raw = static_cast<int>(snr_sum_ / static_cast<int64_t>(d_.frames));
        } else {
            d_.rssi_max_raw = d_.snr_min_raw = 0;
        }
        return d_;
    }

  private:
    SurveyDwell d_;
    int64_t rssi_sum_ = 0, snr_sum_ = 0;
};

struct Result {
    Decision decision;
    int recommended = 0;   // the best qualified candidate's primary channel, 0 when none qualified
};

// chanmig::RecommendEngine over the survey's dwells, default policy. Pre-flight there is no active-link telemetry, so
// the engine holds (it recommends a migration only for an impaired active channel); its ranking still scores every
// candidate from the scout evidence, and the recommendation here is the best qualified one.
inline Result recommend(const std::vector<SurveyDwell> &dwells, const std::vector<ChannelDef> &cands, uint32_t plan,
                        int active_channel, int64_t now_ms) {
    ChannelDef active;
    for (const ChannelDef &c : cands)
        if (c.primary == active_channel) active = c;
    devourer::chanmig::RecommendEngine engine(devourer::chanmig::PolicyConfig{}, cands, plan, active);
    for (const SurveyDwell &d : dwells) engine.ingest_dwell(d, d.t_end_ms);
    Result r;
    r.decision = engine.decide(now_ms);
    for (const auto &s : r.decision.ranking)
        if (s.qualified) {
            r.recommended = s.def.primary;
            break;
        }
    return r;
}

// One chanmig JSONL event as a single line without the trailing newline (for logcat).
template <class Emit> std::string jsonl_line(Emit emit) {
    char *buf = nullptr;
    size_t len = 0;
    std::FILE *f = open_memstream(&buf, &len);
    if (f == nullptr) return "";
    {
        devourer::EventSink sink;
        sink.configure(f, devourer::EventSink::FlushPolicy::Never);
        emit(sink);
    }
    std::fclose(f);
    std::string s(buf ? buf : "", len);
    std::free(buf);
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
    return s;
}

inline std::string dwell_line(const SurveyDwell &d) {
    return jsonl_line([&](devourer::EventSink &sink) { devourer::chanmig::emit_survey_dwell(sink, d); });
}

inline std::string ranking_line(const Decision &d) {
    return jsonl_line([&](devourer::EventSink &sink) { devourer::chanmig::emit_ranking(sink, d); });
}

// The lines that frame a run (same JSONL shape as chanmig's events, so one parser reads the whole run).
inline std::string start_line(uint32_t plan, size_t channels, int link_channel) {
    char buf[160];
    std::snprintf(buf, sizeof buf,
                  "{\"ev\":\"survey.start\",\"plan\":\"0x%08x\",\"channels\":%zu,\"rounds\":%d,\"dwell_ms\":%d,\"link\":%d}",
                  plan, channels, kRounds, kDwellMs, link_channel);
    return buf;
}

// How a survey ended: Completed (the uplink may start), Aborted (stop / teardown: no uplink, no retune back),
// Failed (a device error mid-sweep nobody asked for: back on the link channel, no ranking, the uplink starts;
// pixelpilot-xr-25's re-review B3), RetuneBackFailed (the RTL could not return to the link channel after one retry:
// no uplink, the link restarts).
enum class Outcome { Completed, Aborted, Failed, RetuneBackFailed };

// The RTL is back on the link channel and the link is not being torn down: the caller starts the uplink.
inline bool starts_uplink(Outcome o) { return o == Outcome::Completed || o == Outcome::Failed; }

inline const char *outcome_name(Outcome o) {
    switch (o) {
    case Outcome::Completed: return "completed";
    case Outcome::Aborted: return "aborted";
    case Outcome::Failed: return "failed";
    default: return "retune_back_failed";
    }
}

inline std::string result_line(int recommended, int link_channel, size_t dwells, Outcome outcome) {
    char buf[160];
    std::snprintf(buf, sizeof buf,
                  "{\"ev\":\"survey.result\",\"recommended\":%d,\"link\":%d,\"dwells\":%zu,\"outcome\":\"%s\","
                  "\"aborted\":%d}",
                  recommended, link_channel, dwells, outcome_name(outcome), outcome == Outcome::Aborted ? 1 : 0);
    return buf;
}

}  // namespace survey
