#pragma once

#include <atomic>
#include <cstdint>

#include "XrIncludes.h"

// Minimal controller / hand input for the XR viewer (audit X01): two buttons that change the stats panel.
//
// The layers are head-locked (VIEW space), so there is nothing to recenter. The two actions are:
//   kPanelDetail     - A (right Touch), X (left Touch) or select/pinch (simple controller): compact <-> detailed
//   kPanelVisibility - B (right Touch) or Y (left Touch): hide / show the panel (alerts still show)
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
    };

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

    XrActionSet mSet = XR_NULL_HANDLE;
    XrAction mDetail = XR_NULL_HANDLE;
    XrAction mVisibility = XR_NULL_HANDLE;
    bool mReady = false;
    std::atomic<uint32_t> mEvents{0};
};
