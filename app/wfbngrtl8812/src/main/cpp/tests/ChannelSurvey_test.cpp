// The app side of the pre-flight channel survey (docs/xr/channel-survey-design.md, phase 1): the dwell plan, the
// per-dwell record built from frames + energy reads (devourer chanmig SurveyDwell), the recommendation through
// devourer's RecommendEngine, and the JSONL lines logged as PPXR_SURVEY.
#include "ChannelSurvey.h"

#include <gtest/gtest.h>

#include <string>
#include <vector>

using devourer::chanmig::ChannelDef;
using devourer::chanmig::SurveyDwell;

namespace
{
bool has(const std::string& s, const std::string& part)
{
    return s.find(part) != std::string::npos;
}

std::string name(const ChannelDef& d)
{
    char buf[20];
    d.format(buf, sizeof buf);
    return buf;
}

// One 1 s dwell on candidate idx: foreign airtime share oth (0..1), own-video share own, NHM busy %.
SurveyDwell dwell(survey::DwellBuilder& b, const std::vector<ChannelDef>& c, size_t idx, uint64_t round, uint64_t seq,
                  int64_t t0, double oth, double own, uint8_t busy)
{
    b.begin(seq, c[idx], round, 0x1234, t0);
    b.retuned(1500, 30);
    // frames of 1500 B at OFDM 54 (desc 0x0B): ~242 us each
    const uint32_t us = devourer::chanmig::frame_airtime_us(0x0B, 1500, 0, false);
    for (uint32_t t = 0; t + us <= static_cast<uint32_t>(oth * 1e6); t += us) b.frame(false, 60, 40, 0x0B, 1500, 0, false);
    for (uint32_t t = 0; t + us <= static_cast<uint32_t>(own * 1e6); t += us) b.frame(true, 70, 45, 0x0B, 1500, 0, false);
    survey::Energy e{};
    e.valid_fa = true;
    e.fa_ofdm = 20;
    e.cca_ofdm = 100;
    e.valid_igi = true;
    e.igi = 0x20;
    e.valid_nhm = true;
    e.nhm[0] = static_cast<uint8_t>(100 - busy);
    e.nhm[3] = busy;
    e.nhm_dur = 2;
    b.energy(e);
    return b.finish(t0 + 1030, 1000, 0);
}
}  // namespace

TEST(ChannelSurvey, TheDefaultPlanIsTheNineNonDfsChannels)
{
    const auto c = survey::candidates();
    ASSERT_EQ(c.size(), 9u);
    EXPECT_EQ(name(c.front()), "5:36/20");   // devourer ChannelDef::format: band:primary/width
    EXPECT_EQ(c.back().primary, 165);
}

TEST(ChannelSurvey, TheScheduleVisitsEveryChannelOncePerRoundInterleaved)
{
    const auto s = survey::schedule(9, 3);
    ASSERT_EQ(s.size(), 27u);
    EXPECT_EQ(s[0].round, 0u);
    EXPECT_EQ(s[0].idx, 0u);
    EXPECT_EQ(s[8].idx, 8u);
    EXPECT_EQ(s[9].round, 1u);   // round 1 starts over from the first channel
    EXPECT_EQ(s[9].idx, 0u);
}

TEST(ChannelSurvey, NhmBusyIsTheShareAboveTheLowestBucketAndPeakTheFullest)
{
    uint8_t h[12] = {60, 0, 10, 30};
    EXPECT_EQ(survey::nhm_busy_pct(h), 40);
    EXPECT_EQ(survey::nhm_peak(h), 0);
    uint8_t q[12] = {};
    EXPECT_EQ(survey::nhm_busy_pct(q), 0);   // nothing counted: not busy
}

