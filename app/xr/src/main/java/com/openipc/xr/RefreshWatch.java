package com.openipc.xr;

import java.util.Locale;

/**
 * Watches the display refresh rate the runtime reports against the one the app requested. Horizon OS may lower it to
 * 72 Hz under thermal throttling without the app asking (docs/xr/display-latency.md), which costs latency after the
 * compositor latch; this makes such a change visible in the log and on the HUD.
 */
public final class RefreshWatch {
    /** Runtimes report e.g. 120.00001 or 119.7 for "120": anything within this is the same rate. */
    static final float SAME_HZ = 0.5f;

    private float lastHz = -1f;

    /** A log line when the reported rate is first known or has changed since the last sample, else null. */
    public String onSample(float appliedHz, float requestedHz) {
        if (appliedHz <= 0f) return null;  // not reported (yet)
        if (lastHz > 0f && Math.abs(appliedHz - lastHz) <= SAME_HZ) return null;
        String line = lastHz <= 0f
                ? String.format(Locale.US, "XR refresh applied %.0f Hz (%s)", appliedHz, request(requestedHz))
                : String.format(Locale.US, "XR refresh %.0f -> %.0f Hz (%s)%s", lastHz, appliedHz,
                        request(requestedHz), hudSuffix(appliedHz, requestedHz));
        lastHz = appliedHz;
        return line;
    }

    /** The runtime can report a rate before the app's request is made (it starts the session at its own default). */
    private static String request(float requestedHz) {
        return requestedHz > 0f ? String.format(Locale.US, "requested %.0f", requestedHz) : "not requested yet";
    }

    /** " BELOW REQUEST" when the runtime reports a rate under the requested one; "" otherwise or when unknown. */
    public static String hudSuffix(float appliedHz, float requestedHz) {
        return appliedHz > 0f && requestedHz > 0f && appliedHz < requestedHz - SAME_HZ ? " BELOW REQUEST" : "";
    }
}
