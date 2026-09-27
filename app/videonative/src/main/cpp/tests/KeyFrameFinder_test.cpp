#include "NALU/KeyFrameFinder.hpp"
#include <gtest/gtest.h>
#include <vector>

// isChangedSPS decides when VideoDecoder rebuilds a running decoder: only an SPS whose bytes differ from the
// one the decoder was configured with (an encoder restart with new parameters), never a repeated SPS.
namespace {
using Bytes = std::vector<uint8_t>;

// H.264 NAL units with a 4-byte start code; 0x67 = SPS, 0x68 = PPS, 0x65 = IDR slice.
const Bytes kSps480  = {0, 0, 0, 1, 0x67, 0x42, 0xC0, 0x1E, 0xDA, 0x02, 0x80, 0xF6};
const Bytes kSps1080 = {0, 0, 0, 1, 0x67, 0x42, 0xC0, 0x28, 0xDA, 0x01, 0xE0, 0x08, 0x9F};
const Bytes kPps     = {0, 0, 0, 1, 0x68, 0xCE, 0x3C, 0x80, 0x00};
const Bytes kIdr     = {0, 0, 0, 1, 0x65, 0x88, 0x84, 0x00, 0x33};

NALU nalu(const Bytes& b) { return NALU(b.data(), b.size()); }
}  // namespace

TEST(KeyFrameFinder, NoSavedSpsIsNotAChange)
{
    KeyFrameFinder k;
    EXPECT_FALSE(k.isChangedSPS(nalu(kSps480)));
}

TEST(KeyFrameFinder, RepeatedIdenticalSpsIsNotAChange)
{
    KeyFrameFinder k;
    k.saveIfKeyFrame(nalu(kSps480));
    k.saveIfKeyFrame(nalu(kPps));
    EXPECT_FALSE(k.isChangedSPS(nalu(kSps480)));
}

TEST(KeyFrameFinder, DifferentSpsIsAChange)
{
    KeyFrameFinder k;
    k.saveIfKeyFrame(nalu(kSps1080));
    k.saveIfKeyFrame(nalu(kPps));
    EXPECT_TRUE(k.isChangedSPS(nalu(kSps480)));
}

TEST(KeyFrameFinder, NonSpsUnitsAreNeverAChange)
{
    KeyFrameFinder k;
    k.saveIfKeyFrame(nalu(kSps1080));
    EXPECT_FALSE(k.isChangedSPS(nalu(kPps)));
    EXPECT_FALSE(k.isChangedSPS(nalu(kIdr)));
}

TEST(KeyFrameFinder, ResetForgetsTheSavedSps)
{
    KeyFrameFinder k;
    k.saveIfKeyFrame(nalu(kSps1080));
    k.reset();
    EXPECT_FALSE(k.isChangedSPS(nalu(kSps480)));
}
