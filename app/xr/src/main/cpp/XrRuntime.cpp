#include "XrRuntime.h"
#include <android/trace.h>
#include <android/log.h>
#include <sys/prctl.h>
#include <unistd.h>
#include <algorithm>
#include <cstring>
#include <vector>

#define XR_TAG "PixelPilotXr"
#define XLOGI(...) __android_log_print(ANDROID_LOG_INFO, XR_TAG, __VA_ARGS__)
#define XLOGE(...) __android_log_print(ANDROID_LOG_ERROR, XR_TAG, __VA_ARGS__)

namespace
{
template <typename T>
bool loadFn(XrInstance instance, const char* name, T& fn)
{
    fn = nullptr;
    return XR_SUCCEEDED(xrGetInstanceProcAddr(instance, name, reinterpret_cast<PFN_xrVoidFunction*>(&fn))) &&
           fn != nullptr;
}

XrPosef identityPose()
{
    XrPosef p{};
    p.orientation.w = 1.f;
    return p;
}
}  // namespace

XrRuntime::~XrRuntime() { stop(); }

bool XrRuntime::start(JavaVM* vm, jobject activityGlobalRef, const XrStartConfig& cfg, Listener listener)
{
    if (mThread.joinable())
    {
        JNIEnv* env = nullptr;
        if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_OK) env->DeleteGlobalRef(activityGlobalRef);
        return fail("already started");
    }
    mActivity = activityGlobalRef;
    mListener = std::move(listener);
    mExit     = false;
    std::promise<bool> ready;
    auto               result = ready.get_future();
    mThread                   = std::thread(&XrRuntime::threadMain, this, vm, cfg, std::move(ready));
    if (result.wait_for(std::chrono::seconds(4)) != std::future_status::ready)
    {
        fail("OpenXR setup timed out");
        stop();
        return false;
    }
    const bool ok = result.get();
    if (!ok) stop();
    return ok;
}

void XrRuntime::stop()
{
    mExit = true;
    if (mThread.joinable()) mThread.join();
}

void XrRuntime::setLayerConfig(const LayerConfig& c)
{
    std::lock_guard<std::mutex> lock(mMutex);
    mResizePending = mResizePending || c.bufferW != mLayerConfig.bufferW || c.bufferH != mLayerConfig.bufferH;
    mLayerConfig   = c;
}

jobject XrRuntime::videoSurface()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mVideoSurface;
}

jobject XrRuntime::statsSurface()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mStatsSurface;
}

jobject XrRuntime::menuSurface()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mMenuSurface;
}

void XrRuntime::setMenuVisible(bool visible)
{
    std::lock_guard<std::mutex> lock(mMutex);
    mLayerConfig.menuVisible = visible;
}

void XrRuntime::setWorkerThreads(const std::vector<int>& tids)
{
    std::lock_guard<std::mutex> lock(mMutex);
    mWorkerThreads = tids;
}

void XrRuntime::applyWorkerThreadHints()
{
    if (!pfnSetThread) return;
    std::vector<int> tids;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        tids = mWorkerThreads;
    }
    for (int tid : tids)
    {
        if (tid <= 0 || mHintedThreads.count(tid)) continue;
        const XrResult r = pfnSetThread(mSession, XR_ANDROID_THREAD_TYPE_RENDERER_WORKER_KHR, tid);
        XLOGI("hinted thread %d as renderer worker (result %d)", tid, r);
        mHintedThreads.insert(tid);
    }
}

XrRuntimeInfo XrRuntime::info()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mInfo;
}

XrDisplayGrid XrRuntime::displayGrid()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mGrid;
}

