#ifndef PIXELPILOT_DECODERLEVERS_H
#define PIXELPILOT_DECODERLEVERS_H

#include <cstdint>
#include <string>
#include <vector>
#include "AccessUnitAssembler.h"

// Decoder-side latency levers. Mirrors LatencyExperiments (Java), which owns the pref keys/defaults.
struct DecoderLevers
{
    bool lowLatency                = true;
    bool pictureOrder              = false;
    bool operatingRate             = false;
    bool preferLowLatencyComponent = false;
    bool auAggregation             = false;

    // Codec-facing extras are the ones a decoder can reject in configure().
    bool hasExtras() const { return pictureOrder || operatingRate || preferLowLatencyComponent; }

    DecoderLevers onlyBase() const
    {
        DecoderLevers b;
        b.lowLatency    = lowLatency;
        b.auAggregation = auAggregation;
        return b;
    }
};

struct FormatKey
{
    const char* key;
    int32_t     value;
};

// The AMediaFormat keys a set of levers stands for. Free of NDK types so the mapping is host-testable.
inline std::vector<FormatKey> decoderFormatKeys(const DecoderLevers& l)
{
    std::vector<FormatKey> k;
    if (l.lowLatency)
    {
        // AMEDIAFORMAT_KEY_LOW_LATENCY (API 30+): output a frame as soon as it is decoded.
        k.push_back({"low-latency", 1});
        // Vendor equivalents for codecs that ignore the AOSP key (Qualcomm covers the XR2 headsets).
        k.push_back({"vendor.low-latency.enable", 1});
        k.push_back({"vendor.qti-ext-dec-low-latency.enable", 1});
        k.push_back({"vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1});
        k.push_back({"vendor.rtc-ext-dec-low-latency.enable", 1});
        // Realtime priority. Not combined with a maximum operating rate: Qualcomm decoders can fail when
        // they cannot honour both (moonlight-android MediaCodecHelper.decoderSupportsMaxOperatingRate).
        if (!l.operatingRate) k.push_back({"priority", 0});
    }
    // Output in decode order: OpenIPC streams have no B-frames, so this removes any reorder hold.
    if (l.pictureOrder) k.push_back({"vendor.qti-ext-dec-picture-order.enable", 1});
    // Keep the codec clocked up; Short.MAX_VALUE as moonlight-android uses on Qualcomm.
    if (l.operatingRate) k.push_back({"operating-rate", 32767});
    // Whole access units can be larger than the codec's default input buffer; size it to the
    // assembler's cap so no picture is dropped as "too big".
    if (l.auAggregation) k.push_back({"max-input-size", static_cast<int32_t>(AccessUnitAssembler::kDefaultMaxBytes)});
    return k;
}

// The levers as they actually took effect: a preferred low-latency component that does not exist
// on this device was not used, so it must not be reported.
inline DecoderLevers appliedLevers(const DecoderLevers& requested, bool lowLatencyComponentCreated)
{
    DecoderLevers applied = requested;
    if (!lowLatencyComponentCreated) applied.preferLowLatencyComponent = false;
    return applied;
}

// Qualcomm ships separate low-latency Codec2 components on some SoCs (moonlight-android MediaCodecHelper).
inline const char* lowLatencyComponentName(bool h265)
{
    return h265 ? "c2.qti.hevc.decoder.low_latency" : "c2.qti.avc.decoder.low_latency";
}

inline std::string leversSummary(const DecoderLevers& l)
{
    std::string s;
    auto        add = [&s](const char* t)
    {
        if (!s.empty()) s += ' ';
        s += t;
    };
    if (l.lowLatency) add("LL");
    if (l.pictureOrder) add("PO");
    if (l.operatingRate) add("OR");
    if (l.preferLowLatencyComponent) add("LLC");
    if (l.auAggregation) add("AU");
    return s.empty() ? "stock" : s;
}

#endif  // PIXELPILOT_DECODERLEVERS_H
