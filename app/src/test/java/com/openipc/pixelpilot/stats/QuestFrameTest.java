package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import java.util.List;

import org.junit.Test;

/** VideoPlayer.drainFrameTimes() packs 5 longs per frame: ssrc, RTP timestamp, complete ns, decoded ns, first-packet ns. */
public class QuestFrameTest {
    @Test public void unpacksFiveLongsPerFrame() {
        List<QuestFrame> f = QuestFrame.unpack(new long[]{0xFFFFFFFFL, 90_000, 10, 20, 8, 7, 91_500, 30, 40, 25});
        assertEquals(2, f.size());
        assertEquals(0xFFFFFFFFL, f.get(0).ssrc);
        assertEquals(90_000, f.get(0).rtpTs);
        assertEquals(10, f.get(0).completeNs);
        assertEquals(20, f.get(0).decodedNs);
        assertEquals(8, f.get(0).firstNs);
        assertEquals(91_500, f.get(1).rtpTs);
        assertEquals(25, f.get(1).firstNs);
    }

    @Test public void emptyNullAndATruncatedTail() {
        assertTrue(QuestFrame.unpack(new long[0]).isEmpty());
        assertTrue(QuestFrame.unpack(null).isEmpty());
        assertEquals(1, QuestFrame.unpack(new long[]{1, 2, 3, 4, 5, 6, 7, 8}).size());
    }
}