void XrRuntime::recordDisplayGrid(const XrFrameState& frameState)
{
    XrDisplayGrid g;
    g.displayTimeNs = frameState.predictedDisplayTime;
    g.periodNs      = frameState.predictedDisplayPeriod;
    timespec ts{};
    if (pfnTimeToTimespec && XR_SUCCEEDED(pfnTimeToTimespec(mInstance, frameState.predictedDisplayTime, &ts)))
    {
        g.displayTimeNs = static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
        g.monotonic     = true;
        // Puts the grid on a system trace's timeline, for calibrating the latch offset.
        if (__builtin_available(android 29, *))
        {
            if (ATrace_isEnabled())
            {
                timespec now{};
                clock_gettime(CLOCK_MONOTONIC, &now);
                const int64_t nowNs = static_cast<int64_t>(now.tv_sec) * 1000000000LL + now.tv_nsec;
                ATrace_setCounter("ppxr_display_minus_now_us", (g.displayTimeNs - nowNs) / 1000);
            }
        }
    }
    std::lock_guard<std::mutex> lock(mMutex);
    mGrid = g;
}

std::string XrRuntime::error()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mError;
}

bool XrRuntime::fail(const std::string& what)
{
    XLOGE("%s", what.c_str());
    std::lock_guard<std::mutex> lock(mMutex);
    mError = what;
    return false;
}

void XrRuntime::threadMain(JavaVM* vm, XrStartConfig cfg, std::promise<bool> ready)
{
    prctl(PR_SET_NAME, "PixelPilotXr");
    mVm         = vm;
    mCfg        = cfg;
    JNIEnv* env = nullptr;
    vm->AttachCurrentThread(&env, nullptr);
    const bool ok = setup(env);
    ready.set_value(ok);
    if (ok) loop();
    teardown(env);
    vm->DetachCurrentThread();
}

