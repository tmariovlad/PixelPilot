#include <jni.h>
#include "XrRuntime.h"

namespace
{
struct Handle
{
    XrRuntime runtime;
    jobject   bridge = nullptr;  // global ref to the XrBridge
};

Handle* handle(jlong h) { return reinterpret_cast<Handle*>(h); }
}  // namespace

#define XR_JNI(ret, name) extern "C" JNIEXPORT ret JNICALL Java_com_openipc_xr_XrBridge_##name

XR_JNI(jlong, nativeCreate)(JNIEnv* env, jobject thiz)
{
    auto* h   = new Handle();
    h->bridge = env->NewGlobalRef(thiz);
    return reinterpret_cast<jlong>(h);
}

XR_JNI(jboolean, nativeStart)
(JNIEnv* env, jobject, jlong h, jobject activity, jfloat refreshHz, jboolean useTimestamps, jboolean perfHigh)
{
    Handle* p  = handle(h);
    JavaVM* vm = nullptr;
    env->GetJavaVM(&vm);
    jclass    cls    = env->GetObjectClass(p->bridge);
    jmethodID onEvt  = env->GetMethodID(cls, "onNativeSessionEvent", "(I)V");
    jobject   bridge = p->bridge;
    XrStartConfig cfg;
    cfg.refreshHz         = refreshHz;
    cfg.useTimestamps     = useTimestamps;
    cfg.perfSustainedHigh = perfHigh;
    // Called on the XR thread, which is attached for its whole life.
    auto listener = [vm, bridge, onEvt](SessionEvent e)
    {
        JNIEnv* threadEnv = nullptr;
        if (vm->GetEnv(reinterpret_cast<void**>(&threadEnv), JNI_VERSION_1_6) != JNI_OK) return;
        threadEnv->CallVoidMethod(bridge, onEvt, static_cast<jint>(e));
        if (threadEnv->ExceptionCheck()) threadEnv->ExceptionClear();
    };
    return p->runtime.start(vm, env->NewGlobalRef(activity), cfg, listener) ? JNI_TRUE : JNI_FALSE;
}

XR_JNI(jstring, nativeError)(JNIEnv* env, jobject, jlong h)
{
    return env->NewStringUTF(handle(h)->runtime.error().c_str());
}

XR_JNI(jobject, nativeVideoSurface)(JNIEnv*, jobject, jlong h) { return handle(h)->runtime.videoSurface(); }

XR_JNI(jobject, nativeStatsSurface)(JNIEnv*, jobject, jlong h) { return handle(h)->runtime.statsSurface(); }

XR_JNI(void, nativeSetLayout)
(JNIEnv* env, jobject, jlong h, jboolean cylinder, jboolean flip, jfloatArray values, jint imageW, jint imageH)
{
    jfloat v[12];
    env->GetFloatArrayRegion(values, 0, 12, v);
    LayerConfig c;
    c.cylinder     = cylinder;
    c.flip         = flip;
    c.videoWidthM  = v[0];
    c.videoHeightM = v[1];
    c.videoZ       = v[2];
    c.cylRadius    = v[3];
    c.cylAngleRad  = v[4];
    c.cylAspect    = v[5];
    c.statsWidthM  = v[6];
    c.statsHeightM = v[7];
    c.statsY       = v[8];
    c.statsZ       = v[9];
    c.statsImageW  = static_cast<int>(v[10]);
    c.statsImageH  = static_cast<int>(v[11]);
    c.imageW       = imageW;
    c.imageH       = imageH;
    handle(h)->runtime.setLayerConfig(c);
}

XR_JNI(void, nativeSetWorkerThreads)(JNIEnv* env, jobject, jlong h, jintArray tids)
{
    const jsize      n = env->GetArrayLength(tids);
    std::vector<int> v(static_cast<size_t>(n));
    if (n > 0) env->GetIntArrayRegion(tids, 0, n, v.data());
    handle(h)->runtime.setWorkerThreads(v);
}

XR_JNI(jfloatArray, nativeInfo)(JNIEnv* env, jobject, jlong h)
{
    const XrRuntimeInfo i   = handle(h)->runtime.info();
    const jfloat        v[] = {i.refreshHz, i.requestedHz, i.compositorGpuMs, i.droppedFrames, i.motionToPhotonMs};
    jfloatArray         out = env->NewFloatArray(5);
    env->SetFloatArrayRegion(out, 0, 5, v);
    return out;
}

// {displayTimeNs, periodNs, monotonic (1/0)} of the latest xrWaitFrame.
XR_JNI(jlongArray, nativeDisplayGrid)(JNIEnv* env, jobject, jlong h)
{
    const XrDisplayGrid g   = handle(h)->runtime.displayGrid();
    const jlong         v[] = {g.displayTimeNs, g.periodNs, g.monotonic ? 1 : 0};
    jlongArray          out = env->NewLongArray(3);
    env->SetLongArrayRegion(out, 0, 3, v);
    return out;
}

XR_JNI(jint, nativeTakeInputEvents)(JNIEnv*, jobject, jlong h)
{
    return static_cast<jint>(handle(h)->runtime.takeInputEvents());
}

XR_JNI(void, nativeDestroy)(JNIEnv* env, jobject, jlong h)
{
    Handle* p = handle(h);
    p->runtime.stop();
    env->DeleteGlobalRef(p->bridge);
    delete p;
}
