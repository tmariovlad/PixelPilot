package com.openipc.xr;

import java.util.Locale;

/**
 * What the pilot must be told about the video, decided once per panel tick from primitive inputs.
 *
 * <p>The XR video is a compositor layer that keeps showing the last decoded frame when the stream stops, so a
 * frozen picture looks live. This classifier turns "no new frames" into an explicit state with its most likely
 * cause, so the panel can say NO SIGNAL / WRONG KEY / ... instead of a small "0 fps". Audit:
 * docs/xr/research/2026-09-27-xr-ux-audit.md (X06, X08, X09, X10).
 *
 * <p>Rules:
 * <ul>
 *   <li>Frames arriving means {@link Kind#OK}, whatever the adapter or link say: APFPV over the Quest's own Wi-Fi
 *       delivers video with no adapter at all.</li>
 *   <li>Stalled = no frame for {@code max(250 ms, 6 frame periods)}. Leaving a non-OK state needs
 *       {@link #RECOVERY_FRAMES} fresh frames, so the alert does not flicker at the edge of range.</li>
 *   <li>Without frames, the cause is named in priority order: no adapter, no wfb packets, packets that do not
 *       decrypt (wrong key), no frame yet since the video was attached, otherwise a stall.</li>
 *   <li>Wrong key only after every packet has failed to decrypt for {@link #WRONG_KEY_NS}: a wrong key never
 *       recovers, while one all-failing stats window right after an RTL replug did (2026-09-28, cause still open;
 *       the native DecErrProbe logs it). Before that the stall is named as for any other missing video.</li>
 *   <li>"No packets" is read from the wfb-ng stats as they come: a window with {@code packets == 0}, or no stats for
 *       {@link #STATS_STALE_NS}. The native side owns the dead-link signal (it reports empty windows); this class
 *       does not guess it from repeated counters. Until the native side does that, a dead link shows as a stall.</li>
 *   <li>While a preset switch from the menu runs ({@link #setSwitching}), missing video is the expected gap
 *       (docs/xr/presets-design.md, "What a mode switch costs"): {@link Kind#SWITCHING}, no alarm. A setup error or a
 *       missing adapter is still named, and when the switch ends without video the usual diagnosis returns.</li>
 * </ul>
 * Not thread-safe; call {@link #update} from one thread (the UI thread's stats tick).
 */
public final class SignalState {

    public enum Kind { OK, CONFIG_ERROR, NO_ADAPTER, NO_PACKETS, WRONG_KEY, WAITING_FOR_VIDEO, VIDEO_STALLED, HOLD, SWITCHING }

    /** Link counters of the last wfb-ng stats window; null fields are expressed by {@link #NONE}. */
    public static final class Link {
        public static final Link NONE = new Link(0, 0, 0);
        final int packets, decOk, decErr;

        public Link(int packets, int decOk, int decErr) {
            this.packets = packets;
            this.decOk = decOk;
            this.decErr = decErr;
        }
    }

    public static final long MIN_STALL_NS = 250_000_000L;
    public static final int STALL_FRAMES = 6;
    public static final int RECOVERY_FRAMES = 5;
    /** Stats older than this mean the link thread stopped reporting. */
    public static final long STATS_STALE_NS = 1_500_000_000L;
    /** Packets must fail to decrypt this long, with none decrypting, before the key is blamed. */
    public static final long WRONG_KEY_NS = 2_000_000_000L;

    private Kind kind = Kind.WAITING_FOR_VIDEO;
    private long attachNs;
    private long lastFrameNs;          // 0 = no frame since attach
    private int recoveryFrames;
    private long allFailSinceNs = -1;  // every packet failing to decrypt since then; -1 = not now
    private boolean recovering;
    private String configError;        // non-null: the link cannot start at all (e.g. an invalid gs.key)
    private boolean switching;         // a menu-initiated preset switch runs: a gap in the video is expected
    private String message = message(Kind.WAITING_FOR_VIDEO, 0);

    /**
     * A setup problem that stops the link from starting, shown instead of any link diagnosis while no frames arrive;
     * null clears it.
     */
    public void setConfigError(String problem) {
        configError = problem;
    }

    /** A preset switch started from the menu runs (true) or ended (false); the air owns its outcome. */
    public void setSwitching(boolean switching) {
        this.switching = switching;
    }

    /** Video (re)attached to the compositor surface: forget frames from the previous attachment. */
    public void reset(long nowNs) {
        attachNs = nowNs;
        lastFrameNs = 0;
        recoveryFrames = 0;
        allFailSinceNs = -1;
        recovering = false;
        kind = Kind.WAITING_FOR_VIDEO;
        message = message(kind, 0);
    }