bool XrRuntime::setup(JNIEnv* env)
{
    PFN_xrInitializeLoaderKHR initLoader = nullptr;
    if (!loadFn(XR_NULL_HANDLE, "xrInitializeLoaderKHR", initLoader)) return fail("xrInitializeLoaderKHR missing");
    XrLoaderInitInfoAndroidKHR loaderInfo{XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR};
    loaderInfo.applicationVM      = mVm;
    loaderInfo.applicationContext = mActivity;
    if (XR_FAILED(initLoader(reinterpret_cast<const XrLoaderInitInfoBaseHeaderKHR*>(&loaderInfo))))
        return fail("OpenXR loader init failed");

    uint32_t count = 0;
    if (XR_FAILED(xrEnumerateInstanceExtensionProperties(nullptr, 0, &count, nullptr)))
        return fail("no OpenXR runtime found on this device");
    std::vector<XrExtensionProperties> props(count, {XR_TYPE_EXTENSION_PROPERTIES});
    xrEnumerateInstanceExtensionProperties(nullptr, count, &count, props.data());
    std::set<std::string> available;
    for (const auto& p : props) available.insert(p.extensionName);

    const char* required[] = {XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, XR_KHR_OPENGL_ES_ENABLE_EXTENSION_NAME,
                              XR_KHR_ANDROID_SURFACE_SWAPCHAIN_EXTENSION_NAME};
    const char* optional[] = {XR_FB_ANDROID_SURFACE_SWAPCHAIN_CREATE_EXTENSION_NAME,
                              XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME,
                              XR_EXT_PERFORMANCE_SETTINGS_EXTENSION_NAME,
                              XR_KHR_ANDROID_THREAD_SETTINGS_EXTENSION_NAME,
                              XR_FB_COMPOSITION_LAYER_IMAGE_LAYOUT_EXTENSION_NAME,
                              XR_KHR_COMPOSITION_LAYER_CYLINDER_EXTENSION_NAME,
                              XR_META_PERFORMANCE_METRICS_EXTENSION_NAME,
                              XR_FB_SWAPCHAIN_UPDATE_STATE_EXTENSION_NAME,
                              XR_FB_SWAPCHAIN_UPDATE_STATE_ANDROID_SURFACE_EXTENSION_NAME,
                              XR_KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME};
    std::vector<const char*> exts;
    for (const char* e : required)
    {
        if (!available.count(e)) return fail(std::string("OpenXR runtime lacks ") + e);
        exts.push_back(e);
        mEnabled.insert(e);
    }
    for (const char* e : optional)
    {
        if (!available.count(e)) continue;
        exts.push_back(e);
        mEnabled.insert(e);
    }

    XrInstanceCreateInfoAndroidKHR androidInfo{XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR};
    androidInfo.applicationVM       = mVm;
    androidInfo.applicationActivity = mActivity;
    XrInstanceCreateInfo createInfo{XR_TYPE_INSTANCE_CREATE_INFO};
    createInfo.next = &androidInfo;
    std::strncpy(createInfo.applicationInfo.applicationName, "PixelPilot XR", XR_MAX_APPLICATION_NAME_SIZE - 1);
    std::strncpy(createInfo.applicationInfo.engineName, "PixelPilot", XR_MAX_ENGINE_NAME_SIZE - 1);
    createInfo.applicationInfo.applicationVersion = 1;
    createInfo.applicationInfo.apiVersion         = XR_API_VERSION_1_0;
    createInfo.enabledExtensionCount              = static_cast<uint32_t>(exts.size());
    createInfo.enabledExtensionNames              = exts.data();
    if (XR_FAILED(xrCreateInstance(&createInfo, &mInstance))) return fail("xrCreateInstance failed");

    XrSystemGetInfo systemInfo{XR_TYPE_SYSTEM_GET_INFO};
    systemInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
    if (XR_FAILED(xrGetSystem(mInstance, &systemInfo, &mSystemId))) return fail("xrGetSystem failed (no HMD)");

    PFN_xrGetOpenGLESGraphicsRequirementsKHR glesRequirements = nullptr;
    if (!loadFn(mInstance, "xrGetOpenGLESGraphicsRequirementsKHR", glesRequirements))
        return fail("xrGetOpenGLESGraphicsRequirementsKHR missing");
    XrGraphicsRequirementsOpenGLESKHR requirements{XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_ES_KHR};
    glesRequirements(mInstance, mSystemId, &requirements);  // mandatory before xrCreateSession
    if (!mEgl.create()) return fail("EGL context creation failed");

    XrGraphicsBindingOpenGLESAndroidKHR binding{XR_TYPE_GRAPHICS_BINDING_OPENGL_ES_ANDROID_KHR};
    binding.display = mEgl.display();
    binding.config  = mEgl.config();
    binding.context = mEgl.context();
    XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
    sessionInfo.next     = &binding;
    sessionInfo.systemId = mSystemId;
    if (XR_FAILED(xrCreateSession(mInstance, &sessionInfo, &mSession))) return fail("xrCreateSession failed");

    XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
    spaceInfo.referenceSpaceType   = XR_REFERENCE_SPACE_TYPE_VIEW;  // head-locked: never reprojected
    spaceInfo.poseInReferenceSpace = identityPose();
    if (XR_FAILED(xrCreateReferenceSpace(mSession, &spaceInfo, &mViewSpace))) return fail("VIEW space failed");
    mInput.setup(mInstance, mSession);   // optional: the viewer works without input

    loadFunctions();
    if (!pfnCreateSurface) return fail("xrCreateSwapchainAndroidSurfaceKHR missing");
    LayerConfig initial;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        initial = mLayerConfig;
    }
    jobject video = createSurface(env, initial.bufferW, initial.bufferH, mCfg.useTimestamps, mVideoChain);
    jobject stats = video ? createSurface(env, initial.statsImageW, initial.statsImageH, false, mStatsChain) : nullptr;
    jobject menu  = stats ? createSurface(env, initial.menuImageW, initial.menuImageH, false, mMenuChain) : nullptr;
    if (stats && !menu) XLOGE("menu surface swapchain creation failed; running without the menu");
    {
        std::lock_guard<std::mutex> lock(mMutex);
        mVideoSurface = video;
        mStatsSurface = stats;
        mMenuSurface  = menu;
    }
    if (!video) return fail("video surface swapchain creation failed");
    if (!stats) return fail("stats surface swapchain creation failed");
    enableMetrics();
    XLOGI("OpenXR ready: %zu extensions enabled", mEnabled.size());
    return true;
}

