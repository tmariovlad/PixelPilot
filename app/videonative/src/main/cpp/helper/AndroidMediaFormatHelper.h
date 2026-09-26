
#ifndef FPVUE_ANDROIDMEDIAFORMATHELPER_H
#define FPVUE_ANDROIDMEDIAFORMATHELPER_H

#include <media/NdkMediaFormat.h>
#include "../DecoderLevers.h"
#include "../NALU/KeyFrameFinder.hpp"

// Writes the keys a set of levers stands for (DecoderLevers.h owns the mapping).
// Unknown keys are ignored by MediaCodec, so this is safe on every device / Android version.
static void applyDecoderLevers(AMediaFormat* format, const DecoderLevers& levers)
{
    for (const auto& k : decoderFormatKeys(levers))
    {
        AMediaFormat_setInt32(format, k.key, k.value);
    }
}

static void h264_configureAMediaFormat(KeyFrameFinder& kff, AMediaFormat* format)
{
    const auto sps     = kff.getCSD0();
    const auto pps     = kff.getCSD1();
    const auto videoWH = sps.getVideoWidthHeightSPS();
    AMediaFormat_setInt32(format, AMEDIAFORMAT_KEY_WIDTH, videoWH[0]);
    AMediaFormat_setInt32(format, AMEDIAFORMAT_KEY_HEIGHT, videoWH[1]);
    AMediaFormat_setBuffer(format, "csd-0", sps.getData(), (size_t) sps.getSize());
    AMediaFormat_setBuffer(format, "csd-1", pps.getData(), (size_t) pps.getSize());
    MLOGD << "Video WH:" << videoWH[0] << " H:" << videoWH[1];
    // AMediaFormat_setInt32(format,AMEDIAFORMAT_KEY_BIT_RATE,5*1024*1024);
    // AMediaFormat_setInt32(format,AMEDIAFORMAT_KEY_FRAME_RATE,60);
    // AVCProfileBaseline==1
    // AMediaFormat_setInt32(decoder.format,AMEDIAFORMAT_KEY_PROFILE,1);
}

static void h265_configureAMediaFormat(KeyFrameFinder& kff, AMediaFormat* format)
{
    std::vector<uint8_t> buff = {};
    const auto           sps  = kff.getCSD0();
    const auto           pps  = kff.getCSD1();
    const auto           vps  = kff.getVPS();
    buff.reserve(sps.getSize() + pps.getSize() + vps.getSize());
    KeyFrameFinder::appendNaluData(buff, vps);
    KeyFrameFinder::appendNaluData(buff, sps);
    KeyFrameFinder::appendNaluData(buff, pps);
    const auto videoWH = sps.getVideoWidthHeightSPS();
    AMediaFormat_setInt32(format, AMEDIAFORMAT_KEY_WIDTH, videoWH[0]);
    AMediaFormat_setInt32(format, AMEDIAFORMAT_KEY_HEIGHT, videoWH[1]);
    AMediaFormat_setBuffer(format, "csd-0", buff.data(), buff.size());
    MLOGD << "Video WH:" << videoWH[0] << " H:" << videoWH[1];
}

#endif  // FPVUE_ANDROIDMEDIAFORMATHELPER_H
