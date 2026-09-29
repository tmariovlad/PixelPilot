#include <android/trace.h>
#include "VideoPlayer.h"
#include <android/asset_manager_jni.h>
#include <android/log.h>
#include <android/native_window.h>
#include <android/native_window_jni.h>
#include <jni.h>
#include <atomic>
#include <chrono>
#include <fstream>
#include "AndroidThreadPrioValues.hpp"
#include "helper/NDKHelper.hpp"
#include "helper/NDKThreadHelper.hpp"

#define TAG "pixelpilot"

// Key-frame requests to the air unit (IdrRequester), as counters for a system trace: ok and failed so far.
static void traceIdrRequest(bool ok)
{
    static std::atomic<int32_t> nOk{0}, nFailed{0};
    const int32_t n = ok ? ++nOk : ++nFailed;
    if (__builtin_available(android 29, *))
    {
        if (ATrace_isEnabled()) ATrace_setCounter(ok ? "ppxr_idr_req_ok" : "ppxr_idr_req_failed", n);
    }
}

static int64_t steadyNowMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

// Slices held back by FreezeUntilIdr so far, as a counter for a system trace.
static void traceFrozen(uint32_t dropped)
{
    if (__builtin_available(android 29, *))
    {
        if (ATrace_isEnabled()) ATrace_setCounter("ppxr_frozen_slices", dropped);
    }
}

VideoPlayer::VideoPlayer(JNIEnv* env, jobject context)
    : mParser{std::bind(&VideoPlayer::onNewNALU, this, std::placeholders::_1)}, videoDecoder(env)
{
    env->GetJavaVM(&javaVm);
    mIdrRequester.setOnResult(traceIdrRequest);
    mParser.setOnPacketLoss(
        [this](int)
        {
            mFreezeUntilIdr.onLoss(steadyNowMs());
            mIdrRequester.notifyLoss();
        });
    videoDecoder.registerOnDecoderRatioChangedCallback(
        [this](const VideoRatio ratio)
        {
            const bool changed      = ratio != this->latestVideoRatio;
            this->latestVideoRatio  = ratio;
            latestVideoRatioChanged = changed;
        });
    videoDecoder.registerOnDecodingInfoChangedCallback(
        [this](const DecodingInfo info)
        {
            const bool changed        = info != this->latestDecodingInfo;
            this->latestDecodingInfo  = info;
            latestDecodingInfoChanged = changed;
        });
}

static int write_callback(int64_t offset, const void* buffer, size_t size, void* token)
{
    FILE* f = (FILE*) token;
    fseek(f, offset, SEEK_SET);
    return fwrite(buffer, 1, size, f) != size;
}

void VideoPlayer::processQueue()
{
    ::FILE*           fout = fdopen(dvr_fd, "wb");
    MP4E_mux_t*       mux  = MP4E_open(0 /*sequential_mode*/, dvr_mp4_fragmentation, fout, write_callback);
    mp4_h26x_writer_t mp4wr;
    float             framerate = 0;
    if (mux == nullptr)
    {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "dvr open failed");
        return;
    }

    while (true)
    {
        last_dvr_write = get_time_ms();
        std::unique_lock<std::mutex> lock(mtx);
        cv.wait(lock, [this] { return !naluQueue.empty() || stopFlag; });
        if (stopFlag)
        {
            break;
        }
        if (!naluQueue.empty())
        {
            if (framerate == 0)
            {
                if (latestDecodingInfo.currentFPS <= 0)
                {
                    continue;
                }
                const bool is_h265 = naluQueue.front().is_h265;
                if (MP4E_STATUS_OK !=
                    mp4_h26x_write_init(&mp4wr, mux, latestVideoRatio.width, latestVideoRatio.height, is_h265))
                {
                    __android_log_print(ANDROID_LOG_DEBUG, TAG, "error: mp4_h26x_write_init failed");
                }
                framerate = latestDecodingInfo.currentFPS;
                __android_log_print(
                    ANDROID_LOG_DEBUG,
                    TAG,
                    "mp4 init with fps=%.2f, res=%dx%d, hevc=%d",
                    framerate,
                    latestVideoRatio.width,
                    latestVideoRatio.height,
                    is_h265);
            }
            DvrNalu nalu = std::move(naluQueue.front());
            naluQueue.pop();
            lock.unlock();
            // Process the NALU
            auto res = mp4_h26x_write_nal(&mp4wr, nalu.data.data(), (int) nalu.data.size(), 90000 / framerate);
            if (MP4E_STATUS_OK != res)
            {
                __android_log_print(ANDROID_LOG_DEBUG, TAG, "mp4_h26x_write_nal failed with %d", res);
            }
        }
    }

    MP4E_close(mux);
    mp4_h26x_write_close(&mp4wr);
    if (fout)
    {
        fclose(fout);
        fout = NULL;
    }
    dvr_fd = -1;
    __android_log_print(ANDROID_LOG_DEBUG, TAG, "dvr thread done");
}

