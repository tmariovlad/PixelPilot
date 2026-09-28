package com.openipc.xr.stats;

/** Where the Stats page's numbers come from. The implementation lives in :app (sidecar, native timeline, link). */
public interface StatsSource {
    /** The latest window; cheap and non-blocking, safe from the UI thread. Never null (EMPTY before any data). */
    StatsSnapshot snapshot();
}