void XrRuntime::loadFunctions()
{
    loadFn(mInstance, "xrCreateSwapchainAndroidSurfaceKHR", pfnCreateSurface);
    if (enabled(XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME))
    {
        loadFn(mInstance, "xrEnumerateDisplayRefreshRatesFB", pfnEnumerateRates);
        loadFn(mInstance, "xrRequestDisplayRefreshRateFB", pfnRequestRate);
        loadFn(mInstance, "xrGetDisplayRefreshRateFB", pfnGetRate);
    }
    if (enabled(XR_EXT_PERFORMANCE_SETTINGS_EXTENSION_NAME))
        loadFn(mInstance, "xrPerfSettingsSetPerformanceLevelEXT", pfnPerfLevel);
    if (enabled(XR_KHR_ANDROID_THREAD_SETTINGS_EXTENSION_NAME))
        loadFn(mInstance, "xrSetAndroidApplicationThreadKHR", pfnSetThread);
    if (enabled(XR_FB_SWAPCHAIN_UPDATE_STATE_ANDROID_SURFACE_EXTENSION_NAME))
        loadFn(mInstance, "xrUpdateSwapchainFB", pfnUpdateSwapchain);
    if (enabled(XR_META_PERFORMANCE_METRICS_EXTENSION_NAME))
    {
        loadFn(mInstance, "xrSetPerformanceMetricsStateMETA", pfnSetMetricsState);
        loadFn(mInstance, "xrQueryPerformanceMetricsCounterMETA", pfnQueryMetric);
    }
    if (enabled(XR_KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME))
        loadFn(mInstance, "xrConvertTimeToTimespecTimeKHR", pfnTimeToTimespec);
}

jobject XrRuntime::createSurface(JNIEnv* env, int w, int h, bool useTimestamps, XrSwapchain& out)
{
    XrSwapchainCreateInfo                 info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
    XrAndroidSurfaceSwapchainCreateInfoFB fbInfo{XR_TYPE_ANDROID_SURFACE_SWAPCHAIN_CREATE_INFO_FB};
    // Never SYNCHRONOUS: the default BufferQueue replaces the pending buffer (mailbox), which is
    // what keeps a late frame from queueing behind an older one (measured: depth max 1 at 72/90/120 Hz,
    // docs/xr/display-latency.md). The spec forbids createFlags == 0, so with no flag the FB struct is left out.
    const XrAndroidSurfaceSwapchainFlagsFB flags =
        useTimestamps ? XR_ANDROID_SURFACE_SWAPCHAIN_USE_TIMESTAMPS_BIT_FB : 0;
    if (flags != 0 && enabled(XR_FB_ANDROID_SURFACE_SWAPCHAIN_CREATE_EXTENSION_NAME))
    {
        fbInfo.createFlags = flags;
        info.next          = &fbInfo;
    }
    info.usageFlags = XR_SWAPCHAIN_USAGE_SAMPLED_BIT | XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
    info.width      = static_cast<uint32_t>(w);
    info.height     = static_cast<uint32_t>(h);
    // format, sampleCount, faceCount, arraySize, mipCount must be zero for this extension.
    jobject surface = nullptr;
    if (XR_FAILED(pfnCreateSurface(mSession, &info, &out, &surface)) || surface == nullptr) return nullptr;
    // Own a global ref regardless of what the runtime handed back; only free what was local.
    jobject global = env->NewGlobalRef(surface);
    if (env->GetObjectRefType(surface) == JNILocalRefType) env->DeleteLocalRef(surface);
    return global;
}

void XrRuntime::loop()
{
    while (!mExit && !mRuntimeExit)
    {
        pollEvents();
        if (!mRunning)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        }
        renderFrame();
    }
    if (mRunning) requestExitAndDrain();
}

