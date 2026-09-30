package com.openipc.pixelpilot;

import static org.junit.Assert.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

/**
 * Pins the app's legal channel set to the air's rule, the one source across the two devices: OpenIPC
 * repos/tools/air-common/src/limits.c lim_channel_allowed() (UNII-1 36-48 and UNII-3 149-165, 20 MHz primaries; no
 * DFS). If the air's rule changes, this literal must change with it.
 */
public class LegalChannelsTest {
    /** lim_channel_allowed(), transcribed. */
    private static boolean airAllows(int ch) {
        return (ch >= 36 && ch <= 48 && ch % 4 == 0) || (ch >= 149 && ch <= 165 && (ch - 149) % 4 == 0);
    }

    @Test
    public void theSetIsExactlyTheAirsRule() {
        List<Integer> air = new ArrayList<>();
        for (int ch = -10; ch <= 300; ch++) {
            if (airAllows(ch)) air.add(ch);
            assertEquals("ch " + ch, airAllows(ch), LegalChannels.isLegal(ch));
        }
        assertEquals(List.of(36, 40, 44, 48, 149, 153, 157, 161, 165), air);
        assertEquals(air, LegalChannels.all());
    }
}
