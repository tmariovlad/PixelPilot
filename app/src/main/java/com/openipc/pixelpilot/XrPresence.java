package com.openipc.pixelpilot;

/**
 * Whether the XR viewer is started (between onStart and onStop), for {@link UsbAttachActivity} (audit X15). A count,
 * not a flag: a relaunch can overlap the old instance's onStop with the new one's onStart. onStart/onStop rather than
 * onResume/onPause, because starting the attach trampoline pauses XR before the trampoline runs, while a no-display
 * activity that finishes at once never stops it.
 */
final class XrPresence {
    private static int started;

    private XrPresence() {
    }

    static synchronized void onStart() {
        started++;
    }

    static synchronized void onStop() {
        if (started > 0) started--;
    }

    static synchronized boolean started() {
        return started > 0;
    }
}
