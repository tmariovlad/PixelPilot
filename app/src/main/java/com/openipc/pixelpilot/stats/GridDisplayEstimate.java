package com.openipc.pixelpilot.stats;

/**
 * Time from a decoded frame to the next predicted display on the XR runtime's grid (XrBridge.DisplayGrid:
 * predictedDisplayTime in CLOCK_MONOTONIC ns + predictedDisplayPeriod). predictedDisplayTime is the midpoint of the
 * interval in which a frame is displayed (OpenXR XrFrameState), and the compositor latch comes before it, so this is
 * an estimate of "decoded → shown", not a measurement (docs/xr/display-latency.md).
 */
public final class GridDisplayEstimate implements DisplayEstimate {
    private final long displayTimeNs, periodNs;
    private final boolean monotonic;

    private GridDisplayEstimate(long displayTimeNs, long periodNs, boolean monotonic) {
        this.displayTimeNs = displayTimeNs;
        this.periodNs = periodNs;
        this.monotonic = monotonic;
    }

    public static GridDisplayEstimate of(long displayTimeNs, long periodNs, boolean monotonic) {
        return new GridDisplayEstimate(displayTimeNs, periodNs, monotonic);
    }

    @Override
    public long nsToDisplay(long decodedNs) {
        if (!monotonic || periodNs <= 0) return -1;
        long k = -Math.floorDiv(displayTimeNs - decodedNs, periodNs);   // ceil((decoded - anchor) / period)
        return displayTimeNs + k * periodNs - decodedNs;
    }
}
