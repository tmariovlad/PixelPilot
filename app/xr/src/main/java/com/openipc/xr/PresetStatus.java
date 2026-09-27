package com.openipc.xr;

import java.util.Locale;

/**
 * The panel headline about a preset change (docs/xr/presets-design.md): a countdown while a mode switch runs, then a
 * short result. It wins over the signal headline while a switch runs, because the frozen picture is expected then.
 * Headlines are at most {@link #MAX_HEADLINE} characters, like SignalState's. Pure logic with an injected clock.
 */
public final class PresetStatus {
    public static final int MAX_HEADLINE = 40;
    static final long RESULT_MS = 5000;
    private static final int LABEL = 14;

    private String headline = "";
    private long deadlineMs;         // countdown end while switching
    private long untilMs;            // a result shows until then
    private boolean switching;
    private String switchingLabel = "";

    /** A mode switch was accepted; the air reverts by itself at {@code deadlineMs} without a commit. */
    public void switching(String label, long deadlineMs) {
        switching = true;
        switchingLabel = trim(label);
        this.deadlineMs = deadlineMs;
    }

    /** The new mode was committed (or a bitrate change applied). */
    public void done(String what, long nowMs) {
        result(trim(what) + " ACTIVE", nowMs);
    }

    /** The air went back to {@code label} because the new mode never showed video. */
    public void reverted(String label, long nowMs) {
        result("REVERTED TO " + trim(label) + ": NO VIDEO", nowMs);
    }

    /** The active choice was saved as the air unit's default. */
    public void saved(String label, long nowMs) {
        result("DEFAULT SAVED: " + trim(label), nowMs);
    }

    /** The air refused or never answered. */
    public void refused(String reason, long nowMs) {
        result(("NOT APPLIED: " + reason).toUpperCase(Locale.US), nowMs);
    }

    public boolean switching() {
        return switching;
    }

    /** Empty when there is nothing to say. */
    public String headline(long nowMs) {
        String h;
        if (switching) {
            long left = Math.max(0, (deadlineMs - nowMs + 999) / 1000);
            h = String.format(Locale.US, "SWITCHING TO %s... %d s", switchingLabel, left);
        } else {
            h = nowMs < untilMs ? headline : "";
        }
        return h.length() > MAX_HEADLINE ? h.substring(0, MAX_HEADLINE) : h;
    }

    private void result(String h, long nowMs) {
        switching = false;
        headline = h;
        untilMs = nowMs + RESULT_MS;
    }

    private static String trim(String s) {
        return s.length() > LABEL ? s.substring(0, LABEL) : s;
    }
}