// Per-packet arrival marks for a system trace (transport analysis: arrival time vs the RTP capture
// clock, packet spread within a frame), plus the payload type once per frame (96 H.264 / 97 H.265: which codec a
// segment carried, e.g. around a live codec switch; rtp_seq.codec_segments). No cost unless a trace is recording.
static void traceRtpArrival(uint16_t sequence, uint32_t timestamp, uint8_t payloadType)
{
    if (__builtin_available(android 29, *))
    {
        if (!ATrace_isEnabled()) return;
        ATrace_setCounter("ppxr_rtp_seq", sequence);
        ATrace_setCounter("ppxr_rtp_ts", timestamp);
        static uint32_t lastFrameTimestamp = 0;   // only the receive thread calls this
        if (payloadType != RTP_PAYLOAD_TYPE_AUDIO && timestamp != lastFrameTimestamp)
        {
            lastFrameTimestamp = timestamp;
            ATrace_setCounter("ppxr_rtp_pt", payloadType);
        }
    }
}

// Not yet parsed bit stream (e.g. raw h264 or rtp data)
void VideoPlayer::onNewRTPData(const uint8_t* data, const std::size_t data_length)
{
    // Parse the RTP packet
    const RTP::RTPPacket rtpPacket(data, data_length);
    uint16_t             idx = rtpPacket.header.getSequence();
    traceRtpArrival(rtpPacket.header.getSequence(), rtpPacket.header.getTimestamp(), rtpPacket.header.payload);

    // Define the callback based on payload type
    auto callback = [&](const uint8_t* packet_data, std::size_t packet_length)
    {
        if (rtpPacket.header.payload == RTP_PAYLOAD_TYPE_AUDIO)
        {
            audioDecoder.enqueueAudio(packet_data, packet_length);
        }
        else
        {
            mParser.parse_rtp_stream(packet_data, packet_length);
        }
    };

    // Process the packet using the queue
    if (rtpPacket.header.payload == RTP_PAYLOAD_TYPE_AUDIO)
    {
        mBufferedPacketQueueAudio.processPacket(idx, data, data_length, callback);
    }
    else
    {
        mBufferedPacketQueueVideo.processPacket(idx, data, data_length, callback);
    }
}

void VideoPlayer::onNewNALU(const NALU& nalu)
{
    if (nalu.getSize() > 4 && !mFreezeUntilIdr.admit(nalu.get_nal_unit_type(), nalu.IS_H265_PACKET, steadyNowMs()))
    {
        traceFrozen(mFreezeUntilIdr.dropped());
        return;
    }
    videoDecoder.interpretNALU(nalu);
    if (dvr_fd <= 0 || latestDecodingInfo.currentFPS <= 0)
    {
        return;
    }
    // The writer thread outlives this call, so hand it an owning copy.
    enqueueNALU(DvrNalu{std::vector<uint8_t>(nalu.getData(), nalu.getData() + nalu.getSize()),
                        nalu.IS_H265_PACKET});
}

void VideoPlayer::setVideoSurface(JNIEnv* env, jobject surface, jint i)
{
    // reset the parser so the statistics start again from 0
    //  mParser.reset();
    // set the jni object for settings
    videoDecoder.setOutputSurface(env, surface, i);
}

