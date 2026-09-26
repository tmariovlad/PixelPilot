#include "EglContext.h"
#include <EGL/eglext.h>

bool EglContext::create()
{
    mDisplay = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (mDisplay == EGL_NO_DISPLAY || eglInitialize(mDisplay, nullptr, nullptr) != EGL_TRUE) return false;
    const EGLint attribs[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
                              EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT_KHR, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                              EGL_NONE};
    EGLint n = 0;
    if (eglChooseConfig(mDisplay, attribs, &mConfig, 1, &n) != EGL_TRUE || n < 1) return false;
    const EGLint ctxAttribs[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    mContext = eglCreateContext(mDisplay, mConfig, EGL_NO_CONTEXT, ctxAttribs);
    if (mContext == EGL_NO_CONTEXT) return false;
    const EGLint pbuffer[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
    mSurface = eglCreatePbufferSurface(mDisplay, mConfig, pbuffer);
    if (mSurface == EGL_NO_SURFACE) return false;
    return eglMakeCurrent(mDisplay, mSurface, mSurface, mContext) == EGL_TRUE;
}

void EglContext::destroy()
{
    if (mDisplay == EGL_NO_DISPLAY) return;
    eglMakeCurrent(mDisplay, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (mSurface != EGL_NO_SURFACE) eglDestroySurface(mDisplay, mSurface);
    if (mContext != EGL_NO_CONTEXT) eglDestroyContext(mDisplay, mContext);
    eglTerminate(mDisplay);
    mDisplay = EGL_NO_DISPLAY;
    mConfig  = nullptr;
    mContext = EGL_NO_CONTEXT;
    mSurface = EGL_NO_SURFACE;
}
