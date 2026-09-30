package com.openipc.videonative;

import android.content.Context;
import android.content.res.AssetManager;
import android.graphics.SurfaceTexture;
import android.os.Looper;
import android.util.Log;
import android.view.Surface;
import android.view.SurfaceHolder;

import androidx.annotation.Nullable;

import java.util.Timer;
import java.util.TimerTask;


/**
 * All the receiving and decoding is done in .cpp
 * Tied to the lifetime of the java instance a .cpp instance is created
 * And the native functions talk to the native instance
 */
public class VideoPlayer implements IVideoParamsChanged {
    private static final String TAG = "pixelpilot";

    //All the native binding(s)
    static {
        System.loadLibrary("VideoNative");
    }

    private final long nativeVideoPlayer;
    private final Context context;
    private IVideoParamsChanged mVideoParamsChanged;
    // This timer is used to then 'call back' the IVideoParamsChanged
    private Timer timer;

    // Setup as much as possible without creating the decoder
    public VideoPlayer(final Context parent) {
        this.context = parent;
        nativeVideoPlayer = nativeInitialize(context);
    }

    public static native long nativeInitialize(Context context);

    public static native void nativeFinalize(long nativeVideoPlayer);

    public static native void nativeStart(long nativeInstance, Context context);

    public static native void nativeStop(long nativeInstance, Context context);

    public static native void nativeSetVideoSurface(long nativeInstance, Surface surface, int index);

    public static native void nativeSetUdpForwarding(long nativeInstance, String ip, int port, boolean enabled);

    public static native void nativeSetDecoderLevers(long nativeInstance, boolean lowLatency, boolean pictureOrder,
                                                     boolean operatingRate, boolean preferLowLatencyComponent,
                                                     boolean auAggregation, int debugKeyMask,
                                                     String componentName);

    public static native void nativeSetTightReorder(long nativeInstance, boolean tight);

    public static native void nativeSetFeedIncompleteFrames(long nativeInstance, boolean feed);

    /** {@code minIntervalMs} <= 0 keeps the native default (IdrRequestPolicy.h). */
    public static native void nativeSetRequestIdrOnLoss(long nativeInstance, boolean request, int minIntervalMs);

    public static native void nativeSetFreezeUntilIdr(long nativeInstance, boolean freeze);

    public static native String nativeGetDecoderSummary(long nativeInstance);

    public static native int[] nativeGetLatencyCriticalThreadIds(long nativeInstance);

    public static native long[] nativeDrainFrameReadyTimes(long nativeInstance);

    /** 4 longs per decoded frame: ssrc, RTP timestamp, complete ns, decoded ns (CLOCK_MONOTONIC). */
    public static native long[] nativeDrainFrameTimes(long nativeInstance);

    /**
     * Cumulative: IDR requests ok, IDR requests failed, slices frozen until an IDR, decoder rebuilds, codec switches;
     * then (index 5..10) the IDR requests per result: ok, refused, connect timeout, reply timeout, HTTP status, error
     * (IdrRequester::Result); then (index 11..14) their connect race: attempts started, requests won by attempt >= 2,
     * connect ms sum, requests connected.
     */
    public static native long[] nativeGetLeverCounters(long nativeInstance);

    /** True while freeze_until_idr holds the last good frame until a key frame (FreezeUntilIdr.h). */
    public static native boolean nativeIsFrozenUntilIdr(long nativeInstance);

    public static native void nativeStartDvr(long nativeInstance, int fd, int fmp4_enabled);

    public static native void nativeStopDvr(long nativeInstance);

    public static native boolean nativeIsRecording(long nativeInstance);
    public static native void nativeStartAudio(long nativeInstance);
    public static native void nativeStopAudio(long nativeInstance);

    //get members or other information. Some might be only usable in between (nativeStart <-> nativeStop)
    public static native String getVideoInfoString(long nativeInstance);

    public static native boolean anyVideoDataReceived(long nativeInstance);

    public static native boolean anyVideoBytesParsedSinceLastCall(long nativeInstance);

    public static native boolean receivingVideoButCannotParse(long nativeInstance);
    // TODO: Use message queue from cpp for performance#
    // This initiates a 'call back' for the IVideoParams
    public static native <T extends IVideoParamsChanged> void nativeCallBack(T t, long nativeInstance);

