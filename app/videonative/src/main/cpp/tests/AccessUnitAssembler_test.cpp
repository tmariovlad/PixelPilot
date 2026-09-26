#include "AccessUnitAssembler.h"
#include <gtest/gtest.h>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using Bytes = std::vector<uint8_t>;

Bytes h264(uint8_t type, bool firstSlice)
{
    // 4-byte start code, NAL header (nri=3), then one payload byte whose MSB is the
    // ue(v) of first_mb_in_slice (1 == value 0 == first slice)
    return {0, 0, 0, 1, static_cast<uint8_t>(0x60 | type), static_cast<uint8_t>(firstSlice ? 0x88 : 0x40), 0x11};
}

Bytes h265(uint8_t type, bool firstSlice)
{
    return {0, 0, 0, 1, static_cast<uint8_t>(type << 1), 0x01, static_cast<uint8_t>(firstSlice ? 0x80 : 0x00), 0x22};
}

struct Out
{
    Bytes              data;
    Clock::time_point  t;
    bool               cfg;
};

struct Fixture : ::testing::Test
{
    AccessUnitAssembler asmb;
    std::vector<Out>    out;
    AccessUnitAssembler::Emit emit = [this](const uint8_t* d, size_t n, Clock::time_point t, bool cfg)
    { out.push_back({Bytes(d, d + n), t, cfg}); };

    void push(const Bytes& b, bool h265Stream, bool marker, Clock::time_point t = Clock::time_point{})
    {
        asmb.push(au::classify(b.data(), b.size(), h265Stream, marker, t), emit);
    }
};

Bytes cat(std::initializer_list<Bytes> parts)
{
    Bytes r;
    for (const auto& p : parts) r.insert(r.end(), p.begin(), p.end());
    return r;
}
}  // namespace

TEST(AuHelpers, StartCodeSize)
{
    const uint8_t four[] = {0, 0, 0, 1, 0x65};
    const uint8_t three[] = {0, 0, 1, 0x65};
    const uint8_t none[] = {1, 2, 3, 4};
    EXPECT_EQ(4u, au::startCodeSize(four, sizeof(four)));
    EXPECT_EQ(3u, au::startCodeSize(three, sizeof(three)));
    EXPECT_EQ(0u, au::startCodeSize(none, sizeof(none)));
}

TEST(AuHelpers, FirstSliceBits)
{
    auto a = h264(1, true), b = h264(1, false), c = h265(1, true), d = h265(1, false);
    EXPECT_TRUE(au::isFirstSliceOfPicture(a.data(), a.size(), false));
    EXPECT_FALSE(au::isFirstSliceOfPicture(b.data(), b.size(), false));
    EXPECT_TRUE(au::isFirstSliceOfPicture(c.data(), c.size(), true));
    EXPECT_FALSE(au::isFirstSliceOfPicture(d.data(), d.size(), true));
}

TEST(AuHelpers, Classify)
{
    auto sps = h264(7, false), aud = h264(9, false), idr = h264(5, true);
    auto i = au::classify(sps.data(), sps.size(), false, false, {});
    EXPECT_TRUE(i.isConfig);
    EXPECT_FALSE(i.isVcl);
    EXPECT_TRUE(au::classify(aud.data(), aud.size(), false, false, {}).isAud);
    auto v = au::classify(idr.data(), idr.size(), false, true, {});
    EXPECT_TRUE(v.isVcl);
    EXPECT_TRUE(v.isFirstSlice);
    EXPECT_TRUE(v.endOfAu);
    auto vps = h265(32, false), aud5 = h265(35, false), trail = h265(1, true);
    EXPECT_TRUE(au::classify(vps.data(), vps.size(), true, false, {}).isConfig);
    EXPECT_TRUE(au::classify(aud5.data(), aud5.size(), true, false, {}).isAud);
    EXPECT_TRUE(au::classify(trail.data(), trail.size(), true, false, {}).isVcl);
}

TEST_F(Fixture, MarkerClosesAccessUnit)
{
    auto sei = h264(6, false), slice = h264(1, true);
    push(sei, false, false);
    EXPECT_TRUE(out.empty());
    push(slice, false, true);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(cat({sei, slice}), out[0].data);
    EXPECT_FALSE(out[0].cfg);
    EXPECT_EQ(0u, asmb.pendingBytes());
}

TEST_F(Fixture, MultiSliceJoinedUntilMarker)
{
    auto s1 = h265(1, true), s2 = h265(1, false);
    push(s1, true, false);
    push(s2, true, true);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(cat({s1, s2}), out[0].data);
}

TEST_F(Fixture, ConfigNalusPassAloneAsConfig)
{
    auto sps = h264(7, false), pps = h264(8, false), idr = h264(5, true);
    push(sps, false, false);
    push(pps, false, false);
    push(idr, false, true);
    ASSERT_EQ(3u, out.size());
    EXPECT_TRUE(out[0].cfg);
    EXPECT_TRUE(out[1].cfg);
    EXPECT_FALSE(out[2].cfg);
    EXPECT_EQ(idr, out[2].data);
}

TEST_F(Fixture, LostMarkerSplitsOnNextFirstSlice)
{
    auto a = h264(1, true), b = h264(1, true);
    push(a, false, false);  // its marker packet was lost
    push(b, false, true);
    ASSERT_EQ(2u, out.size());
    EXPECT_EQ(a, out[0].data);
    EXPECT_EQ(b, out[1].data);
}

TEST_F(Fixture, AudStartsNewAccessUnit)
{
    auto a = h264(1, true), aud = h264(9, false), b = h264(1, true);
    push(a, false, false);
    push(aud, false, false);
    push(b, false, true);
    ASSERT_EQ(2u, out.size());
    EXPECT_EQ(a, out[0].data);
    EXPECT_EQ(cat({aud, b}), out[1].data);
}

TEST_F(Fixture, OversizeNaluPassesThroughAlone)
{
    AccessUnitAssembler small(8);
    std::vector<Out> o;
    AccessUnitAssembler::Emit e = [&o](const uint8_t* d, size_t n, Clock::time_point t, bool c)
    { o.push_back({Bytes(d, d + n), t, c}); };
    auto big = h265(1, true);  // 8 bytes, not larger than 8
    Bytes huge = big;
    huge.push_back(0x33);      // 9 bytes > 8
    small.push(au::classify(huge.data(), huge.size(), true, false, {}), e);
    ASSERT_EQ(1u, o.size());
    EXPECT_EQ(huge, o[0].data);
    EXPECT_EQ(0u, small.pendingBytes());
}

TEST_F(Fixture, EmitCarriesFirstNaluTime)
{
    const auto t1 = Clock::time_point{} + std::chrono::milliseconds(5);
    const auto t2 = Clock::time_point{} + std::chrono::milliseconds(9);
    push(h265(39, false), true, false, t1);  // SEI prefix
    push(h265(1, true), true, true, t2);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(t1, out[0].t);
}

TEST_F(Fixture, FlushEmitsPendingAndResets)
{
    auto a = h264(1, true);
    push(a, false, false);
    asmb.flush(emit);
    ASSERT_EQ(1u, out.size());
    asmb.flush(emit);
    EXPECT_EQ(1u, out.size());
}
