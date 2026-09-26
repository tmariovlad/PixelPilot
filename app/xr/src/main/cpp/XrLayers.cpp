#include "XrLayers.h"

namespace
{
XrPosef pose(float x, float y, float z)
{
    XrPosef p{};
    p.orientation.w = 1.f;
    p.position      = {x, y, z};
    return p;
}

XrSwapchainSubImage subImage(XrSwapchain swapchain, int w, int h)
{
    XrSwapchainSubImage s{};
    s.swapchain       = swapchain;
    s.imageRect       = {{0, 0}, {w, h}};
    s.imageArrayIndex = 0;
    return s;
}
}  // namespace

void XrLayers::build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats,
                     bool imageLayoutEnabled, bool cylinderEnabled)
{
    // Android surfaces arrive top-down; negative subImage heights no longer work on current Horizon OS
    // (CitraVR utils/Common.h), so the flip goes through XR_FB_composition_layer_image_layout.
    mFlip.flags      = XR_COMPOSITION_LAYER_IMAGE_LAYOUT_VERTICAL_FLIP_BIT_FB;
    const void* next = (imageLayoutEnabled && c.flip) ? &mFlip : nullptr;

    if (c.cylinder && cylinderEnabled)
    {
        mVideoCylinder.next          = next;
        mVideoCylinder.layerFlags    = 0;
        mVideoCylinder.space         = viewSpace;
        mVideoCylinder.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
        mVideoCylinder.subImage      = subImage(video, c.imageW, c.imageH);
        mVideoCylinder.pose          = pose(0.f, 0.f, 0.f);
        mVideoCylinder.radius        = c.cylRadius;
        mVideoCylinder.centralAngle  = c.cylAngleRad;
        mVideoCylinder.aspectRatio   = c.cylAspect;
        mPtrs[0] = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mVideoCylinder);
    }
    else
    {
        mVideoQuad.next          = next;
        mVideoQuad.layerFlags    = 0;
        mVideoQuad.space         = viewSpace;
        mVideoQuad.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
        mVideoQuad.subImage      = subImage(video, c.imageW, c.imageH);
        mVideoQuad.pose          = pose(0.f, 0.f, c.videoZ);
        mVideoQuad.size          = {c.videoWidthM, c.videoHeightM};
        mPtrs[0] = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mVideoQuad);
    }

    mStatsQuad.next          = next;
    mStatsQuad.layerFlags    = XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT;
    mStatsQuad.space         = viewSpace;
    mStatsQuad.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
    mStatsQuad.subImage      = subImage(stats, c.statsImageW, c.statsImageH);
    mStatsQuad.pose          = pose(0.f, c.statsY, c.statsZ);
    mStatsQuad.size          = {c.statsWidthM, c.statsHeightM};
    mPtrs[1]                 = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mStatsQuad);
    mCount                   = 2;
}