void XrRuntime::requestExitAndDrain()
{
    // Orderly end: ask the runtime to stop, then keep the loop turning until it has sent STOPPING
    // (handled by onStateChanged -> endSession). xrEndSession is only valid in STOPPING.
    const XrResult r = xrRequestExitSession(mSession);
    if (XR_FAILED(r)) XLOGE("xrRequestExitSession failed: %d", r);
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
    while (mRunning && XR_SUCCEEDED(r) && std::chrono::steady_clock::now() < deadline)
    {
        pollEvents();
        if (mRunning) renderFrame();
    }
    if (mRunning)
    {
        XLOGE("runtime did not reach STOPPING in time, ending the session directly");
        endSession();
    }
}

void XrRuntime::pollEvents()
{
    XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
    while (xrPollEvent(mInstance, &event) == XR_SUCCESS)
    {
        if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED)
        {
            const auto& changed = reinterpret_cast<const XrEventDataSessionStateChanged&>(event);
            onStateChanged(changed.state);
        }
        else if (event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING)
        {
            mRuntimeExit = true;
            if (mListener) mListener(SessionEvent::Exiting);
        }
        else if (event.type == XR_TYPE_EVENT_DATA_DISPLAY_REFRESH_RATE_CHANGED_FB)
        {
            // Horizon OS may lower the rate by itself (thermal throttling to 72 Hz, docs/xr/display-latency.md).
            const auto& rate = reinterpret_cast<const XrEventDataDisplayRefreshRateChangedFB&>(event);
            XLOGI("display refresh rate changed %.0f -> %.0f Hz", rate.fromDisplayRefreshRate,
                  rate.toDisplayRefreshRate);
            std::lock_guard<std::mutex> lock(mMutex);
            mInfo.refreshHz = rate.toDisplayRefreshRate;
        }
        event = {XR_TYPE_EVENT_DATA_BUFFER};
    }
}

void XrRuntime::onStateChanged(XrSessionState state)
{
    XLOGI("session state %d -> %d", mState, state);
    mState = state;
    switch (state)
    {
        case XR_SESSION_STATE_READY:
        {
            XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
            begin.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
            const XrResult r = xrBeginSession(mSession, &begin);
            if (XR_FAILED(r))
            {
                fail("xrBeginSession failed: " + std::to_string(r));
                break;
            }
            mRunning = true;
            applyRefreshRate();
            applyPerformanceHints();
            break;
        }
        case XR_SESSION_STATE_VISIBLE:
        case XR_SESSION_STATE_FOCUSED:
            setVideoAllowed(true);
            break;
        case XR_SESSION_STATE_SYNCHRONIZED:
            setVideoAllowed(false);  // dropped out of VISIBLE: writing is undefined from here on
            break;
        case XR_SESSION_STATE_STOPPING:
            endSession();
            break;
        case XR_SESSION_STATE_EXITING:
        case XR_SESSION_STATE_LOSS_PENDING:
            mRuntimeExit = true;
            if (mListener) mListener(SessionEvent::Exiting);
            break;
        default:
            break;
    }
}

void XrRuntime::setVideoAllowed(bool allowed)
{
    if (allowed == mVideoAllowed) return;
    mVideoAllowed = allowed;
    if (mListener) mListener(allowed ? SessionEvent::Active : SessionEvent::Inactive);
}

void XrRuntime::endSession()
{
    setVideoAllowed(false);  // the producer has stopped when this returns (spec: before xrEndSession)
    const XrResult r = xrEndSession(mSession);
    if (XR_FAILED(r)) XLOGE("xrEndSession failed: %d", r);
    mRunning = false;
}

