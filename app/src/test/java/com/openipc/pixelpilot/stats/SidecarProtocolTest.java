package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import java.nio.ByteBuffer;

import org.junit.Test;

/** Wire format of waybeam's RTP sidecar (waybeam include/rtp_sidecar.h, f8742fe): all fields network byte order. */
public class SidecarProtocolTest {
    static final int MAGIC = 0x52545053;

    /** A MSG_FRAME as waybeam serialises it (rtp_sidecar.c), optionally with the ENC_INFO and TRANSPORT trailers. */
    static byte[] frame(long ssrc, long rtpTs, long frameId, long readyUs, int seqFirst, int seqCount, long captureUs,
                        long sendUs, boolean key, boolean enc, boolean transport) {
        ByteBuffer b = ByteBuffer.allocate(52 + (enc ? 12 : 0) + (transport ? 16 : 0));
        int flags = (key ? 0x01 : 0) | (enc ? 0x02 : 0) | (transport ? 0x04 : 0);
        b.putInt(MAGIC).put((byte) 1).put((byte) 2).put((byte) 0).put((byte) flags);
        b.putInt((int) ssrc).putInt((int) rtpTs).putLong(frameId).putLong(readyUs);
        b.putShort((short) seqFirst).putShort((short) seqCount).putLong(captureUs).putLong(sendUs);
        if (enc) b.putInt(41000).put((byte) 2).put((byte) 28).put((byte) 100).put((byte) 0).put((byte) 1)
                .put((byte) 1).putShort((short) 0);
        if (transport) b.put((byte) 37).put((byte) 1).putShort((short) 0).putInt(5).putInt(2).putInt(123456);
        return b.array();
    }

    static byte[] syncResp(long t1, long t2, long t3) {
        return ByteBuffer.allocate(32).putInt(MAGIC).put((byte) 1).put((byte) 4).putShort((short) 0)
                .putLong(t1).putLong(t2).putLong(t3).array();
    }

    @Test public void subscribeIsEightBytesWithMagicVersionAndType() {
        ByteBuffer b = ByteBuffer.wrap(SidecarProtocol.subscribe());
        assertEquals(8, b.remaining());
        assertEquals(MAGIC, b.getInt());
        assertEquals(1, b.get());
        assertEquals(SidecarProtocol.MSG_SUBSCRIBE, b.get());
    }

    @Test public void syncRequestCarriesT1() {
        ByteBuffer b = ByteBuffer.wrap(SidecarProtocol.syncRequest(1_234_567_890_123L));
        assertEquals(16, b.remaining());
        assertEquals(MAGIC, b.getInt());
        b.get();
        assertEquals(SidecarProtocol.MSG_SYNC_REQ, b.get());
        b.getShort();
        assertEquals(1_234_567_890_123L, b.getLong());
    }

    @Test public void parsesABaseFrameWithUnsignedFields() {
        byte[] d = frame(0xF1234567L, 0xFFFFFFF0L, 7, 1_000_500, 65535, 22, 1_000_000, 1_001_200, true, false, false);
        SidecarProtocol.Frame f = SidecarProtocol.parseFrame(d, d.length);
        assertNotNull(f);
        assertEquals(0xF1234567L, f.ssrc);
        assertEquals(0xFFFFFFF0L, f.rtpTs);
        assertEquals(7, f.frameId);
        assertEquals(1_000_500, f.frameReadyUs);
        assertEquals(65535, f.seqFirst);
        assertEquals(22, f.seqCount);
        assertEquals(1_000_000, f.captureUs);
        assertEquals(1_001_200, f.lastPktSendUs);
        assertTrue(f.keyframe);
        assertFalse(f.hasEncInfo);
        assertFalse(f.hasTransport);
    }

    @Test public void readsBothTrailers() {
        byte[] d = frame(1, 2, 3, 4, 5, 6, 7, 8, false, true, true);
        SidecarProtocol.Frame f = SidecarProtocol.parseFrame(d, d.length);
        assertTrue(f.hasEncInfo);
        assertEquals(41000, f.frameSizeBytes);
        assertEquals(2, f.frameType);
        assertEquals(28, f.qp);
        assertTrue(f.idrInserted);
        assertTrue(f.hasTransport);
        assertEquals(37, f.fillPct);
        assertEquals(5, f.transportDrops);
    }

    @Test public void transportTrailerWithoutEncInfoFollowsTheBaseFrame() {
        byte[] d = frame(1, 2, 3, 4, 5, 6, 7, 8, false, false, true);
        SidecarProtocol.Frame f = SidecarProtocol.parseFrame(d, d.length);
        assertFalse(f.hasEncInfo);
        assertTrue(f.hasTransport);
        assertEquals(37, f.fillPct);
    }

    @Test public void aFlaggedTrailerThatIsCutShortIsIgnoredNotMisread() {
        byte[] d = frame(1, 2, 3, 4, 5, 6, 7, 8, false, true, false);
        SidecarProtocol.Frame f = SidecarProtocol.parseFrame(d, 52 + 5);
        assertNotNull(f);
        assertFalse(f.hasEncInfo);
    }

    @Test public void rejectsShortWrongMagicAndOtherTypes() {
        byte[] d = frame(1, 2, 3, 4, 5, 6, 7, 8, false, false, false);
        assertNull(SidecarProtocol.parseFrame(d, 51));
        byte[] bad = d.clone();
        bad[0] = 0;
        assertNull(SidecarProtocol.parseFrame(bad, bad.length));
        byte[] resp = syncResp(1, 2, 3);
        assertNull(SidecarProtocol.parseFrame(resp, resp.length));
    }

    @Test public void parsesASyncResponse() {
        byte[] d = syncResp(100, 5_000_150, 5_000_160);
        SidecarProtocol.SyncResponse r = SidecarProtocol.parseSyncResponse(d, d.length);
        assertNotNull(r);
        assertEquals(100, r.t1Us);
        assertEquals(5_000_150, r.t2Us);
        assertEquals(5_000_160, r.t3Us);
        assertNull(SidecarProtocol.parseSyncResponse(d, 31));
    }

    @Test public void messageTypeOfADatagram() {
        byte[] d = syncResp(1, 2, 3);
        assertEquals(SidecarProtocol.MSG_SYNC_RESP, SidecarProtocol.messageType(d, d.length));
        assertEquals(-1, SidecarProtocol.messageType(d, 5));
    }
}
