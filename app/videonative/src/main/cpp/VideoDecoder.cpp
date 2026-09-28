//
// Created by gaeta on 2024-04-01.
//

#include "VideoDecoder.h"

#include <iomanip>
#include <sstream>
#include <unistd.h>
#include <android/trace.h>
#include <ctime>
#include <sstream>
#include "AndroidThreadPrioValues.hpp"
#include "helper/AndroidMediaFormatHelper.h"
#include "helper/NDKThreadHelper.hpp"

#include <vector>

#include <android/native_window_jni.h>
#include <media/NdkMediaCodec.h>

using namespace std::chrono;

VideoDecoder::VideoDecoder(JNIEnv* env)
{
    env->GetJavaVM(&javaVm);
    resetStatistics();
}

void VideoDecoder::setOutputSurface(JNIEnv* env, jobject surface, jint idx)
{
    if (surface == nullptr)
    {
        MLOGD << "Set output null surface idx: " << idx;
        // assert(decoder.window!=nullptr);
        if (decoder.window[idx] == nullptr && decoder.codec[idx] == nullptr)
        {
            // MLOGD<<"Decoder window is already null";
            return;
        }
        std::lock_guard<std::mutex> lock(mMutexInputPipe);
        inputPipeClosed = true;
        releaseDecoder(idx);
        if (decoder.window[idx])
        {
            ANativeWindow_release(decoder.window[idx]);
            decoder.window[idx] = nullptr;
            MLOGD << "Set decoder.window null idx: " << idx;
        }
        resetStatistics();
    }
    else
    {
        MLOGD << "Set output non-null surface idx :" << idx;
        // Throw warning if the surface is set without clearing it first
        assert(decoder.window[idx] == nullptr);
        decoder.window[idx] = ANativeWindow_fromSurface(env, surface);
        // open the input pipe - now the decoder will start as soon as enough data is available
        inputPipeClosed = false;
    }
}

void VideoDecoder::releaseDecoder(int idx)
{
    if (!decoder.configured[idx]) return;
    AMediaCodec_stop(decoder.codec[idx]);
    AMediaCodec_delete(decoder.codec[idx]);
    decoder.codec[idx] = nullptr;
    MLOGD << "Set decoder.codec null idx: " << idx;
    mKeyFrameFinder.reset();
    mAssembler.reset();
    if (idx == 0) mTimeline.reset();   // inputs queued to this decoder never come out
    decoder.configured[idx] = false;
    if (mCheckOutputThread[idx]->joinable())
    {
        mCheckOutputThread[idx]->join();
        mCheckOutputThread[idx].reset();
    }
}

void VideoDecoder::registerOnDecoderRatioChangedCallback(DECODER_RATIO_CHANGED decoderRatioChangedC)
{
    onDecoderRatioChangedCallback = std::move(decoderRatioChangedC);
}

void VideoDecoder::registerOnDecodingInfoChangedCallback(DECODING_INFO_CHANGED_CALLBACK decodingInfoChangedCallback)
{
    onDecodingInfoChangedCallback = std::move(decodingInfoChangedCallback);
}

