#include "CodecSwitch.h"
#include "NALU/KeyFrameFinder.hpp"
#include <gtest/gtest.h>
#include <vector>

// VideoDecoder::interpretNALU on a codec switch: CodecSwitch reports it, and the saved SPS/PPS are forgotten
// (together with the running decoders). This models that order on the real KeyFrameFinder: without the reset, an
// H.264 SPS/PPS left over from before the switch plus the first H.265 VPS look like a complete H.265 set, and the
// decoder would be configured as "video/hevc" with H.264 parameter sets.
namespace {
using Bytes = std::vector<uint8_t>;

const Bytes kH264Sps = {0, 0, 0, 1, 0x67, 0x42, 0xC0, 0x1E};
const Bytes kH264Pps = {0, 0, 0, 1, 0x68, 0xCE, 0x3C, 0x80};
const Bytes kH265Vps = {0, 0, 0, 1, 0x40, 0x01, 0x0C, 0x01};
const Bytes kH265Sps = {0, 0, 0, 1, 0x42, 0x01, 0x01, 0x01};
const Bytes kH265Pps = {0, 0, 0, 1, 0x44, 0x01, 0xC1, 0x72};

struct Model
{
    CodecSwitch    codec;
    KeyFrameFinder keyFrames;
    bool           resetOnSwitch = true;

    // What interpretNALU does before it decides whether to configure: true when the decoder would be configured.
    bool feed(const Bytes& b, bool h265)
    {
        const NALU nalu(b.data(), b.size(), h265);
        if (codec.changed(h265) && resetOnSwitch) keyFrames.reset();
        keyFrames.saveIfKeyFrame(nalu);
        return keyFrames.allKeyFramesAvailable(h265);
    }
};
}  // namespace

TEST(CodecSwitchKeyFrames, WithoutTheResetAnH265DecoderWouldGetH264ParameterSets)
{
    Model m;
    m.resetOnSwitch = false;   // the hazard the reset exists for
    m.feed(kH264Sps, false);
    m.feed(kH264Pps, false);
    EXPECT_TRUE(m.feed(kH265Vps, true)) << "the stale H.264 SPS/PPS complete the H.265 set on the VPS alone";
}

TEST(CodecSwitchKeyFrames, AfterASwitchTheSetIsCompleteOnlyWithTheNewCodecsOwnSpsAndPps)
{
    Model m;
    EXPECT_FALSE(m.feed(kH264Sps, false));
    EXPECT_TRUE(m.feed(kH264Pps, false));    // H.264 decoder configured
    EXPECT_FALSE(m.feed(kH265Vps, true));    // switch: old parameter sets forgotten
    EXPECT_FALSE(m.feed(kH265Sps, true));
    EXPECT_TRUE(m.feed(kH265Pps, true));     // H.265 decoder configured from H.265 parameter sets only
    EXPECT_EQ(1u, m.codec.switches());
}

TEST(CodecSwitchKeyFrames, SwitchingBackNeedsTheH264SetAgain)
{
    Model m;
    m.feed(kH265Vps, true);
    m.feed(kH265Sps, true);
    EXPECT_TRUE(m.feed(kH265Pps, true));
    EXPECT_FALSE(m.feed(kH264Sps, false));   // switch back
    EXPECT_TRUE(m.feed(kH264Pps, false));
    EXPECT_EQ(1u, m.codec.switches());
}
