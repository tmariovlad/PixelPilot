package com.openipc.xr;

import android.app.Activity;
import android.view.Surface;

/**
 * Java face of the native OpenXR runtime. start() creates the session and two compositor-owned
 * surfaces; the caller feeds videoSurface() with MediaCodec and draws the stats into statsSurface().
 */
public final class XrBridge {
    static {
        System.loadLibrary("PixelPilotXr");
    }

    public enum SessionEvent { ACTIVE, INACTIVE, EXITING }

    /**
     * Called on the XR thread. ACTIVE: the video surface may be fed. INACTIVE: stop feeding it
     * before returning (the runtime ends the session right after). EXITING: finish the activity.
     */
    public interface Listener {
        void onSessionEvent(SessionEvent event);
    }

    /** Negative values mean "not reported by the runtime". */
    public static final class Info {
        public final float refreshHz, requestedHz, compositorGpuMs, droppedFrames, motionToPhotonMs;

        Info(float[] v) {
            refreshHz = v[0];
            requestedHz = v[1];
            compositorGpuMs = v[2];
            droppedFrames = v[3];
            motionToPhotonMs = v[4];
        }
    }

    /** Display timing of the latest frame the runtime predicted; periodNs == 0 means none yet. */
    public static final class DisplayGrid {
        /** predictedDisplayTime, in CLOCK_MONOTONIC ns when {@link #monotonic}. */
        public final long displayTimeNs;
        public final long periodNs;
        public final boolean monotonic;

        DisplayGrid(long[] v) {
            displayTimeNs = v[0];
            periodNs = v[1];
            monotonic = v[2] != 0;
        }
    }

    private final Listener listener;
    private long handle;

    public XrBridge(Listener listener) {
        this.listener = listener;
        handle = nativeCreate();
    }

    /**
     * Returns null on success, otherwise a human-readable reason. The initial layout sizes the
     * surfaces, so the swapchains are created with the same numbers the layers later use.
     */
    public String start(Activity activity, int refreshHz, boolean useTimestamps, boolean perfSustainedHigh,
                        LayerLayout initialLayout) {
        setLayout(initialLayout);
        if (nativeStart(handle, activity, refreshHz, useTimestamps, perfSustainedHigh)) return null;
        String error = nativeError(handle);
        return error.isEmpty() ? "OpenXR start failed" : error;
    }

    public Surface videoSurface() {
        return handle == 0 ? null : (Surface) nativeVideoSurface(handle);
    }

    public Surface statsSurface() {
        return handle == 0 ? null : (Surface) nativeStatsSurface(handle);
    }

    /** The menu layer's surface (docs/xr/menu-design.md); null if the runtime has no menu swapchain. */
    public Surface menuSurface() {
        return handle == 0 ? null : (Surface) nativeMenuSurface(handle);
    }

    /** The menu layer is submitted only while visible. No-op after stop(). */
    public void setMenuVisible(boolean visible) {
        if (handle != 0) nativeSetMenuVisible(handle, visible);
    }

    /** No-op after stop(): late callbacks from other threads may still arrive then. */
    public void setLayout(LayerLayout l) {
        if (handle == 0) return;
        float[] v = {l.videoWidthM, l.videoHeightM, l.videoZ, l.cylRadius, l.cylAngleRad, l.cylAspect,
                l.statsWidthM, l.statsHeightM, l.statsY, l.statsZ, LayerLayout.STATS_IMAGE_W,
                LayerLayout.STATS_IMAGE_H, l.menuWidthM, l.menuHeightM, l.menuX, l.menuY, l.menuZ, l.menuYawRad,
                LayerLayout.MENU_IMAGE_W, LayerLayout.MENU_IMAGE_H};
        nativeSetLayout(handle, l.cylinder, l.flip, v, l.imageW, l.imageH, l.bufferW, l.bufferH, l.rectX, l.rectY);
    }

    /**
     * Threads outside the runtime that sit on the video path (receive/feed, decoder output); the
     * runtime schedules them as renderer workers. Safe to call repeatedly; no-op after stop().
     */
    public void hintWorkerThreads(int[] threadIds) {
        if (handle == 0 || threadIds == null) return;
        nativeSetWorkerThreads(handle, threadIds);
    }

    /** All values "not available" after stop(). */
    public Info info() {
        return new Info(handle == 0 ? new float[]{-1f, -1f, -1f, -1f, -1f} : nativeInfo(handle));
    }

    /** No grid (periodNs == 0) after stop(). */
    public DisplayGrid displayGrid() {
        return new DisplayGrid(handle == 0 ? new long[]{0, 0, 0} : nativeDisplayGrid(handle));
    }

    /** Ends the session and frees everything. Stop feeding the video surface before calling. */
    public void stop() {
        if (handle == 0) return;
        nativeDestroy(handle);
        handle = 0;
    }

    @SuppressWarnings("unused") // called from xr_jni.cpp
    private void onNativeSessionEvent(int event) {
        listener.onSessionEvent(SessionEvent.values()[event]);
    }

    /** Press bits from {@link #takeInputEvents()}; the same values as XrInput::Event in XrInput.h. */
    public static final int INPUT_PANEL_DETAIL = 1;
    public static final int INPUT_PANEL_VISIBILITY = 2;
    public static final int INPUT_STICK_LEFT = 4;       // a thumbstick flick (preset menu)
    public static final int INPUT_STICK_RIGHT = 8;
    public static final int INPUT_STICK_UP = 16;
    public static final int INPUT_STICK_DOWN = 32;
    public static final int INPUT_STICK_PRESS = 64;     // a thumbstick click goes down / up
    public static final int INPUT_STICK_RELEASE = 128;

    private final java.util.concurrent.atomic.AtomicInteger injected = new java.util.concurrent.atomic.AtomicInteger();

    /** Controller/hand presses since the last call (INPUT_* bits), taken from the XR thread without blocking it. */
    public int takeInputEvents() {
        return (handle == 0 ? 0 : nativeTakeInputEvents(handle)) | injected.getAndSet(0);
    }

    /** Debug builds: input bits that reach the next {@link #takeInputEvents()} as if a controller sent them. */
    public void injectInputEvents(int events) {
        injected.getAndAccumulate(events, (a, b) -> a | b);
    }

    private native long nativeCreate();
    private native boolean nativeStart(long h, Activity activity, float refreshHz, boolean useTimestamps, boolean perfHigh);
    private native String nativeError(long h);
    private native Object nativeVideoSurface(long h);
    private native Object nativeStatsSurface(long h);
    private native Object nativeMenuSurface(long h);
    private native void nativeSetMenuVisible(long h, boolean visible);
    private native void nativeSetLayout(long h, boolean cylinder, boolean flip, float[] values, int imageW, int imageH,
                                        int bufferW, int bufferH, int rectX, int rectY);
    private native float[] nativeInfo(long h);
    private native long[] nativeDisplayGrid(long h);
    private native void nativeSetWorkerThreads(long h, int[] threadIds);
    private native int nativeTakeInputEvents(long h);
    private native void nativeDestroy(long h);
}