void VideoDecoder::interpretNALU(const NALU& nalu)
{
    // we need this lock, since the receiving/parsing/feeding does not run on the same thread who sets the input surface
    std::lock_guard<std::mutex> lock(mMutexInputPipe);
    if (mCodec.changed(nalu.IS_H265_PACKET))
    {
        // The air switched H.264 <-> H.265 (RTP 96 <-> 97). A MediaCodec cannot change its MIME type: release both
        // decoders and build new ones from the new codec's first key frames. The windows stay, so the decoder is
        // re-created on the same surface (the XR swapchain), as the X23 rebuild does [docs/xr/decoder-levers.md].
        // The saved SPS/PPS go too, also when nothing was configured yet: an H.264 SPS next to an H.265 VPS would
        // otherwise look like a complete H.265 set.
        MLOGD << "codec changed to " << (nalu.IS_H265_PACKET ? "H.265" : "H.264") << ", rebuilding the decoder";
        releaseDecoder(0);
        releaseDecoder(1);
        mKeyFrameFinder.reset();
        mAssembler.reset();
    }
    IS_H265             = nalu.IS_H265_PACKET;
    decodingInfo.nCodec = IS_H265;
    decodingInfo.nNALU++;
    if (nalu.getSize() <= 4)
    {
        // No data in NALU (e.g at the beginning of a stream)
        return;
    }
    nNALUBytesFed.add(nalu.getSize());
    if (inputPipeClosed)
    {
        MLOGD << "inputPipeClosed.";
        // A feedD thread (e.g. file or udp) thread might be running even tough no output surface was set
        // But at least we can buffer the sps/pps data
        mKeyFrameFinder.saveIfKeyFrame(nalu);
        return;
    }
    // A new SPS (the encoder restarted, e.g. with another resolution) is left to the running decoder, which adapts
    // in place. Rebuilding it on every SPS change was measured slower on a live switch (audit X23 c, withdrawn).
    // '|', not '||': both decoders' flags are consumed in the same pass.
    if (mRecovery.shouldRebuild(0, decoder.configured[0]) | mRecovery.shouldRebuild(1, decoder.configured[1]))
    {
        // A codec errored out and its output thread ended: the picture would stay frozen. Rebuild from the next
        // key frame (audit X23 b, DecoderRecovery.h).
        MLOGE << "decoder failed, rebuilding at the next key frame";
        releaseDecoder(0);
        releaseDecoder(1);
    }
    if (decoder.configured[0] || decoder.configured[1])
    {
        if (mAuAggregationActive)
        {
            mAssembler.push(
                au::classify(
                    nalu.getData(), nalu.getSize(), IS_H265, nalu.endOfAccessUnit, nalu.creationTime, nalu.rtpTag),
                [this](const uint8_t* d, size_t n, std::chrono::steady_clock::time_point t, bool cfg, const RtpTag& tag)
                { feedBoth(d, n, t, IS_H265 && cfg, tag); });
        }
        else
        {
            feedBoth(nalu.getData(),
                     nalu.getSize(),
                     nalu.creationTime,
                     IS_H265 && (nalu.isSPS() || nalu.isPPS() || nalu.isVPS()),
                     nalu.rtpTag);
        }
        decodingInfo.nNALUSFeeded++;
        // manually feeding AUDs doesn't seem to change anything for high latency streams
        // Only for the x264 sw encoded example stream it might improve latency slightly
        // if(!nalu.IS_H265_PACKET && nalu.get_nal_unit_type()==NAL_UNIT_TYPE_CODED_SLICE_NON_IDR){
        // MLOGD<<"Feeding special AUD";
        // feedDecoder(NALU::createExampleH264_AUD());
        //}
    }
    else
    {
        // Store sps,pps, vps(H265 only)
        // As soon as enough data has been buffered to initialize the decoder,do so.
        mKeyFrameFinder.saveIfKeyFrame(nalu);
        if (mKeyFrameFinder.allKeyFramesAvailable(IS_H265))
        {
            MLOGD << "Configuring decoder...";
            configureStartDecoder(0);
            configureStartDecoder(1);
            if (mRecovery.configureFailed(decoder.configured[0] || decoder.configured[1],
                                          decoder.window[0] != nullptr || decoder.window[1] != nullptr))
            {
                // Do not retry on every following NALU with the same key frames (audit X23 a).
                MLOGE << "decoder not configured, retrying at the next key frame";
                mKeyFrameFinder.reset();
            }
        }
    }
}

void VideoDecoder::configureStartDecoder(int idx)
{
    if (decoder.window[idx] == nullptr) return;
    DecoderLevers wanted;
    {
        std::lock_guard<std::mutex> lock(mLeversMutex);
        wanted = mLevers;
    }
    // A decoder may reject vendor keys or a component at configure() or only at start(); either way
    // fall back to the base set instead of leaving the stream undecoded.
    bool started = configureAndStart(idx, wanted);
    if (!started && wanted.hasExtras())
    {
        MLOGE << "Decoder rejected levers [" << leversSummary(wanted) << "], retrying without the extras";
        started = configureAndStart(idx, wanted.onlyBase());
    }
    if (!started)
    {
        MLOGE << "Cannot configure decoder";
        return;
    }
    mAuAggregationActive = wanted.auAggregation;
    mAssembler.reset();
    mRecovery.configured(idx);
    mCheckOutputThread[idx] = std::make_unique<std::thread>(&VideoDecoder::checkOutputLoop, this, idx);
    NDKThreadHelper::setName(mCheckOutputThread[idx]->native_handle(), "LLDCheckOutput");
    decoder.configured[idx] = true;
}