std::vector<int> VideoPlayer::latencyCriticalThreadIds()
{
    std::vector<int> ids;
    if (mUDPReceiver && mUDPReceiver->threadId()) ids.push_back(mUDPReceiver->threadId());
    if (mUDSReceiver && mUDSReceiver->threadId()) ids.push_back(mUDSReceiver->threadId());
    if (videoDecoder.outputThreadId()) ids.push_back(videoDecoder.outputThreadId());
    return ids;
}

void VideoPlayer::start(JNIEnv* env, jobject androidContext)
{
    AAssetManager* assetManager = NDKHelper::getAssetManagerFromContext2(env, androidContext);
    // mParser.setLimitFPS(-1); //Default: Real time !
    const int VS_PORT = 5600;
    mUDPReceiver.release();
    mUDPReceiver = std::make_unique<UDPReceiver>(
        javaVm,
        VS_PORT,
        "UdpReceiver",
        -16,
        [this](const uint8_t* data, size_t data_length) { onNewRTPData(data, data_length); },
        WANTED_UDP_RCVBUF_SIZE);
    mUDPReceiver->setForwarding(mForwardIP, mForwardPort, mForwardEnabled);
    mUDPReceiver->startReceiving();

    mUDSReceiver.release();
    // build the abstract socket name ("\0my_socket")
    auto udsName = std::string("\0my_socket", sizeof("\0my_socket") - 1);

    // now construct your receiver with that
    mUDSReceiver = std::make_unique<UDSReceiver>(
        javaVm,
        udsName,   // abstract socket name
        "UDS‑Rx",  // thread name
        -16,       // Android priority
        [this](const uint8_t* data, size_t data_length) { onNewRTPData(data, data_length); },
        WANTED_UDP_RCVBUF_SIZE  // your desired recv‑buffer size
    );

    mUDSReceiver->startReceiving();
}

void VideoPlayer::stop(JNIEnv* env, jobject androidContext)
{
    if (mUDPReceiver)
    {
        mUDPReceiver->stopReceiving();
        mUDPReceiver.reset();
    }
    if (mUDSReceiver)
    {
        mUDSReceiver->stopReceiving();
        mUDSReceiver.reset();
    }

    audioDecoder.stopAudio();
}

std::string VideoPlayer::getInfoString() const
{
    std::stringstream ss;
    if (mUDPReceiver)
    {
        ss << "Listening for video on port " << mUDPReceiver->getPort();
        ss << "\nReceived: " << mUDPReceiver->getNReceivedBytes() << "B"
           << " | parsed frames: ";
        // << mParser.nParsedNALUs << " | key frames: " << mParser.nParsedKonfigurationFrames;
    }
    else if (mUDSReceiver)
    {
        ss << "Listening for video on socket " << mUDSReceiver->getSourcePath();
        ss << "\nReceived: " << mUDSReceiver->getNReceivedBytes() << "B"
           << " | parsed frames: ";
        // << mParser.nParsedNALUs << " | key frames: " << mParser.nParsedKonfigurationFrames;
    }
    else
    {
        ss << "Not receiving udp raw / rtp / rtsp";
    }
    return ss.str();
}

void VideoPlayer::startDvr(JNIEnv* env, jint fd, jint dvr_fmp4_enabled)
{
    dvr_fd                = dup(fd);
    dvr_mp4_fragmentation = dvr_fmp4_enabled;
    __android_log_print(ANDROID_LOG_DEBUG, TAG, "dvr_fd=%d", dvr_fd);
    if (dvr_fd == -1)
    {
        __android_log_print(ANDROID_LOG_DEBUG, TAG, "Failed to duplicate dvr file descriptor");
        return;
    }
    startProcessing();
}

void VideoPlayer::stopDvr()
{
    __android_log_print(ANDROID_LOG_DEBUG, TAG, "Stop dvr");
    stopProcessing();
}

void VideoPlayer::setForwarding(const std::string& ip, int port, bool enabled)
{
    mForwardIP = ip;
    mForwardPort = port;
    mForwardEnabled = enabled;
    if (mUDPReceiver)
    {
        mUDPReceiver->setForwarding(ip, port, enabled);
    }
}

