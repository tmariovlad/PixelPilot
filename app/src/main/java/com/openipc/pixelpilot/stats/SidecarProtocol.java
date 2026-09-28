package com.openipc.pixelpilot.stats;

import java.nio.ByteBuffer;

/**
 * Wire format of waybeam's RTP timing sidecar (waybeam include/rtp_sidecar.h; the air runs f8742fe, md5 13b85893).
 * All fields are network byte order. waybeam stays silent until it gets MSG_SUBSCRIBE, then sends one MSG_FRAME per
 * encoded frame to the subscriber; the subscription expires after 5 s without SUBSCRIBE or SYNC_REQ.
 *
 * Clocks on the air (f8742fe): frame_ready_us, last_pkt_send_us and the SYNC_RESP t2/t3 are all wb_monotonic_us() =
 * CLOCK_MONOTONIC (src/timing.c:8, src/star6e_video.c:138, src/rtp_sidecar.c:183-184, 236), and capture_us is the
 * encoder PTS converted to CLOCK_MONOTONIC per frame (src/star6e_video.c:139-161). The header's comments still say
 * CLOCK_MONOTONIC_RAW for two of them; the code does not.
 */
public final class SidecarProtocol {
    public static final int MAGIC = 0x52545053;  // "RTPS"
    public static final int VERSION = 1;
    public static final int MSG_SUBSCRIBE = 1;
    public static final int MSG_FRAME = 2;
    public static final int MSG_SYNC_REQ = 3;
    public static final int MSG_SYNC_RESP = 4;

    static final int FLAG_KEYFRAME = 0x01;
    static final int FLAG_ENC_INFO = 0x02;
    static final int FLAG_TRANSPORT_INFO = 0x04;
    static final int FRAME_LEN = 52;
    static final int ENC_INFO_LEN = 12;
    static final int TRANSPORT_LEN = 16;
    static final int SYNC_RESP_LEN = 32;
    public static final int FRAME_TYPE_IDR = 2;

    private SidecarProtocol() {
    }

    /** One MSG_FRAME. Unsigned 32-bit wire fields are held in longs. */
    public static final class Frame {
        public long ssrc, rtpTs;
        public long frameId, frameReadyUs, captureUs, lastPktSendUs;
        public int seqFirst, seqCount;
        public boolean keyframe;
        public boolean hasEncInfo;
        public long frameSizeBytes;
        public int frameType, qp;
        public boolean idrInserted;
        public boolean hasTransport;
        public int fillPct;
        public long transportDrops;
    }

    public static final class SyncResponse {
        public final long t1Us, t2Us, t3Us;

        SyncResponse(long t1Us, long t2Us, long t3Us) {
            this.t1Us = t1Us;
            this.t2Us = t2Us;
            this.t3Us = t3Us;
        }
    }

    public static byte[] subscribe() {
        return ByteBuffer.allocate(8).putInt(MAGIC).put((byte) VERSION).put((byte) MSG_SUBSCRIBE).array();
    }

    public static byte[] syncRequest(long t1Us) {
        return ByteBuffer.allocate(16).putInt(MAGIC).put((byte) VERSION).put((byte) MSG_SYNC_REQ).putShort((short) 0)
                .putLong(t1Us).array();
    }

    /** The message type of a sidecar datagram, or -1 if it is not one. */
    public static int messageType(byte[] d, int len) {
        if (len < 6 || ByteBuffer.wrap(d).getInt(0) != MAGIC) return -1;
        return d[5] & 0xFF;
    }

    /** A MSG_FRAME, or null. A trailer whose flag is set but whose bytes are missing is ignored. */
    public static Frame parseFrame(byte[] d, int len) {
        if (len < FRAME_LEN || messageType(d, len) != MSG_FRAME) return null;
        ByteBuffer b = ByteBuffer.wrap(d, 0, len);
        b.position(7);
        int flags = b.get() & 0xFF;
        Frame f = new Frame();
        f.ssrc = b.getInt() & 0xFFFFFFFFL;
        f.rtpTs = b.getInt() & 0xFFFFFFFFL;
        f.frameId = b.getLong();
        f.frameReadyUs = b.getLong();
        f.seqFirst = b.getShort() & 0xFFFF;
        f.seqCount = b.getShort() & 0xFFFF;
        f.captureUs = b.getLong();
        f.lastPktSendUs = b.getLong();
        f.keyframe = (flags & FLAG_KEYFRAME) != 0;
        int pos = FRAME_LEN;
        if ((flags & FLAG_ENC_INFO) != 0) {
            if (len < pos + ENC_INFO_LEN) return f;
            b.position(pos);
            f.hasEncInfo = true;
            f.frameSizeBytes = b.getInt() & 0xFFFFFFFFL;
            f.frameType = b.get() & 0xFF;
            f.qp = b.get() & 0xFF;
            b.position(pos + 9);   // complexity, scene_change, gop_state
            f.idrInserted = b.get() != 0;
            pos += ENC_INFO_LEN;
        }
        if ((flags & FLAG_TRANSPORT_INFO) != 0 && len >= pos + TRANSPORT_LEN) {
            b.position(pos);
            f.hasTransport = true;
            f.fillPct = b.get() & 0xFF;
            b.position(pos + 4);
            f.transportDrops = b.getInt() & 0xFFFFFFFFL;
        }
        return f;
    }

    public static SyncResponse parseSyncResponse(byte[] d, int len) {
        if (len < SYNC_RESP_LEN || messageType(d, len) != MSG_SYNC_RESP) return null;
        ByteBuffer b = ByteBuffer.wrap(d, 0, len);
        return new SyncResponse(b.getLong(8), b.getLong(16), b.getLong(24));
    }
}
