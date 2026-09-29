//
// Created by Constantin on 1/9/2019.
//

#ifndef FPV_VR_VIDEOPLAYERN_H
#define FPV_VR_VIDEOPLAYERN_H
#include <fcntl.h>
#include <jni.h>
#include <stdio.h>
#include <fstream>
#include <queue>
#include <utility>
#include <vector>
#include "AudioDecoder.h"
#include "BufferedPacketQueue.h"
#include "UdpReceiver.h"
#include "UdsReceiver.h"
#include "FreezeUntilIdr.h"
#include "IdrRequester.h"
#include "VideoDecoder.h"
#include "minimp4.h"
#include "parser/H26XParser.h"
#include "time_util.h"

class VideoPlayer
{
  public:
    VideoPlayer(JNIEnv* env, jobject context);

    void onNewRTPData(const uint8_t* data, const std::size_t data_length);

    /*
     * Set the surface the decoder can be configured with. When @param surface==nullptr
     * It is guaranteed that the surface is not used by the decoder anymore when this call returns
     */
    void setVideoSurface(JNIEnv* env, jobject surface, jint i);

    /*
     * Start the receiver and ground recorder if enabled
     */
    void start(JNIEnv* env, jobject androidContext);

    /**
     * Stop the receiver and ground recorder if enabled
     */
    void stop(JNIEnv* env, jobject androidContext);

    /*
     * Returns a string with the current configuration for debugging
     */
    std::string getInfoString() const;

    void startDvr(JNIEnv* env, jint fd, jint fmp4_enabled);

    void stopDvr();

    bool isRecording() { return (get_time_ms() - last_dvr_write) <= 500; }

    void setForwarding(const std::string& ip, int port, bool enabled);

    void setDecoderLevers(const DecoderLevers& levers) { videoDecoder.setDecoderLevers(levers); }
    // Video only; audio keeps the upstream bounds (it runs at a fraction of the packet rate).
    void setTightReorder(bool tight)
    {
        mBufferedPacketQueueVideo.setBounds(tight ? kTightReorderBounds : kLegacyReorderBounds);
    }

    void setFeedIncompleteFrames(bool feed) { mParser.setFeedIncompleteFrames(feed); }
    void setFreezeUntilIdr(bool freeze) { mFreezeUntilIdr.setEnabled(freeze); }
    void setRequestIdrOnLoss(bool request, int min_interval_ms)
    {
        mIdrRequester.setMinIntervalMs(min_interval_ms);
        mIdrRequester.setEnabled(request);
    }

    std::string getDecoderSummary() { return videoDecoder.getDecoderSummary(); }
    std::vector<int64_t> drainFrameReadyTimes() { return videoDecoder.drainFrameReadyTimes(); }
    // Decoded frames keyed by RTP (ssrc, ts) since the last call, for the Stats page (FrameTimeline.h).
    std::vector<FrameTimes> drainFrameTimes() { return videoDecoder.drainFrameTimes(); }
    // Cumulative lever counters for the Stats page: IDR requests sent ok / failed, slices frozen until an IDR.
    uint32_t idrRequestsOk() const { return mIdrRequester.requestsOk(); }
    uint32_t idrRequestsFailed() const { return mIdrRequester.requestsFailed(); }
    uint32_t frozenSlices() const { return mFreezeUntilIdr.dropped(); }
    uint32_t decoderRebuilds() const { return videoDecoder.decoderRebuilds(); }
    uint32_t codecSwitches() const { return videoDecoder.codecSwitches(); }

    // Threads on the video latency path (receive/parse/feed and output release), for scheduling hints.
    std::vector<int> latencyCriticalThreadIds();

  private:
    void onNewNALU(const NALU& nalu);

    // Assumptions: Max bitrate: 40 MBit/s, Max time to buffer: 500ms
    // 25 MB should be plenty !
    static constexpr const size_t WANTED_UDP_RCVBUF_SIZE = 1024 * 1024 * 25;
    // Retrieve settings from shared preferences
    enum SOURCE_TYPE_OPTIONS
    {
        UDP,
        FILE,
        ASSETS,
        VIA_FFMPEG_URL,
        EXTERNAL
    };
    const std::string   GROUND_RECORDING_DIRECTORY;
    JavaVM*             javaVm = nullptr;
    // Declared before mParser: the parser's loss callback uses it, so it must outlive the parser.
    IdrRequester        mIdrRequester;
    FreezeUntilIdr      mFreezeUntilIdr;
    H26XParser          mParser;
    // Video starts tight like LatencyExperiments' default and follows setTightReorder.
    BufferedPacketQueue mBufferedPacketQueueVideo{kTightReorderBounds};
    BufferedPacketQueue mBufferedPacketQueueAudio{kLegacyReorderBounds};

    // A NALU is a non-owning view onto the parser's buffer (see NALU.hpp), which is
    // reused for the next packet. The DVR writer runs on its own thread, so what gets
    // handed over has to own its bytes.
    struct DvrNalu
    {
        std::vector<uint8_t> data;
        bool                 is_h265 = false;
    };

    // DVR attributes
    int                     dvr_fd;
    std::queue<DvrNalu>     naluQueue;
    std::mutex              mtx;
    std::condition_variable cv;
    bool                    stopFlag = false;
    std::thread             processingThread;
    int                     dvr_mp4_fragmentation = 0;
    uint64_t                last_dvr_write        = 0;

    void enqueueNALU(DvrNalu&& nalu)
    {
        {
            std::lock_guard<std::mutex> lock(mtx);
            naluQueue.push(std::move(nalu));
        }
        cv.notify_one();
    }

    void startProcessing()
    {
        stopFlag         = false;
        processingThread = std::thread(&VideoPlayer::processQueue, this);
    }

    void stopProcessing()
    {
        {
            std::lock_guard<std::mutex> lock(mtx);
            stopFlag = true;
        }
        cv.notify_all();
        if (processingThread.joinable())
        {
            processingThread.join();
        }
    }

    void processQueue();

    std::string mForwardIP = "";
    int         mForwardPort = 0;
    bool        mForwardEnabled = false;

  public:
    AudioDecoder                 audioDecoder;
    VideoDecoder                 videoDecoder;
    std::unique_ptr<UDPReceiver> mUDPReceiver;
    std::unique_ptr<UDSReceiver> mUDSReceiver;
    long                         nNALUsAtLastCall = 0;

  public:
    DecodingInfo      latestDecodingInfo{};
    std::atomic<bool> latestDecodingInfoChanged = false;
    VideoRatio        latestVideoRatio{};
    std::atomic<bool> latestVideoRatioChanged = false;

    bool lastFrameWasAUD = false;
};

#endif  // FPV_VR_VIDEOPLAYERN_H
