#ifndef PIXELPILOT_XRRUNTIME_H
#define PIXELPILOT_XRRUNTIME_H

#include <atomic>
#include <functional>
#include <future>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>
#include "EglContext.h"
#include "XrIncludes.h"
#include "XrLayers.h"

// Matches XrBridge.SessionEvent ordinals.
enum class SessionEvent : int
{
    Active   = 0,  // session VISIBLE/FOCUSED: surfaces may be written
    Inactive = 1,  // leaving VISIBLE or stopping: the producer must stop before this returns
    Exiting  = 2,  // runtime asked the app to quit
};

struct XrStartConfig
{
    float refreshHz         = 120.f;
    bool  useTimestamps     = false;
    bool  perfSustainedHigh = true;
};

// Values < 0 mean "not available".
struct XrRuntimeInfo
{
    float refreshHz        = -1.f;
    float requestedHz      = -1.f;
    float compositorGpuMs  = -1.f;
    float droppedFrames    = -1.f;
    float motionToPhotonMs = -1.f;
};

// Owns the OpenXR instance, session and frame loop on its own thread (the EGL context lives there).
// Video and stats are Android surface swapchains: the compositor consumes whatever their producers
// queue, independently of this loop, which only re-submits the two layers every frame.
class XrRuntime
{
  public:
    using Listener = std::function<void(SessionEvent)>;

    ~XrRuntime();
    // Takes ownership of the global ref `activityGlobalRef`. Blocks until the session and both
    // surfaces exist (true) or setup failed (false, see error()).
    bool start(JavaVM* vm, jobject activityGlobalRef, const XrStartConfig& cfg, Listener listener);
    // Ends the session (Inactive is delivered first if needed) and joins the loop thread.
    void stop();

    jobject       videoSurface();
    jobject       statsSurface();
    void          setLayerConfig(const LayerConfig& c);
    // Threads outside this runtime that sit on the video path; hinted as renderer workers on the
    // XR thread once the session runs (xrSetAndroidApplicationThreadKHR).
    void          setWorkerThreads(const std::vector<int>& tids);
    XrRuntimeInfo info();
    std::string   error();

  private:
    void    threadMain(JavaVM* vm, XrStartConfig cfg, std::promise<bool> ready);
    bool    setup(JNIEnv* env);
    bool    fail(const std::string& what);
    bool    enabled(const char* ext) const { return mEnabled.count(ext) != 0; }
    void    loadFunctions();
    jobject createSurface(JNIEnv* env, int w, int h, bool useTimestamps, XrSwapchain& out);
    void    loop();
    void    pollEvents();
    void    onStateChanged(XrSessionState state);
    void    setVideoAllowed(bool allowed);
    void    renderFrame();
    void    endSession();
    void    requestExitAndDrain();
    void    applyRefreshRate();
    void    applyPerformanceHints();
    void    applyWorkerThreadHints();
    void    enableMetrics();
    void    readMetrics();
    float   queryMetric(XrPath path);
    void    teardown(JNIEnv* env);

    std::thread       mThread;
    std::atomic<bool> mExit{false};
    Listener          mListener;
    XrStartConfig     mCfg;
    JavaVM*           mVm       = nullptr;
    jobject           mActivity = nullptr;

    std::mutex    mMutex;  // guards mError, mLayerConfig, mResizePending, mInfo
    std::string   mError;
    LayerConfig   mLayerConfig;
    bool          mResizePending = false;
    std::vector<int> mWorkerThreads;    // requested (guarded by mMutex)
    std::set<int>    mHintedThreads;    // already hinted (XR thread only)
    XrRuntimeInfo mInfo;

    std::set<std::string> mEnabled;
    EglContext            mEgl;
    XrInstance            mInstance     = XR_NULL_HANDLE;
    XrSystemId            mSystemId     = XR_NULL_SYSTEM_ID;
    XrSession             mSession      = XR_NULL_HANDLE;
    XrSpace               mViewSpace    = XR_NULL_HANDLE;
    XrSwapchain           mVideoChain   = XR_NULL_HANDLE;
    XrSwapchain           mStatsChain   = XR_NULL_HANDLE;
    jobject               mVideoSurface = nullptr;
    jobject               mStatsSurface = nullptr;
    XrSessionState        mState        = XR_SESSION_STATE_UNKNOWN;
    bool                  mRunning      = false;
    bool                  mVideoAllowed = false;
    bool                  mRuntimeExit  = false;
    uint64_t              mFrames       = 0;
    XrLayers              mLayers;

    PFN_xrCreateSwapchainAndroidSurfaceKHR   pfnCreateSurface   = nullptr;
    PFN_xrEnumerateDisplayRefreshRatesFB     pfnEnumerateRates  = nullptr;
    PFN_xrRequestDisplayRefreshRateFB        pfnRequestRate     = nullptr;
    PFN_xrGetDisplayRefreshRateFB            pfnGetRate         = nullptr;
    PFN_xrPerfSettingsSetPerformanceLevelEXT pfnPerfLevel       = nullptr;
    PFN_xrSetAndroidApplicationThreadKHR     pfnSetThread       = nullptr;
    PFN_xrUpdateSwapchainFB                  pfnUpdateSwapchain = nullptr;
    PFN_xrSetPerformanceMetricsStateMETA     pfnSetMetricsState = nullptr;
    PFN_xrQueryPerformanceMetricsCounterMETA pfnQueryMetric     = nullptr;
    XrPath                                   mPathCompositorGpu  = XR_NULL_PATH;
    XrPath                                   mPathDroppedFrames  = XR_NULL_PATH;
    XrPath                                   mPathMotionToPhoton = XR_NULL_PATH;
};

#endif  // PIXELPILOT_XRRUNTIME_H
