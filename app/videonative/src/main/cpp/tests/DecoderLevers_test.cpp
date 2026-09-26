#include "DecoderLevers.h"
#include <gtest/gtest.h>
#include <algorithm>
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

// Final review Important 4: whole access units must fit the codec's input buffers.
TEST(DecoderLevers, AuAggregationRaisesMaxInputSizeToAssemblerCap)
{
    DecoderLevers l;
    l.auAggregation = true;
    auto f = flat(l);
    EXPECT_EQ((std::pair<std::string, int32_t>{"max-input-size", static_cast<int32_t>(AccessUnitAssembler::kDefaultMaxBytes)}),
              f.back());
    const auto defaults = flat(DecoderLevers{});
    EXPECT_EQ(0, std::count_if(defaults.begin(), defaults.end(),
                               [](const auto& kv) { return kv.first == "max-input-size"; }));
}

// Final review Important 7: the summary must describe what was actually applied.
TEST(DecoderLevers, AppliedLeversDropComponentWhenNotCreated)
{
    DecoderLevers l;
    l.preferLowLatencyComponent = true;
    EXPECT_EQ("LL LLC", leversSummary(appliedLevers(l, true)));
    EXPECT_EQ("LL", leversSummary(appliedLevers(l, false)));
}

// Debug key mask: isolates individual keys for measurement (which key makes decoding slower?).
TEST(DecoderLevers, KeyMaskDropsIndividualKeys)
{
    DecoderLevers l;
    l.keyMask = ~static_cast<uint32_t>(DecoderKey::Priority);
    for (const auto& kv : flat(l)) EXPECT_NE("priority", kv.first);
    EXPECT_EQ(5u, flat(l).size());

    l.keyMask = static_cast<uint32_t>(DecoderKey::Priority);
    EXPECT_EQ((std::vector<std::pair<std::string, int32_t>>{{"priority", 0}}), flat(l));

    l.keyMask = 0;
    EXPECT_TRUE(decoderFormatKeys(l).empty());
}

TEST(DecoderLevers, DefaultMaskKeepsEverything)
{
    DecoderLevers l;
    l.pictureOrder = l.operatingRate = l.auAggregation = true;
    DecoderLevers all = l;
    all.keyMask = 0xFFFFFFFFu;
    EXPECT_EQ(flat(all), flat(l));
}

// Which components to try, in order, before falling back to the default for the MIME type.
TEST(DecoderLevers, ComponentCandidatesOrder)
{
    DecoderLevers l;
    EXPECT_TRUE(componentCandidates(l, true).empty());  // default decoder

    l.preferLowLatencyComponent = true;
    EXPECT_EQ((std::vector<std::string>{"c2.qti.hevc.decoder.low_latency"}), componentCandidates(l, true));

    l.componentName = "c2.qti.hevc.decoder";  // an explicit name wins, then the low-latency one
    EXPECT_EQ((std::vector<std::string>{"c2.qti.hevc.decoder", "c2.qti.hevc.decoder.low_latency"}),
              componentCandidates(l, true));

    l.preferLowLatencyComponent = false;
    l.componentName             = "c2.qti.avc.decoder";
    EXPECT_EQ((std::vector<std::string>{"c2.qti.avc.decoder"}), componentCandidates(l, false));
}
