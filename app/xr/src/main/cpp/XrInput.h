#pragma once

#include <atomic>
#include <cstdint>

#include "XrIncludes.h"

// Minimal controller / hand input for the XR viewer (audit X01): buttons that change the stats panel, and the
// thumbsticks for the preset menu (docs/xr/presets-design.md).
//
// The layers are head-locked (VIEW space), so there is nothing to recenter. The actions are:
//   kPanelDetail     - A (right Touch), X (left Touch) or select/pinch (simple controller): compact <-> detailed
//   kPanelVisibility - B (right Touch) or Y (left Touch): hide / show the panel (alerts still show)
//   kStick*          - a thumbstick flick on either Touch controller (past kFlickOn, re-armed below kFlickOff)
//   kStickPress/Release - either thumbstick click goes down / up (the menu times the hold)
//
// Cost on the frame path: poll() runs once per frame after xrEndFrame, with no allocation and no lock. Presses
// are handed to Java as atomic event bits that the UI thread takes in its stats tick, so the XR thread never calls
// into Java for input. Input that cannot be set up (a runtime without these profiles) is logged and skipped; the
// viewer works without it.
class XrInput {
  public:
    enum Event : uint32_t {
        kPanelDetail = 1u << 0,
        kPanelVisibility = 1u << 1,
        kStickLeft = 1u << 2,
        kStickRight = 1u << 3,
        kStickUp = 1u << 4,
        kStickDown = 1u << 5,
        kStickPress = 1u << 6,
        kStickRelease = 1u << 7,
    };
    static constexpr float kFlickOn = 0.7f;    // deflection that counts as a flick
    static constexpr float kFlickOff = 0.3f;   // back under this, the next flick can fire

    // After xrCreateSession, before xrBeginSession. Returns false if input is unavailable (not fatal).
    bool setup(XrInstance instance, XrSession session);
    // Once per frame on the XR thread. Only a FOCUSED session reports input; other states are ignored.
    void poll(XrSession session);
    // Pending events, cleared. Any thread.
    uint32_t take() { return mEvents.exchange(0); }
    // Before xrDestroySession.
    void destroy();

  private:
    bool pressed(XrSession session, XrAction action);
    uint32_t stickEvents(XrSession session);

    XrActionSet mSet = XR_NULL_HANDLE;
    XrAction mDetail = XR_NULL_HANDLE;
    XrAction mVisibility = XR_NULL_HANDLE;
    XrAction mStick = XR_NULL_HANDLE;        // vector2f per hand
    XrAction mStickClick = XR_NULL_HANDLE;
    XrPath mHands[2] = {XR_NULL_PATH, XR_NULL_PATH};
    uint32_t mFlick[2] = {0, 0};              // the flick each hand fired and has not released yet
    bool mReady = false;
    std::atomic<uint32_t> mEvents{0};
};