TEST(ChannelSurvey, TheDwellSplitsOwnVideoFromOtherTrafficByAirtime)
{
    survey::DwellBuilder b;
    const auto c = survey::candidates();
    b.begin(7, c[6], 1, 0x1234, 1000);
    b.retuned(1800, 30);
    b.frame(true, 70, 45, 0x0B, 1500, 0, false);    // our video
    b.frame(false, 90, 30, 0x0B, 500, 0, false);    // a neighbour
    survey::Energy e{};
    e.valid_fa = true;
    e.fa_ofdm = 5;
    e.cca_ofdm = 9;
    e.valid_nhm = true;
    e.nhm[0] = 50;
    e.nhm[5] = 50;
    b.energy(e);
    const SurveyDwell d = b.finish(2030, 1000, 0);
    EXPECT_EQ(d.seq, 7u);
    EXPECT_EQ(d.def.primary, 157);
    EXPECT_EQ(d.frames, 2u);
    EXPECT_EQ(d.dvr_frames, 1u);
    EXPECT_EQ(d.dvr_air_us, devourer::chanmig::frame_airtime_us(0x0B, 1500, 0, false));
    EXPECT_EQ(d.oth_air_us, devourer::chanmig::frame_airtime_us(0x0B, 500, 0, false));
    EXPECT_EQ(d.rssi_max_raw, 90);
    EXPECT_EQ(d.retune_us, 1800);
    EXPECT_EQ(d.observe_ms, 1000);
    EXPECT_TRUE(d.valid_fa);
    EXPECT_EQ(d.cca_ofdm, 9u);
    EXPECT_TRUE(d.valid_nhm);
    EXPECT_EQ(d.nhm_busy_pct, 50);
    EXPECT_EQ(d.nhm_peak, 0);   // a tie keeps the lowest bucket
}

TEST(ChannelSurvey, ABusyChannelRanksLastAndOurOwnVideoIsNotOccupancy)
{
    survey::DwellBuilder b;
    const auto c = survey::candidates();
    std::vector<SurveyDwell> dw;
    uint64_t seq = 0;
    int64_t t = 0;
    for (const auto& v : survey::schedule(c.size(), 3))
    {
        const bool busy = c[v.idx].primary == 153;     // a neighbour: 40 % foreign airtime, NHM 60 %
        const bool link = c[v.idx].primary == 165;     // our link: 50 % own video
        dw.push_back(dwell(b, c, v.idx, v.round, seq++, t, busy ? 0.40 : 0.01, link ? 0.50 : 0.0, busy ? 60 : 5));
        t += 1100;
    }
    const survey::Result r = survey::recommend(dw, c, 0x1234, 165, t);
    ASSERT_EQ(r.decision.ranking.size(), 9u);
    EXPECT_EQ(r.decision.ranking.back().def.primary, 153);
    EXPECT_FALSE(r.decision.ranking.back().qualified);
    EXPECT_NE(r.recommended, 153);
    EXPECT_NE(r.recommended, 0);
    bool link_qualified = false;
    for (const auto& s : r.decision.ranking)
        if (s.def.primary == 165) link_qualified = s.qualified || s.occ_q50 < 0.2;
    EXPECT_TRUE(link_qualified) << "our own 50 % video must not read as occupancy";
}

TEST(ChannelSurvey, TheLinesAreDevourersJsonl)
{
    survey::DwellBuilder b;
    const auto c = survey::candidates();
    const SurveyDwell d = dwell(b, c, 0, 0, 0, 0, 0.1, 0.0, 10);
    const std::string l = survey::dwell_line(d);
    EXPECT_TRUE(has(l, "\"survey.dwell\"")) << l;
    EXPECT_TRUE(has(l, "\"chan\":\"5:36/20\"")) << l;
    EXPECT_EQ(l.find('\n'), std::string::npos);   // one logcat line, no newline
    std::vector<SurveyDwell> one{d};
    const survey::Result r = survey::recommend(one, c, 0x1234, 36, 2000);
    EXPECT_TRUE(has(survey::ranking_line(r.decision), "\"channel.ranking\""));
}

TEST(ChannelSurvey, TheStartAndResultLinesFrameTheRun)
{
    const auto c = survey::candidates();
    const std::string s = survey::start_line(survey::plan_hash(c), c.size(), 165);
    EXPECT_TRUE(has(s, "\"ev\":\"survey.start\"")) << s;
    EXPECT_TRUE(has(s, "\"channels\":9,\"rounds\":3,\"dwell_ms\":1000,\"link\":165")) << s;
    const std::string r = survey::result_line(149, 165, 27, survey::Outcome::Completed);
    EXPECT_EQ(r, "{\"ev\":\"survey.result\",\"recommended\":149,\"link\":165,\"dwells\":27,"
                 "\"outcome\":\"completed\",\"aborted\":0}");
    EXPECT_TRUE(has(survey::result_line(0, 165, 27, survey::Outcome::RetuneBackFailed), "\"outcome\":\"retune_back_failed\""));
}