bool VideoDecoder::configureAndStart(int idx, const DecoderLevers& levers)
{
    const std::string MIME             = IS_H265 ? "video/hevc" : "video/avc";
    std::string       name             = "default " + MIME;
    bool              componentCreated = false;
    decoder.codec[idx]                 = nullptr;
    for (const auto& candidate : componentCandidates(levers, IS_H265))
    {
        decoder.codec[idx] = AMediaCodec_createCodecByName(candidate.c_str());
        if (decoder.codec[idx] == nullptr) continue;
        name             = candidate;
        componentCreated = candidate == lowLatencyComponentName(IS_H265);
        break;
    }
    if (decoder.codec[idx] == nullptr)
    {
        decoder.codec[idx] = AMediaCodec_createDecoderByType(MIME.c_str());
    }
    if (decoder.codec[idx] == nullptr) return false;

    AMediaFormat* format = AMediaFormat_new();
    AMediaFormat_setString(format, AMEDIAFORMAT_KEY_MIME, MIME.c_str());
    if (IS_H265)
    {
        h265_configureAMediaFormat(mKeyFrameFinder, format);
    }
    else
    {
        h264_configureAMediaFormat(mKeyFrameFinder, format);
    }
    applyDecoderLevers(format, levers);
    // The SPS the decoder is configured with, as hex: scripts/quest/sps_vui.py reads it and says whether the stream
    // signals max_num_reorder_frames = 0 (VUI bitstream_restriction), i.e. whether the decoder may hold frames.
    {
        const NALU&        sps = mKeyFrameFinder.getCSD0();
        std::ostringstream hex;
        hex << std::hex << std::setfill('0');
        for (size_t i = 0; i < static_cast<size_t>(sps.getSize()); i++) hex << std::setw(2) << static_cast<int>(sps.getData()[i]);
        MLOGD << "csd-0 " << hex.str();
    }
    MLOGD << "Configuring decoder " << name << ": " << AMediaFormat_toString(format);
    const auto status = AMediaCodec_configure(decoder.codec[idx], format, decoder.window[idx], nullptr, 0);
    AMediaFormat_delete(format);
    if (status != AMEDIA_OK)
    {
        MLOGE << "AMediaCodec_configure failed: " << (int) status;
        AMediaCodec_delete(decoder.codec[idx]);
        decoder.codec[idx] = nullptr;
        return false;
    }
    const auto startStatus = AMediaCodec_start(decoder.codec[idx]);
    if (startStatus != AMEDIA_OK)
    {
        MLOGE << "AMediaCodec_start failed: " << (int) startStatus;
        AMediaCodec_delete(decoder.codec[idx]);
        decoder.codec[idx] = nullptr;
        return false;
    }
    std::lock_guard<std::mutex> lock(mLeversMutex);
    mAppliedSummary = name + " | " + leversSummary(appliedLevers(levers, componentCreated));
    return true;
}

void VideoDecoder::feedBoth(const uint8_t*                        data,
                            size_t                                size,
                            std::chrono::steady_clock::time_point creationTime,
                            bool                                  codecConfig,
                            const RtpTag&                         tag)
{
    feedDecoder(data, size, creationTime, codecConfig, 0, tag);
    feedDecoder(data, size, creationTime, codecConfig, 1, tag);
}

