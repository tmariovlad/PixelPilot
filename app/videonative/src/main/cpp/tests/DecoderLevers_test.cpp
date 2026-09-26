#include "DecoderLevers.h"
#include <gtest/gtest.h>
#include <string>

namespace {
std::vector<std::pair<std::string, int32_t>> flat(const DecoderLevers& l)
{
    std::vector<std::pair<std::string, int32_t>> r;
    for (const auto& k : decoderFormatKeys(l)) r.emplace_back(k.key, k.value);
    return r;
}
}  // namespace

TEST(DecoderLevers, DefaultIsExactlyTheUpstreamKeySet)
{
    // Pins the pre-existing writeAndroidPerformanceParams() behaviour (PixelPilot #113).
    const std::vector<std::pair<std::string, int32_t>> expected = {
        {"low-latency", 1},
        {"vendor.low-latency.enable", 1},
        {"vendor.qti-ext-dec-low-latency.enable", 1},
        {"vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1},
        {"vendor.rtc-ext-dec-low-latency.enable", 1},
        {"priority", 0},
    };
    EXPECT_EQ(expected, flat(DecoderLevers{}));
}

TEST(DecoderLevers, AllOffIsEmpty)
{
    DecoderLevers l;
    l.lowLatency = false;
    EXPECT_TRUE(decoderFormatKeys(l).empty());
}

TEST(DecoderLevers, PictureOrderAddsQtiKey)
{
    DecoderLevers l;
    l.pictureOrder = true;
    auto f = flat(l);
    EXPECT_EQ((std::pair<std::string, int32_t>{"vendor.qti-ext-dec-picture-order.enable", 1}), f.back());
}

TEST(DecoderLevers, OperatingRateReplacesPriority)
{
    DecoderLevers l;
    l.operatingRate = true;
    auto f = flat(l);
    for (const auto& kv : f) EXPECT_NE("priority", kv.first);
    EXPECT_EQ((std::pair<std::string, int32_t>{"operating-rate", 32767}), f.back());
}

TEST(DecoderLevers, OnlyBaseKeepsLowLatencyDropsExtras)
{
    DecoderLevers l;
    l.pictureOrder = l.operatingRate = l.preferLowLatencyComponent = l.auAggregation = true;
    EXPECT_TRUE(l.hasExtras());
    DecoderLevers b = l.onlyBase();
    EXPECT_TRUE(b.lowLatency);
    EXPECT_FALSE(b.hasExtras());
    EXPECT_TRUE(b.auAggregation);  // not a codec key, cannot make configure() fail
}

TEST(DecoderLevers, ComponentNamesAndSummary)
{
    EXPECT_STREQ("c2.qti.hevc.decoder.low_latency", lowLatencyComponentName(true));
    EXPECT_STREQ("c2.qti.avc.decoder.low_latency", lowLatencyComponentName(false));
    DecoderLevers l;
    EXPECT_EQ("LL", leversSummary(l));
    l.pictureOrder = l.auAggregation = true;
    EXPECT_EQ("LL PO AU", leversSummary(l));
    l.lowLatency = l.pictureOrder = l.auAggregation = false;
    EXPECT_EQ("stock", leversSummary(l));
}
