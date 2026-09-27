package com.openipc.xr;

/**
 * Debug builds only: controller input sent by adb, so the preset menu can be driven without hands on the controller.
 * The bits go into {@link XrBridge#injectInputEvents(int)}, the same path as the native XrInput. Example:
 * {@code adb shell am broadcast -a com.openipc.pixelpilot.xr.DEBUG_INPUT --es input right} (a hold is "press",
 * then "release" 1+ s later; scripts/quest/preset_flow.py does that).
 */
public final class DebugInput {
    public static final String ACTION = "com.openipc.pixelpilot.xr.DEBUG_INPUT";
    public static final String EXTRA = "input";

    private DebugInput() {
    }

    /** The input bits for a name (left, right, up, down, press, release, detail, visibility), 0 if unknown. */
    public static int bits(String name) {
        if (name == null) return 0;
        switch (name) {
            case "left": return XrBridge.INPUT_STICK_LEFT;
            case "right": return XrBridge.INPUT_STICK_RIGHT;
            case "up": return XrBridge.INPUT_STICK_UP;
            case "down": return XrBridge.INPUT_STICK_DOWN;
            case "press": return XrBridge.INPUT_STICK_PRESS;
            case "release": return XrBridge.INPUT_STICK_RELEASE;
            case "detail": return XrBridge.INPUT_PANEL_DETAIL;
            case "visibility": return XrBridge.INPUT_PANEL_VISIBILITY;
            default: return 0;
        }
    }
}
