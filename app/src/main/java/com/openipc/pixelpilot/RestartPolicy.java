package com.openipc.pixelpilot;

/**
 * When to restart a wfb-ng link whose RX thread has ended on its own (adapter lock timeout, CreateRtlDevice failure,
 * a runtime error inside devourer; audit X17, docs/xr/research/2026-09-27-xr-ux-audit.md).
 *
 * <p>The first restart is immediate; further ones wait 1, 2, 4, then 8 s, so a link that dies on every start does
 * not spin. After the link has stayed up for {@link #HEALTHY_RESET_MS} the backoff starts over. Feed it once per
 * tick with whether the link thread is alive. Not thread-safe; one tick thread.
 */
final class RestartPolicy {
    static final long[] BACKOFF_MS = {1_000, 2_000, 4_000, 8_000};
    static final long HEALTHY_RESET_MS = 10_000;

    private int attempts;
    private long nextAllowedMs = Long.MIN_VALUE;
    private long healthySinceMs = -1;

    /** @return true when the caller should restart the link now */
    boolean onTick(long nowMs, boolean alive) {
        if (alive) {
            if (healthySinceMs < 0) healthySinceMs = nowMs;
            if (nowMs - healthySinceMs >= HEALTHY_RESET_MS) {
                attempts = 0;
                nextAllowedMs = Long.MIN_VALUE;
            }
            return false;
        }
        healthySinceMs = -1;
        if (nowMs < nextAllowedMs) return false;
        nextAllowedMs = nowMs + BACKOFF_MS[Math.min(attempts, BACKOFF_MS.length - 1)];
        attempts++;
        return true;
    }

    /** Restarts attempted since the link was last healthy for {@link #HEALTHY_RESET_MS}. */
    int attempts() {
        return attempts;
    }
}