void VideoDecoder::feedDecoder(const uint8_t*                        data,
                               size_t                                size,
                               std::chrono::steady_clock::time_point creationTime,
                               bool                                  codecConfig,
                               int                                   idx,
                               const RtpTag&                         tag)
{
    if (!decoder.codec[idx]) return;
    const auto now          = std::chrono::steady_clock::now();
    const auto deltaParsing = now - creationTime;
    while (true)
    {
        const auto index = AMediaCodec_dequeueInputBuffer(decoder.codec[idx], BUFFER_TIMEOUT_US);
        if (index >= 0)
        {
            // getInputBuffer returns NULL without touching the size when the codec is in an error
            // state; an uninitialised size then passes the check below and memcpy writes to NULL.
            size_t   inputBufferSize = 0;
            uint8_t* buf             = AMediaCodec_getInputBuffer(decoder.codec[idx], (size_t) index, &inputBufferSize);
            if (buf == nullptr)
            {
                MLOGE << "No input buffer for index " << (int) index << " (codec error)";
                return;
            }
            // I have not seen any case where the input buffer returned by MediaCodec is too small to hold the NALU
            // But better be safe than crashing with a memory exception
            if (size > inputBufferSize)
            {
                MLOGE << "Input buffer too small for " << size << " bytes, dropped";
                ++mInputTooBig;
                return;
            }

            const int flag = codecConfig ? AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG : 0;
            std::memcpy(buf, data, size);
            const uint64_t presentationTimeUS =
                (uint64_t) duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
            AMediaCodec_queueInputBuffer(
                decoder.codec[idx], (size_t) index, 0, size, presentationTimeUS, flag);
            if (idx == 0 && !codecConfig) mTimeline.onQueued(static_cast<int64_t>(presentationTimeUS), tag);
            waitForInputB.add(steady_clock::now() - now);
            parsingTime.add(deltaParsing);
            return;
        }
        else if (index == AMEDIACODEC_INFO_TRY_AGAIN_LATER)
        {
            // just try again. But if we had no success in the last 1 second,log a warning and return.
            const auto elapsedTimeTryingForBuffer = std::chrono::steady_clock::now() - now;
            if (elapsedTimeTryingForBuffer > std::chrono::seconds(1))
            {
                // Since OpenHD provides a lossy link it is really unlikely, but possible that we somehow 'break' the
                // codec by feeding corrupt data. It will probably recover itself as soon as we feed enough valid data
                // though;
                MLOGE << "AMEDIACODEC_INFO_TRY_AGAIN_LATER for more than 1 second "
                      << MyTimeHelper::R(elapsedTimeTryingForBuffer) << "return.";
                return;
            }
        }
        else
        {
            // Something went wrong. But we will feed the next NALU soon anyways
            MLOGD << "dequeueInputBuffer idx " << (int) index << "return.";
            return;
        }
    }
}

