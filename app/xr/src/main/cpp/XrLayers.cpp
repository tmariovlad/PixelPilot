#include "XrLayers.h"

#include <cmath>

namespace
{
XrPosef pose(float x, float y, float z)
{
    XrPosef p{};
    p.orientation.w = 1.f;
    p.position      = {x, y, z};
    return p;
}

// Turned about the vertical axis, so a quad off to the side faces the eye.
XrPosef poseYaw(float x, float y, float z, float yawRad)
{
    XrPosef p       = pose(x, y, z);
    p.orientation.y = std::sin(yawRad / 2.f);
    p.orientation.w = std::cos(yawRad / 2.f);
    return p;
}

XrSwapchainSubImage subImage(XrSwapchain swapchain, int w, int h, int x = 0, int y = 0)
{
    XrSwapchainSubImage s{};
    s.swapchain       = swapchain;
    s.imageRect       = {{x, y}, {w, h}};
    s.imageArrayIndex = 0;
    return s;
}
}  // namespace

void XrLayers::build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats, XrSwapchain menu,
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
        mVideoCylinder.subImage      = subImage(video, c.imageW, c.imageH, c.rectX, c.rectY);
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
        mVideoQuad.subImage      = subImage(video, c.imageW, c.imageH, c.rectX, c.rectY);
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

    if (c.menuVisible && menu != XR_NULL_HANDLE)
    {
        mMenuQuad.next          = next;   // an Android surface, oriented like the stats panel
        mMenuQuad.layerFlags    = XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT;
        mMenuQuad.space         = viewSpace;
        mMenuQuad.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
        mMenuQuad.subImage      = subImage(menu, c.menuImageW, c.menuImageH);
        mMenuQuad.pose          = poseYaw(c.menuX, c.menuY, c.menuZ, c.menuYawRad);
        mMenuQuad.size          = {c.menuWidthM, c.menuHeightM};
        mPtrs[2]                = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mMenuQuad);
        mCount                  = 3;
    }
}
