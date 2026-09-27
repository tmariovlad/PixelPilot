#include "XrInput.h"

#include <android/log.h>

#include <cstring>

namespace {
constexpr const char* kTag = "pixelpilot-xr-input";

XrPath path(XrInstance instance, const char* s)
{
    XrPath p = XR_NULL_PATH;
    xrStringToPath(instance, s, &p);
    return p;
}

bool createAction(XrActionSet set, const char* name, const char* localized, XrAction& out)
{
    XrActionCreateInfo info{XR_TYPE_ACTION_CREATE_INFO};
    info.actionType = XR_ACTION_TYPE_BOOLEAN_INPUT;
    std::strncpy(info.actionName, name, XR_MAX_ACTION_NAME_SIZE - 1);
    std::strncpy(info.localizedActionName, localized, XR_MAX_LOCALIZED_ACTION_NAME_SIZE - 1);
    return XR_SUCCEEDED(xrCreateAction(set, &info, &out));
}

// Suggests one profile's bindings; a runtime that does not know the profile rejects it, which is not an error here.
void suggest(XrInstance instance, const char* profile, const XrActionSuggestedBinding* b, uint32_t n)
{
    XrInteractionProfileSuggestedBinding s{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
    s.interactionProfile = path(instance, profile);
    s.suggestedBindings = b;
    s.countSuggestedBindings = n;
    const XrResult r = xrSuggestInteractionProfileBindings(instance, &s);
    if (XR_FAILED(r)) __android_log_print(ANDROID_LOG_WARN, kTag, "bindings for %s rejected: %d", profile, r);
}
}  // namespace

bool XrInput::setup(XrInstance instance, XrSession session)
{
    XrActionSetCreateInfo setInfo{XR_TYPE_ACTION_SET_CREATE_INFO};
    std::strncpy(setInfo.actionSetName, "viewer", XR_MAX_ACTION_SET_NAME_SIZE - 1);
    std::strncpy(setInfo.localizedActionSetName, "Viewer", XR_MAX_LOCALIZED_ACTION_SET_NAME_SIZE - 1);
    if (XR_FAILED(xrCreateActionSet(instance, &setInfo, &mSet)) ||
        !createAction(mSet, "panel_detail", "Panel detail", mDetail) ||
        !createAction(mSet, "panel_visibility", "Show or hide panel", mVisibility))
    {
        __android_log_print(ANDROID_LOG_WARN, kTag, "input unavailable: action set/actions not created");
        destroy();
        return false;
    }

    const XrActionSuggestedBinding touch[] = {
        {mDetail, path(instance, "/user/hand/right/input/a/click")},
        {mDetail, path(instance, "/user/hand/left/input/x/click")},
        {mVisibility, path(instance, "/user/hand/right/input/b/click")},
        {mVisibility, path(instance, "/user/hand/left/input/y/click")},
    };
    suggest(instance, "/interaction_profiles/oculus/touch_controller", touch, 4);
    const XrActionSuggestedBinding simple[] = {
        {mDetail, path(instance, "/user/hand/right/input/select/click")},
        {mDetail, path(instance, "/user/hand/left/input/select/click")},
    };
    suggest(instance, "/interaction_profiles/khr/simple_controller", simple, 2);

    XrSessionActionSetsAttachInfo attach{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};
    attach.countActionSets = 1;
    attach.actionSets = &mSet;
    if (XR_FAILED(xrAttachSessionActionSets(session, &attach)))
    {
        __android_log_print(ANDROID_LOG_WARN, kTag, "input unavailable: action set not attached");
        destroy();
        return false;
    }
    mReady = true;
    __android_log_print(ANDROID_LOG_INFO, kTag, "input ready (A/X/select: panel detail, B/Y: show/hide panel)");
    return true;
}

bool XrInput::pressed(XrSession session, XrAction action)
{
    XrActionStateGetInfo get{XR_TYPE_ACTION_STATE_GET_INFO};
    get.action = action;
    XrActionStateBoolean state{XR_TYPE_ACTION_STATE_BOOLEAN};
    if (XR_FAILED(xrGetActionStateBoolean(session, &get, &state))) return false;
    return state.isActive && state.changedSinceLastSync && state.currentState;   // rising edge only
}

void XrInput::poll(XrSession session)
{
    if (!mReady) return;
    XrActiveActionSet active{mSet, XR_NULL_PATH};
    XrActionsSyncInfo sync{XR_TYPE_ACTIONS_SYNC_INFO};
    sync.countActiveActionSets = 1;
    sync.activeActionSets = &active;
    if (xrSyncActions(session, &sync) != XR_SUCCESS) return;   // e.g. XR_SESSION_NOT_FOCUSED: no input to read
    uint32_t events = 0;
    if (pressed(session, mDetail)) events |= kPanelDetail;
    if (pressed(session, mVisibility)) events |= kPanelVisibility;
    if (events) mEvents.fetch_or(events);
}

void XrInput::destroy()
{
    mReady = false;
    if (mSet != XR_NULL_HANDLE) xrDestroyActionSet(mSet);   // destroys its actions too
    mSet = XR_NULL_HANDLE;
    mDetail = mVisibility = XR_NULL_HANDLE;
}
