#ifndef PIXELPILOT_DECODERLEVERS_H
#define PIXELPILOT_DECODERLEVERS_H

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include "AccessUnitAssembler.h"

// One bit per AMediaFormat key, for the debug key mask (isolating a single key in a measurement).
enum class DecoderKey : uint32_t
{
    LowLatency       = 1u << 0,  // "low-latency"
    VendorLowLatency = 1u << 1,  // "vendor.low-latency.enable"
    QtiLowLatency    = 1u << 2,  // "vendor.qti-ext-dec-low-latency.enable"
    HisiLowLatency   = 1u << 3,
    RtcLowLatency    = 1u << 4,
    Priority         = 1u << 5,  // "priority" = 0 (realtime)
    PictureOrder     = 1u << 6,
    OperatingRate    = 1u << 7,
    MaxInputSize     = 1u << 8,
};

// Decoder-side latency levers. Mirrors LatencyExperiments (Java), which owns the pref keys/defaults.
struct DecoderLevers
{
    bool lowLatency                = true;
    bool pictureOrder              = false;
    bool operatingRate             = false;
    bool preferLowLatencyComponent = false;
    bool auAggregation             = false;
    // Debug only: keys whose bit is clear are not written even if a lever asks for them.
    uint32_t keyMask = 0xFFFFFFFFu;

    // Codec-facing extras are the ones a decoder can reject in configure().
    bool hasExtras() const { return pictureOrder || operatingRate || preferLowLatencyComponent; }

    DecoderLevers onlyBase() const
    {
        DecoderLevers b;
        b.lowLatency    = lowLatency;
        b.auAggregation = auAggregation;
        b.keyMask       = keyMask;
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
    auto add = [&](DecoderKey bit, const char* key, int32_t value)
    {
        if (l.keyMask & static_cast<uint32_t>(bit)) k.push_back({key, value});
    };
    if (l.lowLatency)
    {
        // AMEDIAFORMAT_KEY_LOW_LATENCY (API 30+): output a frame as soon as it is decoded.
        add(DecoderKey::LowLatency, "low-latency", 1);
        // Vendor equivalents for codecs that ignore the AOSP key (Qualcomm covers the XR2 headsets).
        add(DecoderKey::VendorLowLatency, "vendor.low-latency.enable", 1);
        add(DecoderKey::QtiLowLatency, "vendor.qti-ext-dec-low-latency.enable", 1);
        add(DecoderKey::HisiLowLatency, "vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1);
        add(DecoderKey::RtcLowLatency, "vendor.rtc-ext-dec-low-latency.enable", 1);
        // Realtime priority. Not combined with a maximum operating rate: Qualcomm decoders can fail when
        // they cannot honour both (moonlight-android MediaCodecHelper.decoderSupportsMaxOperatingRate).
        if (!l.operatingRate) add(DecoderKey::Priority, "priority", 0);
    }
    // Output in decode order: OpenIPC streams have no B-frames, so this removes any reorder hold.
    if (l.pictureOrder) add(DecoderKey::PictureOrder, "vendor.qti-ext-dec-picture-order.enable", 1);
    // Keep the codec clocked up; Short.MAX_VALUE as moonlight-android uses on Qualcomm.
    if (l.operatingRate) add(DecoderKey::OperatingRate, "operating-rate", 32767);
    // Whole access units can be larger than the codec's default input buffer; size it to the
    // assembler's cap so no picture is dropped as "too big".
    if (l.auAggregation)
        add(DecoderKey::MaxInputSize, "max-input-size", static_cast<int32_t>(AccessUnitAssembler::kDefaultMaxBytes));
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
    if (l.keyMask != 0xFFFFFFFFu)
    {
        char buf[24];
        std::snprintf(buf, sizeof(buf), "mask=0x%x", l.keyMask);
        add(buf);
    }
    return s.empty() ? "stock" : s;
}

#endif  // PIXELPILOT_DECODERLEVERS_H