void XrRuntime::renderFrame()
{
    XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
    XrFrameState    frameState{XR_TYPE_FRAME_STATE};
    const XrResult waited = xrWaitFrame(mSession, &waitInfo, &frameState);
    if (XR_FAILED(waited))
    {
        // Only on the failure path: without a pause, a runtime that keeps failing xrWaitFrame turned loop() into a
        // busy spin on one core (audit X25). The normal frame path is untouched.
        if (!mWaitFailing) XLOGE("xrWaitFrame failed (%d); retrying every 5 ms", static_cast<int>(waited));
        mWaitFailing = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        return;
    }
    mWaitFailing = false;
    recordDisplayGrid(frameState);
    XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
    if (XR_FAILED(xrBeginFrame(mSession, &beginInfo))) return;

    LayerConfig config;
    bool        resize = false;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        config         = mLayerConfig;
        resize         = mResizePending;
        mResizePending = false;
    }
    if (resize && pfnUpdateSwapchain)
    {
        XrSwapchainStateAndroidSurfaceDimensionsFB dims{XR_TYPE_SWAPCHAIN_STATE_ANDROID_SURFACE_DIMENSIONS_FB};
        dims.width  = static_cast<uint32_t>(config.bufferW);
        dims.height = static_cast<uint32_t>(config.bufferH);
        pfnUpdateSwapchain(mVideoChain, reinterpret_cast<const XrSwapchainStateBaseHeaderFB*>(&dims));
    }

    XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
    endInfo.displayTime          = frameState.predictedDisplayTime;
    endInfo.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
    if (frameState.shouldRender)
    {
        mLayers.build(config,
                      mViewSpace,
                      mVideoChain,
                      mStatsChain,
                      mMenuChain,
                      enabled(XR_FB_COMPOSITION_LAYER_IMAGE_LAYOUT_EXTENSION_NAME),
                      enabled(XR_KHR_COMPOSITION_LAYER_CYLINDER_EXTENSION_NAME));
        endInfo.layerCount = mLayers.count();
        endInfo.layers     = mLayers.layers();
    }
    const XrResult ended = xrEndFrame(mSession, &endInfo);
    if (XR_FAILED(ended) && (mFrames % 120) == 0) XLOGE("xrEndFrame failed: %d", ended);
    // After the frame is submitted, so input never delays it. Traced, to measure its cost (ppxr_input_sync).
    const bool traced = ATrace_isEnabled();
    if (traced) ATrace_beginSection("ppxr_input_sync");
    mInput.poll(mSession);
    if (traced) ATrace_endSection();
    if (++mFrames % 30 == 0)
    {
        readMetrics();
        applyWorkerThreadHints();
    }
}

void XrRuntime::applyRefreshRate()
{
    {
        std::lock_guard<std::mutex> lock(mMutex);
        mInfo.requestedHz = mCfg.refreshHz;
    }
    if (!pfnEnumerateRates || !pfnRequestRate) return;
    uint32_t n = 0;
    pfnEnumerateRates(mSession, 0, &n, nullptr);
    std::vector<float> rates(n);
    pfnEnumerateRates(mSession, n, &n, rates.data());
    float best = -1.f;
    for (float r : rates)
        if (r <= mCfg.refreshHz + 0.5f && r > best) best = r;  // highest supported <= requested
    if (best < 0.f && !rates.empty()) best = *std::min_element(rates.begin(), rates.end());
    if (best > 0.f)
    {
        const XrResult r = pfnRequestRate(mSession, best);
        XLOGI("requested %.0f Hz -> %.0f Hz (result %d)", mCfg.refreshHz, best, r);
    }
    // The request may apply later: a change after this point arrives as XrEventDataDisplayRefreshRateChangedFB.
    float now = -1.f;
    if (pfnGetRate && XR_SUCCEEDED(pfnGetRate(mSession, &now))) XLOGI("display refresh rate now %.0f Hz", now);
}

void XrRuntime::applyPerformanceHints()
{
    if (pfnSetThread) pfnSetThread(mSession, XR_ANDROID_THREAD_TYPE_RENDERER_MAIN_KHR, gettid());
    if (!mCfg.perfSustainedHigh || !pfnPerfLevel) return;
    pfnPerfLevel(mSession, XR_PERF_SETTINGS_DOMAIN_CPU_EXT, XR_PERF_SETTINGS_LEVEL_SUSTAINED_HIGH_EXT);
    pfnPerfLevel(mSession, XR_PERF_SETTINGS_DOMAIN_GPU_EXT, XR_PERF_SETTINGS_LEVEL_SUSTAINED_HIGH_EXT);
}