//----------------------------------------------------JAVA
// bindings---------------------------------------------------------------
#define JNI_METHOD(return_type, method_name) \
    JNIEXPORT return_type JNICALL Java_com_openipc_videonative_VideoPlayer_##method_name

inline jlong jptr(VideoPlayer* videoPlayerN)
{
    return reinterpret_cast<intptr_t>(videoPlayerN);
}

inline VideoPlayer* native(jlong ptr)
{
    return reinterpret_cast<VideoPlayer*>(ptr);
}

extern "C"
{
    extern "C" JNIEXPORT jlong JNICALL
    Java_com_openipc_videonative_VideoPlayer_nativeInitialize(JNIEnv* env, jclass clazz, jobject context)
    {
        auto* p = new VideoPlayer(env, context);
        return jptr(p);
    }

    JNI_METHOD(void, nativeFinalize)
    (JNIEnv* env, jclass jclass1, jlong videoPlayerN)
    {
        VideoPlayer* p = native(videoPlayerN);
        delete (p);
    }

    JNI_METHOD(void, nativeStart)
    (JNIEnv* env, jclass jclass1, jlong videoPlayerN, jobject androidContext)
    {
        native(videoPlayerN)->start(env, androidContext);
    }

    JNI_METHOD(void, nativeStop)
    (JNIEnv* env, jclass jclass1, jlong videoPlayerN, jobject androidContext)
    {
        native(videoPlayerN)->stop(env, androidContext);
    }

    JNI_METHOD(void, nativeSetUdpForwarding)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jstring ipStr, jint port, jboolean enabled)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p)
        {
            const char* ip = env->GetStringUTFChars(ipStr, nullptr);
            std::string ip_cpp(ip);
            env->ReleaseStringUTFChars(ipStr, ip);
            p->setForwarding(ip_cpp, port, enabled);
        }
    }

    JNI_METHOD(void, nativeSetDecoderLevers)
    (JNIEnv* env,
     jclass jclass1,
     jlong nativeInstance,
     jboolean lowLatency,
     jboolean pictureOrder,
     jboolean operatingRate,
     jboolean preferLowLatencyComponent,
     jboolean auAggregation,
     jint     debugKeyMask,
     jstring  componentName)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p)
        {
            DecoderLevers l;
            l.lowLatency                = lowLatency;
            l.pictureOrder              = pictureOrder;
            l.operatingRate             = operatingRate;
            l.preferLowLatencyComponent = preferLowLatencyComponent;
            l.auAggregation             = auAggregation;
            l.keyMask                   = static_cast<uint32_t>(debugKeyMask);
            if (componentName != nullptr)
            {
                const char* chars = env->GetStringUTFChars(componentName, nullptr);
                l.componentName   = chars;
                env->ReleaseStringUTFChars(componentName, chars);
            }
            p->setDecoderLevers(l);
        }
    }

    JNI_METHOD(void, nativeSetFreezeUntilIdr)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jboolean freeze)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p) p->setFreezeUntilIdr(freeze);
    }

    JNI_METHOD(void, nativeSetRequestIdrOnLoss)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jboolean request, jint minIntervalMs)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p) p->setRequestIdrOnLoss(request, minIntervalMs);
    }

    JNI_METHOD(void, nativeSetFeedIncompleteFrames)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jboolean feed)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p) p->setFeedIncompleteFrames(feed);
    }

    JNI_METHOD(void, nativeSetTightReorder)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jboolean tight)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p) p->setTightReorder(tight);
    }

    JNI_METHOD(jintArray, nativeGetLatencyCriticalThreadIds)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer*           p   = native(nativeInstance);
        const std::vector<int> ids = p ? p->latencyCriticalThreadIds() : std::vector<int>{};
        jintArray              out = env->NewIntArray(static_cast<jsize>(ids.size()));
        if (!ids.empty()) env->SetIntArrayRegion(out, 0, static_cast<jsize>(ids.size()), ids.data());
        return out;
    }

    JNI_METHOD(jstring, nativeGetDecoderSummary)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer* p = native(nativeInstance);
        return env->NewStringUTF(p ? p->getDecoderSummary().c_str() : "");
    }

    JNI_METHOD(jlongArray, nativeDrainFrameReadyTimes)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer*               p     = native(nativeInstance);
        const std::vector<int64_t> times = p ? p->drainFrameReadyTimes() : std::vector<int64_t>{};
        jlongArray                 out   = env->NewLongArray(static_cast<jsize>(times.size()));
        if (!times.empty())
            env->SetLongArrayRegion(out, 0, static_cast<jsize>(times.size()),
                                    reinterpret_cast<const jlong*>(times.data()));
        return out;
    }

    // Decoded frames for the Stats page, 4 longs each: ssrc, RTP timestamp, complete ns, decoded ns (CLOCK_MONOTONIC).
    JNI_METHOD(jlongArray, nativeDrainFrameTimes)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer*                  p      = native(nativeInstance);
        const std::vector<FrameTimes> frames = p ? p->drainFrameTimes() : std::vector<FrameTimes>{};
        std::vector<jlong>            packed;
        packed.reserve(frames.size() * 4);
        for (const FrameTimes& f : frames)
        {
            packed.push_back(f.ssrc);
            packed.push_back(f.ts);
            packed.push_back(f.completeNs);
            packed.push_back(f.decodedNs);
        }
        jlongArray out = env->NewLongArray(static_cast<jsize>(packed.size()));
        if (!packed.empty()) env->SetLongArrayRegion(out, 0, static_cast<jsize>(packed.size()), packed.data());
        return out;
    }

    // Cumulative counters: IDR requests ok, IDR requests failed, slices frozen until an IDR, decoder rebuilds,
    // codec switches (the first three first: StatsCollector reads [0..2], HealthMonitor all five).
    JNI_METHOD(jlongArray, nativeGetLeverCounters)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer* p     = native(nativeInstance);
        const jlong  v[5]  = {p ? static_cast<jlong>(p->idrRequestsOk()) : 0,
                              p ? static_cast<jlong>(p->idrRequestsFailed()) : 0,
                              p ? static_cast<jlong>(p->frozenSlices()) : 0,
                              p ? static_cast<jlong>(p->decoderRebuilds()) : 0,
                              p ? static_cast<jlong>(p->codecSwitches()) : 0};
        jlongArray   out   = env->NewLongArray(5);
        env->SetLongArrayRegion(out, 0, 5, v);
        return out;
    }

    JNI_METHOD(void, nativeSetVideoSurface)
    (JNIEnv* env, jclass jclass1, jlong videoPlayerN, jobject surface, jint index)
    {
        native(videoPlayerN)->setVideoSurface(env, surface, index);
    }

    JNI_METHOD(jstring, getVideoInfoString)
    (JNIEnv* env, jclass jclass1, jlong testReceiverN)
    {
        VideoPlayer* p   = native(testReceiverN);
        jstring      ret = env->NewStringUTF(p->getInfoString().c_str());
        return ret;
    }

    JNI_METHOD(jboolean, anyVideoDataReceived)
    (JNIEnv* env, jclass jclass1, jlong testReceiverN)
    {
        VideoPlayer* p = native(testReceiverN);

        bool ret{false};

        if (p->mUDPReceiver != nullptr)
        {
            ret |= (p->mUDPReceiver->getNReceivedBytes() > 0);
        }
        if (p->mUDSReceiver != nullptr)
        {
            ret |= (p->mUDSReceiver->getNReceivedBytes() > 0);
        }

        return (jboolean) ret;
    }

    JNI_METHOD(jboolean, receivingVideoButCannotParse)
    (JNIEnv* env, jclass jclass1, jlong testReceiverN)
    {
        VideoPlayer* p = native(testReceiverN);
        //    if(p->mUDPReceiver){
        //        return (jboolean) (p->mUDPReceiver->getNReceivedBytes() > 1024 * 1024 && p->mParser.nParsedNALUs ==
        //        0);
        //    }
        return (jboolean) false;
    }

    JNI_METHOD(jboolean, anyVideoBytesParsedSinceLastCall)
    (JNIEnv* env, jclass jclass1, jlong testReceiverN)
    {
        VideoPlayer* p              = native(testReceiverN);
        long         nalusSinceLast = 0;  // p->mParser.nParsedNALUs - p->nNALUsAtLastCall;
        p->nNALUsAtLastCall += nalusSinceLast;
        return (jboolean) (nalusSinceLast > 0);
    }

    JNI_METHOD(void, nativeCallBack)
    (JNIEnv* env, jclass jclass1, jobject videoParamsChangedI, jlong testReceiverN)
    {
        VideoPlayer* p = native(testReceiverN);
        // Update all java stuff
        if (p->latestDecodingInfoChanged || p->latestVideoRatioChanged)
        {
            jclass jClassExtendsIVideoParamsChanged = env->GetObjectClass(videoParamsChangedI);
            if (p->latestVideoRatioChanged)
            {
                jmethodID onVideoRatioChangedJAVA =
                    env->GetMethodID(jClassExtendsIVideoParamsChanged, "onVideoRatioChanged", "(II)V");
                env->CallVoidMethod(
                    videoParamsChangedI,
                    onVideoRatioChangedJAVA,
                    (jint) p->latestVideoRatio.width,
                    (jint) p->latestVideoRatio.height);
                p->latestVideoRatioChanged = false;
            }
            if (p->latestDecodingInfoChanged)
            {
                jclass jcDecodingInfo = env->FindClass("com/openipc/videonative/DecodingInfo");
                assert(jcDecodingInfo != nullptr);
                jmethodID jcDecodingInfoConstructor = env->GetMethodID(jcDecodingInfo, "<init>", "(FFFFFIIII)V");
                assert(jcDecodingInfoConstructor != nullptr);
                const auto info         = p->latestDecodingInfo;
                auto       decodingInfo = env->NewObject(
                    jcDecodingInfo,
                    jcDecodingInfoConstructor,
                    (jfloat) info.currentFPS,
                    (jfloat) info.currentKiloBitsPerSecond,
                    (jfloat) info.avgParsingTime_ms,
                    (jfloat) info.avgWaitForInputBTime_ms,
                    (jfloat) info.avgDecodingTime_ms,
                    (jint) info.nNALU,
                    (jint) info.nNALUSFeeded,
                    (jint) info.nDecodedFrames,
                    (jint) info.nCodec);
                assert(decodingInfo != nullptr);
                jmethodID onDecodingInfoChangedJAVA = env->GetMethodID(
                    jClassExtendsIVideoParamsChanged,
                    "onDecodingInfoChanged",
                    "(Lcom/openipc/videonative/DecodingInfo;)V");
                assert(onDecodingInfoChangedJAVA != nullptr);
                env->CallVoidMethod(videoParamsChangedI, onDecodingInfoChangedJAVA, decodingInfo);
                p->latestDecodingInfoChanged = false;
            }
        }
    }
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_videonative_VideoPlayer_nativeStartDvr(
    JNIEnv* env, jclass clazz, jlong native_instance, jint fd, jint fmp4_enabled)
{
    native(native_instance)->startDvr(env, fd, fmp4_enabled);
}

extern "C" JNIEXPORT void JNICALL
Java_com_openipc_videonative_VideoPlayer_nativeStopDvr(JNIEnv* env, jclass clazz, jlong native_instance)
{
    native(native_instance)->stopDvr();
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_openipc_videonative_VideoPlayer_nativeIsRecording(JNIEnv* env, jclass clazz, jlong native_instance)
{
    return native(native_instance)->isRecording();
}
extern "C" JNIEXPORT void JNICALL
Java_com_openipc_videonative_VideoPlayer_nativeStartAudio(JNIEnv* env, jclass clazz, jlong native_instance)
{
    if (!native(native_instance)->audioDecoder.isInit)
    {
        native(native_instance)->audioDecoder.initAudio();
    }
    native(native_instance)->audioDecoder.stopAudioProcessing();
    native(native_instance)->audioDecoder.startAudioProcessing();
}
extern "C" JNIEXPORT void JNICALL
Java_com_openipc_videonative_VideoPlayer_nativeStopAudio(JNIEnv* env, jclass clazz, jlong native_instance)
{
    native(native_instance)->audioDecoder.stopAudioProcessing();
}