    public static void verifyApplicationThread() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            Log.w(TAG, "Player is accessed on the wrong thread.");
        }
    }

    public void setIVideoParamsChanged(final IVideoParamsChanged iVideoParamsChanged) {
        mVideoParamsChanged = iVideoParamsChanged;
    }

    private void setVideoSurface(final @Nullable Surface surface, int index) {
        verifyApplicationThread();
        nativeSetVideoSurface(nativeVideoPlayer, surface, index);
    }

    public synchronized void start() {
        verifyApplicationThread();
        nativeStart(nativeVideoPlayer, context);
        //The timer initiates the callback(s), but if no data has changed they are not called (and the timer does almost no work)
        //TODO: proper queue, but how to do synchronization in java ndk ?!
        timer = new Timer();
        timer.schedule(new TimerTask() {
            @Override
            public void run() {
                nativeCallBack(VideoPlayer.this, nativeVideoPlayer);
            }
        }, 0, 200);
    }

    public synchronized void stop() {
        if (timer == null) {
            return;
        }
        verifyApplicationThread();
        timer.cancel();
        timer.purge();
        nativeStop(nativeVideoPlayer, context);
        timer = null;
    }

    public void startAudio()
    {
        nativeStartAudio(nativeVideoPlayer);
    }

    public void stopAudio()
    {
        nativeStopAudio(nativeVideoPlayer);
    }

    public boolean isRunning() {
        return timer != null;
    }

    /**
     * Decoder latency levers from the single source of truth.
     * Takes effect the next time the decoder is configured; the RTP reorder bound at the next packet.
     */
    public void setDecoderLevers(LatencyExperiments e) {
        nativeSetDecoderLevers(nativeVideoPlayer, e.lowLatencyDecoder, e.decPictureOrder, e.decOperatingRate,
                e.decPreferLowLatencyComponent, e.auAggregation, e.decDebugKeyMask, e.decComponent);
        nativeSetTightReorder(nativeVideoPlayer, e.rtpTightReorder);
        nativeSetFeedIncompleteFrames(nativeVideoPlayer, e.feedIncompleteFrames);
        nativeSetRequestIdrOnLoss(nativeVideoPlayer, e.requestIdrOnLoss, e.idrMinIntervalMs);
        nativeSetFreezeUntilIdr(nativeVideoPlayer, e.freezeUntilIdr);
    }

    /** Kernel thread ids on the video latency path (receive/feed, output release); may be empty. */
    public int[] getLatencyCriticalThreadIds() {
        return nativeGetLatencyCriticalThreadIds(nativeVideoPlayer);
    }

    /**
     * CLOCK_MONOTONIC ns at which decoded frames were handed to the output surface since the previous
     * call (oldest first, bounded). Input for the XR compositor-phase meter.
     */
    public long[] drainFrameReadyTimes() {
        return nativeDrainFrameReadyTimes(nativeVideoPlayer);
    }

    /** Decoded frames since the last call, for the Stats page: see {@link #nativeDrainFrameTimes}. */
    public long[] drainFrameTimes() {
        return nativeDrainFrameTimes(nativeVideoPlayer);
    }

    /** See {@link #nativeIsFrozenUntilIdr}. */
    public boolean isFrozenUntilIdr() {
        return nativeIsFrozenUntilIdr(nativeVideoPlayer);
    }

    /** See {@link #nativeGetLeverCounters}. */
    public long[] leverCounters() {
        return nativeGetLeverCounters(nativeVideoPlayer);
    }

    /** Codec name and the levers it accepted, e.g. "default video/hevc | LL PO". */
    public String getDecoderSummary() {
        return nativeGetDecoderSummary(nativeVideoPlayer);
    }

    public void setUdpForwarding(String ip, int port, boolean enabled) {
        verifyApplicationThread();
        nativeSetUdpForwarding(nativeVideoPlayer, ip, port, enabled);
    }

    public void startDvr(int fd, boolean enabled_fmp4) {
        nativeStartDvr(nativeVideoPlayer, fd, enabled_fmp4 ? 1 : 0);
    }

    public void stopDvr() {
        nativeStopDvr(nativeVideoPlayer);
    }

    /**
     * Depending on the selected Settings, this starts either
     * a) Receiving RTP over UDP
     * b) Receiving RAW over UDP
     * c) Receiving Data from a resource file (Assets)
     * d) Receiving Data from a file in the phone file system
     * e) and more
     */
    public void addAndStartDecoderReceiver(Surface surface, int index) {
        setVideoSurface(surface, index);
    }

    /**
     * Stop the Receiver
     * Stop the Decoder
     * Free resources
     */
    public void stopAndRemoveReceiverDecoder(int index) {
        stop();
        setVideoSurface(null, index);
    }

    /**
     * Configure for use with SurfaceHolder from a SurfaceVew
     * The callback will handle the lifecycle of the Video player
     *
     * @return Callback that should be added to SurfaceView.Holder
     */
    public SurfaceHolder.Callback configure1(int index) {
        return new SurfaceHolder.Callback() {
            @Override
            public void surfaceCreated(SurfaceHolder holder) {
                addAndStartDecoderReceiver(holder.getSurface(), index);
            }

            @Override
            public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {

            }

            @Override
            public void surfaceDestroyed(SurfaceHolder holder) {
                Log.d(TAG, "surfaceDestroyed idx: " + index);
                stopAndRemoveReceiverDecoder(index);
            }
        };
    }

    public android.view.TextureView.SurfaceTextureListener configureTextureView(final int index) {
        return new android.view.TextureView.SurfaceTextureListener() {
            @Override
            public void onSurfaceTextureAvailable(android.graphics.SurfaceTexture surfaceTexture, int width, int height) {
                addAndStartDecoderReceiver(new Surface(surfaceTexture), index);
            }

            @Override
            public void onSurfaceTextureSizeChanged(android.graphics.SurfaceTexture surfaceTexture, int width, int height) {
            }

            @Override
            public boolean onSurfaceTextureDestroyed(android.graphics.SurfaceTexture surfaceTexture) {
                stopAndRemoveReceiverDecoder(index);
                return true;
            }

            @Override
            public void onSurfaceTextureUpdated(android.graphics.SurfaceTexture surfaceTexture) {
            }
        };
    }

