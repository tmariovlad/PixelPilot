package com.openipc.pixelpilot;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * The 5 GHz channels the link may use: UNII-1 36-48 and UNII-3 149-165, 20 MHz primaries, no DFS. The same rule as
 * the air's lim_channel_allowed() (OpenIPC repos/tools/air-common/src/limits.c), pinned by LegalChannelsTest; the
 * app's one copy of it (O123).
 */
final class LegalChannels {
    private static final List<Integer> ALL = Collections.unmodifiableList(
            Arrays.asList(36, 40, 44, 48, 149, 153, 157, 161, 165));   // not List.of: minSdk 26

    private LegalChannels() {
    }

    static boolean isLegal(int ch) {
        return ALL.contains(ch);
    }

    /** In ascending order. */
    static List<Integer> all() {
        return ALL;
    }
}
