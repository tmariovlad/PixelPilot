#ifndef PIXELPILOT_EGLCONTEXT_H
#define PIXELPILOT_EGLCONTEXT_H

#include <EGL/egl.h>

// Minimal pbuffer EGL context. OpenXR's GLES binding needs one to create a session, even though
// nothing renders with GL here: video and stats are Android surfaces the compositor samples.
class EglContext
{
  public:
    // Creates the context and makes it current on the calling thread.
    bool create();
    void destroy();
    EGLDisplay display() const { return mDisplay; }
    EGLConfig  config() const { return mConfig; }
    EGLContext context() const { return mContext; }

  private:
    EGLDisplay mDisplay = EGL_NO_DISPLAY;
    EGLConfig  mConfig  = nullptr;
    EGLContext mContext = EGL_NO_CONTEXT;
    EGLSurface mSurface = EGL_NO_SURFACE;
};

#endif  // PIXELPILOT_EGLCONTEXT_H
