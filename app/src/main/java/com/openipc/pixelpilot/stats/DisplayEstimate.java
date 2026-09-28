package com.openipc.pixelpilot.stats;

/**
 * Estimated time from a decoded frame to its display, from the XR runtime's predicted-display grid. An estimate: the
 * compositor latch itself is not observable in the app (docs/xr/display-latency.md).
 */
public interface DisplayEstimate {
    /** ns from {@code decodedNs} (CLOCK_MONOTONIC) to the next predicted display, or a negative value if unknown. */
    long nsToDisplay(long decodedNs);
}
