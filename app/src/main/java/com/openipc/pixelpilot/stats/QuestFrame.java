package com.openipc.pixelpilot.stats;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * One video frame as the Quest saw it, keyed like the air's sidecar by (ssrc, RTP timestamp). Times are the Quest's
 * CLOCK_MONOTONIC in ns: completeNs = the frame's last RTP packet handed to the parser (after the reorder queue),
 * decodedNs = MediaCodec released it to the surface.
 */
public final class QuestFrame {
    public final long ssrc;
    public final long rtpTs;
    public final long completeNs;
    public final long decodedNs;
    /** When the frame's first RTP packet reached the parser (CLOCK_MONOTONIC ns); 0 = unknown. */
    public final long firstNs;

    public QuestFrame(long ssrc, long rtpTs, long completeNs, long decodedNs) {
        this(ssrc, rtpTs, completeNs, decodedNs, 0);
    }

    public QuestFrame(long ssrc, long rtpTs, long completeNs, long decodedNs, long firstNs) {
        this.ssrc = ssrc;
        this.rtpTs = rtpTs;
        this.completeNs = completeNs;
        this.decodedNs = decodedNs;
        this.firstNs = firstNs;
    }

    /** Frames from VideoPlayer.drainFrameTimes(): 5 longs each (ssrc, RTP timestamp, complete ns, decoded ns, first ns). */
    public static List<QuestFrame> unpack(long[] packed) {
        if (packed == null || packed.length < 5) return Collections.emptyList();
        List<QuestFrame> out = new ArrayList<>(packed.length / 5);
        for (int i = 0; i + 4 < packed.length; i += 5) {
            out.add(new QuestFrame(packed[i], packed[i + 1], packed[i + 2], packed[i + 3], packed[i + 4]));
        }
        return out;
    }
}
