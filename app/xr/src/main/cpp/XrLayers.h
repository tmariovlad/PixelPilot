#ifndef PIXELPILOT_XRLAYERS_H
#define PIXELPILOT_XRLAYERS_H

#include "XrIncludes.h"

// Mirrors com.openipc.xr.LayerLayout (which owns the math).
struct LayerConfig
{
    bool  cylinder     = false;
    bool  flip         = true;
    float videoWidthM  = 2.31f;
    float videoHeightM = 1.30f;
    float videoZ       = -2.f;
    float cylRadius    = 2.f;
    float cylAngleRad  = 1.047f;
    float cylAspect    = 16.f / 9.f;
    float statsWidthM  = 0.81f;
    float statsHeightM = 0.40f;
    float statsY       = -0.92f;
    float statsZ       = -2.f;
    int   imageW       = 1280;   // the video's visible rect in the swapchain image (the decoder's display crop)
    int   imageH       = 720;
    int   bufferW      = 1280;   // the swapchain's size = the decoded buffer (e.g. 1088 rows for 1080 visible)
    int   bufferH      = 720;
    int   rectX        = 0;      // the visible rect's origin in the buffer
    int   rectY        = 0;
    int   statsImageW  = 512;
    int   statsImageH  = 256;
    // The menu quad (docs/xr/menu-design.md), submitted only while menuVisible.
    bool  menuVisible  = false;
    float menuWidthM   = 0.9f;
    float menuHeightM  = 0.5625f;
    float menuX        = 1.6f;
    float menuY        = 0.f;
    float menuZ        = -2.f;
    float menuYawRad   = 0.f;
    int   menuImageW   = 1024;
    int   menuImageH   = 640;
};

// Builds the head-locked layers (video, stats, and the menu while it is open) for one xrEndFrame. The structs live here so the pointers
// handed to xrEndFrame stay valid until it returns.
class XrLayers
{
  public:
    void build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats, XrSwapchain menu,
               bool imageLayoutEnabled, bool cylinderEnabled);
    const XrCompositionLayerBaseHeader* const* layers() const { return mPtrs; }
    uint32_t                                   count() const { return mCount; }

  private:
    XrCompositionLayerQuad              mVideoQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerCylinderKHR       mVideoCylinder{XR_TYPE_COMPOSITION_LAYER_CYLINDER_KHR};
    XrCompositionLayerQuad              mStatsQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerQuad              mMenuQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerImageLayoutFB     mFlip{XR_TYPE_COMPOSITION_LAYER_IMAGE_LAYOUT_FB};
    const XrCompositionLayerBaseHeader* mPtrs[3]{};
    uint32_t                            mCount = 0;
};

#endif  // PIXELPILOT_XRLAYERS_H