    /**
     * @param nowNs          CLOCK_MONOTONIC now (System.nanoTime on Android)
     * @param frameReadyNs   decoded-frame times since the previous call, same clock
     * @param framePeriodNs  expected frame period (0 if unknown)
     * @param adapterPresent an RTL adapter is open; false in the UDP fallback
     * @param link           latest wfb-ng stats, or {@link Link#NONE}
     * @param statsAgeNs     age of {@code link}; Long.MAX_VALUE if none ever arrived
     */
    public Kind update(long nowNs, long[] frameReadyNs, long framePeriodNs, boolean adapterPresent, Link link,
                       long statsAgeNs) {
        return update(nowNs, frameReadyNs, framePeriodNs, adapterPresent, link, statsAgeNs, false);
    }

    /**
     * As above; {@code holdingForKeyframe}: freeze_until_idr is holding the last good frame until a key frame arrives
     * (FreezeUntilIdr.h). Frames missing for that reason, with packets arriving, are a {@link Kind#HOLD}, not a stall.
     */
    public Kind update(long nowNs, long[] frameReadyNs, long framePeriodNs, boolean adapterPresent, Link link,
                       long statsAgeNs, boolean holdingForKeyframe) {
        long newest = lastFrameNs;
        // A hold ends on a clean key frame, so the video is OK at once, with no resuming phase.
        boolean hadStall = kind != Kind.OK && kind != Kind.HOLD;
        for (long t : frameReadyNs) {
            if (t < attachNs) continue;             // decoded before this attachment
            if (hadStall && t > lastFrameNs) recoveryFrames++;
            if (t > newest) newest = t;
        }
        lastFrameNs = newest;
        boolean allFail = statsAgeNs <= STATS_STALE_NS && link.packets > 0 && link.decErr > 0 && link.decOk == 0;
        if (!allFail) allFailSinceNs = -1;
        else if (allFailSinceNs < 0) allFailSinceNs = nowNs;

        long stallNs = Math.max(MIN_STALL_NS, STALL_FRAMES * Math.max(0, framePeriodNs));
        boolean fresh = lastFrameNs != 0 && nowNs - lastFrameNs <= stallNs;
        if (fresh && (!hadStall || recoveryFrames >= RECOVERY_FRAMES)) {
            kind = Kind.OK;
            recoveryFrames = 0;
        } else if (!fresh) {
            recoveryFrames = 0;
            kind = cause(nowNs, adapterPresent, link, statsAgeNs, holdingForKeyframe);
        }
        // fresh but still recovering: keep the previous non-OK kind until enough frames arrived
        recovering = fresh && kind != Kind.OK;
        long sinceNs = lastFrameNs == 0 ? nowNs - attachNs : nowNs - lastFrameNs;
        message = recovering ? "VIDEO RESUMING"
                : kind == Kind.CONFIG_ERROR ? "SETUP: " + configError : message(kind, sinceNs);
        return kind;
    }

    private Kind cause(long nowNs, boolean adapterPresent, Link link, long statsAgeNs, boolean holding) {
        if (configError != null) return Kind.CONFIG_ERROR;
        if (!adapterPresent) return Kind.NO_ADAPTER;
        if (switching) return Kind.SWITCHING;
        boolean packets = statsAgeNs <= STATS_STALE_NS && link.packets > 0;
        if (!packets) return Kind.NO_PACKETS;
        if (allFailSinceNs >= 0 && nowNs - allFailSinceNs >= WRONG_KEY_NS) return Kind.WRONG_KEY;
        if (lastFrameNs == 0) return Kind.WAITING_FOR_VIDEO;
        return holding ? Kind.HOLD : Kind.VIDEO_STALLED;
    }

    public Kind kind() {
        return kind;
    }

    /**
     * True for a fault the pilot has to act on (no adapter, no signal, wrong key, a stall); false when the video is
     * OK, has not started yet, is resuming, is held for a key frame, or is in an expected preset-switch gap. The panel
     * shows the first in red and the others in amber.
     */
    public boolean needsAction() {
        return kind != Kind.OK && kind != Kind.WAITING_FOR_VIDEO && kind != Kind.HOLD && kind != Kind.SWITCHING
                && !recovering;
    }

    /** One short line for the panel headline (at most ~40 characters, so it fits the band); empty when OK. */
    public String message() {
        return message;
    }

    static String message(Kind kind, long sinceNs) {
        double s = sinceNs / 1e9;
        switch (kind) {
            case NO_ADAPTER:
                return "NO ADAPTER - plug in the RTL8812AU";
            case NO_PACKETS:
                return String.format(Locale.US, "NO SIGNAL (%.1f s)", s);
            case WRONG_KEY:
                return "WRONG KEY - check gs.key";
            case WAITING_FOR_VIDEO:
                return String.format(Locale.US, "WAITING FOR VIDEO (%.1f s)", s);
            case VIDEO_STALLED:
                return String.format(Locale.US, "VIDEO STALLED (%.1f s)", s);
            case HOLD:
                return String.format(Locale.US, "HOLD - WAITING FOR KEYFRAME (%.1f s)", s);
            case SWITCHING:
                return String.format(Locale.US, "SWITCHING MODE (%.1f s)", s);
            default:
                return "";
        }
    }
}
