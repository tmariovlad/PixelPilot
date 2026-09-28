//
// Created by Constantin on 24.01.2018.
//
#include "H26XParser.h"
#include <android/log.h>
#include <endian.h>
#include <chrono>
#include <cstring>
#include <thread>

H26XParser::H26XParser(NALU_DATA_CALLBACK onNewNALU)
    : onNewNALU(std::move(onNewNALU)),
      mDecodeRTP(std::bind(
          &H26XParser::onNewNaluDataExtracted,
          this,
          std::placeholders::_1,
          std::placeholders::_2,
          std::placeholders::_3,
          std::placeholders::_4))
{
}

void H26XParser::reset()
{
    mDecodeRTP.reset();
    mCodec.reset();
    nParsedNALUs               = 0;
    nParsedKonfigurationFrames = 0;
}

void H26XParser::parse_rtp_stream(const uint8_t* rtp_data, const size_t data_length)
{
    const RTP::RTPPacket rtpPacket(rtp_data, data_length);
    const auto           payload = rtpPacket.header.payload;
    if (payload != RTP_PAYLOAD_TYPE_H264 && payload != RTP_PAYLOAD_TYPE_H265) return;
    IS_H265 = payload == RTP_PAYLOAD_TYPE_H265;
    if (mCodec.changed(IS_H265))
    {
        // A live H.264 <-> H.265 switch: the old encoder stopped mid-NALU. Drop its half-built bytes, or the first
        // fragment end of the new codec would complete them into a NALU of the wrong codec (CodecSwitch.h).
        mDecodeRTP.reset();
    }
    if (IS_H265)
    {
        mDecodeRTP.parseRTPH265toNALU(rtp_data, data_length);
    }
    else
    {
        mDecodeRTP.parseRTPH264toNALU(rtp_data, data_length);
    }
}

void H26XParser::onNewNaluDataExtracted(
    const std::chrono::steady_clock::time_point creation_time,
    const uint8_t*                              nalu_data,
    const int                                   nalu_data_size,
    const bool                                  end_of_access_unit)
{
    NALU nalu(nalu_data, nalu_data_size, IS_H265, creation_time, end_of_access_unit);
    newNaluExtracted(nalu);
}

void H26XParser::newNaluExtracted(const NALU& nalu)
{
    if (onNewNALU != nullptr)
    {
        onNewNALU(nalu);
    }
    nParsedNALUs++;
    const bool sps_or_pps = nalu.isSPS() || nalu.isPPS();
    if (sps_or_pps)
    {
        nParsedKonfigurationFrames++;
    }
}