void VideoDecoder::checkOutputLoop(int idx)
{
    if (idx == 0) mOutputTid = gettid();
    NDKThreadHelper::setProcessThreadPriorityAttachDetach(javaVm, -16, "DecoderCheckOutput");
    AMediaCodecBufferInfo info;
    bool                  decoderSawEOS          = false;
    bool                  decoderProducedUnknown = false;
    while (!decoderSawEOS && !decoderProducedUnknown)
    {
        if (!decoder.codec[idx]) break;
        const ssize_t index = AMediaCodec_dequeueOutputBuffer(decoder.codec[idx], &info, BUFFER_TIMEOUT_US);
        if (index >= 0)
        {
            const auto    now   = steady_clock::now();
            const int64_t nowUS = (int64_t) duration_cast<microseconds>(now.time_since_epoch()).count();
            // the timestamp for releasing the buffer is in NS, just release as fast as possible (e.g. now)
            // https://android.googlesource.com/platform/frameworks/av/+/master/media/ndk/NdkMediaCodec.cpp
            //-> renderOutputBufferAndRelease which is in
            // https://android.googlesource.com/platform/frameworks/av/+/3fdb405/media/libstagefright/MediaCodec.cpp
            //-> Message kWhatReleaseOutputBuffer -> onReleaseOutputBuffer
            //  also https://android.googlesource.com/platform/frameworks/native/+/5c1139f/libs/gui/SurfaceTexture.cpp
            if (!decoder.codec[idx]) break;
            AMediaCodec_releaseOutputBuffer(decoder.codec[idx], (size_t) index, true);
            // but the presentationTime is in US
            if (idx == 0)
            {
                timespec ready{};
                clock_gettime(CLOCK_MONOTONIC, &ready);
                const int64_t readyNs = static_cast<int64_t>(ready.tv_sec) * 1000000000LL + ready.tv_nsec;
                mFrameReady.add(readyNs);
                mTimeline.onDecoded(info.presentationTimeUs, readyNs);
                if (ATrace_isEnabled())  // marks the phase meter's frame-ready time in a system trace
                {
                    ATrace_beginSection("ppxr_frame_ready");
                    ATrace_endSection();
                }
                decodingTime.add(std::chrono::microseconds(nowUS - info.presentationTimeUs));
                nDecodedFrames.add(1);
            }
            if (info.flags & AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM)
            {
                MLOGD << "Decoder saw EOS";
                decoderSawEOS = true;
                continue;
            }
        }
        else if (index == AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED)
        {
            auto format = AMediaCodec_getOutputFormat(decoder.codec[idx]);
            int  width = 0, height = 0;
            AMediaFormat_getInt32(format, AMEDIAFORMAT_KEY_WIDTH, &width);
            AMediaFormat_getInt32(format, AMEDIAFORMAT_KEY_HEIGHT, &height);
            MLOGD << "Actual Width and Height in output " << width << "," << height;
            if (idx == 0 && onDecoderRatioChangedCallback != nullptr && width != 0 && height != 0)
            {
                onDecoderRatioChangedCallback({width, height});
            }
            MLOGD << "AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED " << width << " " << height << " "
                  << AMediaFormat_toString(format);
        }
        else if (index == AMEDIACODEC_INFO_OUTPUT_BUFFERS_CHANGED)
        {
            MLOGD << "AMEDIACODEC_INFO_OUTPUT_BUFFERS_CHANGED";
        }
        else if (index == AMEDIACODEC_INFO_TRY_AGAIN_LATER)
        {
            // MLOGD<<"AMEDIACODEC_INFO_TRY_AGAIN_LATER";
        }
        else
        {
            // AMediaCodec_stop() was called (a release), or the codec failed. Flag it either way: a release is
            // followed by a fresh configure, which clears the flag (DecoderRecovery::configured).
            MLOGD << "dequeueOutputBuffer idx: " << (int) index << " .Exit.";
            mRecovery.outputFailed(idx);
            decoderProducedUnknown = true;
            continue;
        }
        // every 2 seconds recalculate the current fps and bitrate
        const auto now   = steady_clock::now();
        const auto delta = now - decodingInfo.lastCalculation;
        if (idx == 0 && delta > DECODING_INFO_RECALCULATION_INTERVAL)
        {
            decodingInfo.lastCalculation = steady_clock::now();
            decodingInfo.currentFPS =
                (float) nDecodedFrames.getDeltaSinceLastCall() / (float) duration_cast<seconds>(delta).count();
            decodingInfo.currentKiloBitsPerSecond =
                ((float) nNALUBytesFed.getDeltaSinceLastCall() / duration_cast<seconds>(delta).count()) / 1024.0f *
                8.0f;
            // and recalculate the avg latencies. If needed,also print the log.
            decodingInfo.avgDecodingTime_ms      = decodingTime.getAvg_ms();
            decodingInfo.avgParsingTime_ms       = parsingTime.getAvg_ms();
            decodingInfo.avgWaitForInputBTime_ms = waitForInputB.getAvg_ms();
            decodingInfo.nDecodedFrames          = nDecodedFrames.getAbsolute();
            printAvgLog();
            if (onDecodingInfoChangedCallback != nullptr)
            {
                onDecodingInfoChangedCallback(decodingInfo);
            }
        }
    }
    MLOGD << "Exit CheckOutputLoop";
}

void VideoDecoder::printAvgLog()
{
    if (PRINT_DEBUG_INFO)
    {
        auto now = steady_clock::now();
        if ((now - lastLog) > TIME_BETWEEN_LOGS)
        {
            lastLog = now;
            std::ostringstream frameLog;
            frameLog << std::fixed;
            float avgDecodingLatencySum =
                decodingInfo.avgParsingTime_ms + decodingInfo.avgWaitForInputBTime_ms + decodingInfo.avgDecodingTime_ms;
            frameLog << "......................Decoding Latency Averages......................"
                     << "\nParsing:" << decodingInfo.avgParsingTime_ms
                     << " | WaitInputBuffer:" << decodingInfo.avgWaitForInputBTime_ms
                     << " | Decoding:" << decodingInfo.avgDecodingTime_ms
                     << " | Decoding Latency Sum:" << avgDecodingLatencySum << "\nN NALUS:" << decodingInfo.nNALU
                     << " | N NALUES feeded:" << decodingInfo.nNALUSFeeded
                     << " | N Decoded Frames:" << nDecodedFrames.getAbsolute() << "\nFPS:" << decodingInfo.currentFPS
                     << " | Codec:" << (decodingInfo.nCodec ? "H265" : "H264");
            MLOGD << frameLog.str();
        }
    }
}

void VideoDecoder::resetStatistics()
{
    nDecodedFrames.reset();
    nNALUBytesFed.reset();
    parsingTime.reset();
    waitForInputB.reset();
    decodingTime.reset();
    decodingInfo = {};
}