//    /**
//     * Configure for use with VideoSurfaceHolder (OpenGL)
//     * The callback will handle the lifecycle of the video player
//     *
//     * @return Callback that should be added to VideoSurfaceHolder
//     */
//    public ISurfaceTextureAvailable configure2() {
//        return new ISurfaceTextureAvailable() {
//            @Override
//            public void surfaceTextureCreated(SurfaceTexture surfaceTexture, Surface surface) {
//                addAndStartDecoderReceiver(surface, index);
//            }
//
//            @Override
//            public void surfaceTextureDestroyed() {
//                stopAndRemoveReceiverDecoder(index);
//            }
//        };
//    }

    public long getNativeInstance() {
        return nativeVideoPlayer;
    }

    // called by native code via NDK
    @Override
    @SuppressWarnings({"UnusedDeclaration"})
    public void onVideoCodedSizeChanged(int codedW, int codedH, int cropLeft, int cropTop) {
        if (mVideoParamsChanged != null) {
            mVideoParamsChanged.onVideoCodedSizeChanged(codedW, codedH, cropLeft, cropTop);
        }
    }

    // called by native code via NDK
    @Override
    @SuppressWarnings({"UnusedDeclaration"})
    public void onVideoRatioChanged(int videoW, int videoH) {
        if (mVideoParamsChanged != null) {
            mVideoParamsChanged.onVideoRatioChanged(videoW, videoH);
        }
        System.out.println("Video W and H" + videoW + "," + videoH);
    }

    // called by native code via NDK
    @Override
    public void onDecodingInfoChanged(DecodingInfo decodingInfo) {
        if (mVideoParamsChanged != null) {
            mVideoParamsChanged.onDecodingInfoChanged(decodingInfo);
        }
        //Log.d(TAG,"onDecodingInfoChanged"+decodingInfo.toString());
    }

    @Override
    protected void finalize() throws Throwable {
        try {
            nativeFinalize(nativeVideoPlayer);
        } finally {
            super.finalize();
        }
    }

}

