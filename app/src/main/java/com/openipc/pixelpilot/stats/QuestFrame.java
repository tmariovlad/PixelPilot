package com.openipc.pixelpilot.stats;

/**
 * One video frame as the Quest saw it, keyed like the air's sidecar by (ssrc, RTP timestamp). Times are the Quest's
 * CLOCK_MONOTONIC in ns: completeNs = the frame's last RTP packet handed to the parser (after the reorder queue),
 * decodedNs = MediaCodec released it to the surface.
 */
public final class QuestFrame {
    public final long ssrc, rtpTs, completeNs, decodedNs;

    public QuestFrame(long ssrc, long rtpTs, long completeNs, long decodedNs) {
        this.ssrc = ssrc;
        this.rtpTs = rtpTs;
        this.completeNs = completeNs;
        this.decodedNs = decodedNs;
    }
}