void XrRuntime::enableMetrics()
{
    if (!pfnSetMetricsState || !pfnQueryMetric) return;
    XrPerformanceMetricsStateMETA state{XR_TYPE_PERFORMANCE_METRICS_STATE_META};
    state.enabled = XR_TRUE;
    pfnSetMetricsState(mSession, &state);
    xrStringToPath(mInstance, "/perfmetrics_meta/compositor/gpu_frametime", &mPathCompositorGpu);
    xrStringToPath(mInstance, "/perfmetrics_meta/compositor/dropped_frame_count", &mPathDroppedFrames);
    xrStringToPath(mInstance, "/perfmetrics_meta/app/motion_to_photon_latency", &mPathMotionToPhoton);
}

float XrRuntime::queryMetric(XrPath path)
{
    if (!pfnQueryMetric || path == XR_NULL_PATH) return -1.f;
    XrPerformanceMetricsCounterMETA counter{XR_TYPE_PERFORMANCE_METRICS_COUNTER_META};
    if (XR_FAILED(pfnQueryMetric(mSession, path, &counter))) return -1.f;
    if (counter.counterFlags & XR_PERFORMANCE_METRICS_COUNTER_FLOAT_VALUE_VALID_BIT_META) return counter.floatValue;
    if (counter.counterFlags & XR_PERFORMANCE_METRICS_COUNTER_UINT_VALUE_VALID_BIT_META)
        return static_cast<float>(counter.uintValue);
    return -1.f;
}

void XrRuntime::readMetrics()
{
    float hz = -1.f;
    if (pfnGetRate) pfnGetRate(mSession, &hz);
    const float                 gpu     = queryMetric(mPathCompositorGpu);
    const float                 dropped = queryMetric(mPathDroppedFrames);
    const float                 m2p     = queryMetric(mPathMotionToPhoton);
    std::lock_guard<std::mutex> lock(mMutex);
    mInfo.refreshHz        = hz;
    mInfo.compositorGpuMs  = gpu;
    mInfo.droppedFrames    = dropped;
    mInfo.motionToPhotonMs = m2p;
}

void XrRuntime::teardown(JNIEnv* env)
{
    if (mVideoChain != XR_NULL_HANDLE) xrDestroySwapchain(mVideoChain);
    if (mStatsChain != XR_NULL_HANDLE) xrDestroySwapchain(mStatsChain);
    if (mMenuChain != XR_NULL_HANDLE) xrDestroySwapchain(mMenuChain);
    if (mViewSpace != XR_NULL_HANDLE) xrDestroySpace(mViewSpace);
    mInput.destroy();
    if (mSession != XR_NULL_HANDLE) xrDestroySession(mSession);
    mEgl.destroy();
    if (mInstance != XR_NULL_HANDLE) xrDestroyInstance(mInstance);
    jobject video, stats, menu;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        video         = mVideoSurface;
        stats         = mStatsSurface;
        menu          = mMenuSurface;
        mVideoSurface = mStatsSurface = mMenuSurface = nullptr;
    }
    if (video) env->DeleteGlobalRef(video);
    if (stats) env->DeleteGlobalRef(stats);
    if (menu) env->DeleteGlobalRef(menu);
    if (mActivity) env->DeleteGlobalRef(mActivity);
    mVideoChain = mStatsChain = mMenuChain = XR_NULL_HANDLE;
    mViewSpace                = XR_NULL_HANDLE;
    mSession                  = XR_NULL_HANDLE;
    mInstance                 = XR_NULL_HANDLE;
    mActivity = nullptr;
    mHintedThreads.clear();
    mRunning = mVideoAllowed = false;
}
