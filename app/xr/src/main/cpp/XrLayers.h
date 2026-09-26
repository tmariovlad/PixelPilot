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
    int   imageW       = 1280;
    int   imageH       = 720;
    int   statsImageW  = 512;
    int   statsImageH  = 256;
};

// Builds the two head-locked layers for one xrEndFrame. The structs live here so the pointers
// handed to xrEndFrame stay valid until it returns.
class XrLayers
{
  public:
    void build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats,
               bool imageLayoutEnabled, bool cylinderEnabled);
    const XrCompositionLayerBaseHeader* const* layers() const { return mPtrs; }
    uint32_t                                   count() const { return mCount; }

  private:
    XrCompositionLayerQuad              mVideoQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerCylinderKHR       mVideoCylinder{XR_TYPE_COMPOSITION_LAYER_CYLINDER_KHR};
    XrCompositionLayerQuad              mStatsQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerImageLayoutFB     mFlip{XR_TYPE_COMPOSITION_LAYER_IMAGE_LAYOUT_FB};
    const XrCompositionLayerBaseHeader* mPtrs[2]{};
    uint32_t                            mCount = 0;
};

#endif  // PIXELPILOT_XRLAYERS_H
