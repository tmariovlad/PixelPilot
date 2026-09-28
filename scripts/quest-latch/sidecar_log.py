"""Log waybeam's per-frame RTP sidecar (encode timing) from the air unit to a TSV, without the RTP stream.

Usage: python3 sidecar_log.py <air_ip> <seconds> <out.tsv> [port=5602]

waybeam (f8742fe) listens on `outgoing.sidecarPort` and stays silent until it receives MSG_SUBSCRIBE; from then on it
sends one 52-byte MSG_FRAME per encoded frame to the subscriber (include/rtp_sidecar.h). The subscription expires after
5 s, so we re-subscribe every 2 s. Columns: PC receive time, frame id, RTP timestamp, packets, frame_ready - capture
(encode path), last send - frame_ready (packetise + send), the optional encoder trailer (frame size, type, QP), then
the absolute air times capture/ready/send (us, air CLOCK_MONOTONIC) and the best recent SYNC (air minus PC epoch, us,
and its round trip; a SYNC_REQ at the start and every 10 s), so a PC capture can be joined with a Quest trace:
pc_time = air_time - air_minus_pc_us, and ab_detached's quest_minus_pc_ms takes it on to the Quest's clock.
Clocks: the header comments say frame_ready/last_pkt_send are CLOCK_MONOTONIC_RAW, but on the air's build (13b85893 =
f8742fe) every sidecar timestamp is CLOCK_MONOTONIC (timing.c:8, star6e_video.c:138-161, rtp_sidecar.c:183-184/236;
pixelpilot-xr-36, 2026-09-29), so frame_ready - capture is the encode path without a clock offset [PROVEN in code, not
yet checked live].
"""
import socket
import struct
import sys
import time

MAGIC = 0x52545053
FRAME_FMT = ">IBBBBIIQQHHQQ"            # RtpSidecarFrame, 52 bytes, network order
FRAME_LEN = struct.calcsize(FRAME_FMT)
ENC_FMT = ">IBBB"                        # RtpSidecarEncInfo head: size, frame_type, qp, complexity
FLAG_ENC_INFO = 0x02
MSG_SUBSCRIBE, MSG_FRAME, MSG_SYNC_REQ, MSG_SYNC_RESP = 1, 2, 3, 4
SYNC_EVERY_S = 10.0
TAB = "\t"
HEADER_OLD = TAB.join(["pc_recv", "ssrc", "frame_id", "rtp_ts", "seq_count", "ready_minus_capture_us",
                       "send_minus_ready_us", "size", "ftype", "qp"])
# Appended, so readers of the old columns keep working.
HEADER = TAB.join([HEADER_OLD, "capture_us", "ready_us", "send_us", "air_minus_pc_us", "sync_rtt_us"])


def parse_frame(buf):
    """Return a dict for a MSG_FRAME datagram, or None for anything else."""
    if len(buf) < FRAME_LEN:
        return None
    (magic, _version, msg_type, _stream, flags, ssrc, rtp_ts, frame_id, ready_us, seq_first, seq_count,
     capture_us, send_us) = struct.unpack_from(FRAME_FMT, buf)
    if magic != MAGIC or msg_type != MSG_FRAME:
        return None
    size = ftype = qp = None
    if flags & FLAG_ENC_INFO and len(buf) >= FRAME_LEN + struct.calcsize(ENC_FMT):
        size, ftype, qp, _cx = struct.unpack_from(ENC_FMT, buf, FRAME_LEN)
    return {
        "ssrc": ssrc, "rtp_ts": rtp_ts, "frame_id": frame_id, "seq_first": seq_first, "seq_count": seq_count,
        "flags": flags,
        "ready_minus_capture_us": (ready_us - capture_us) if capture_us else None,
        "send_minus_ready_us": send_us - ready_us,
        "size": size, "ftype": ftype, "qp": qp,
        "capture_us": capture_us, "ready_us": ready_us, "send_us": send_us,
    }


def subscribe_packet():
    return struct.pack(">IBBxx", MAGIC, 1, MSG_SUBSCRIBE)


def sync_request(t1_us):
    """MSG_SYNC_REQ (16 B): the air echoes t1 and adds its receive (t2) and send (t3) times."""
    return struct.pack(">IBBxxQ", MAGIC, 1, MSG_SYNC_REQ, t1_us)


def parse_sync_resp(buf):
    """(t1, t2, t3) of a MSG_SYNC_RESP (32 B), or None."""
    if len(buf) < 32:
        return None
    magic, _v, msg_type, t1, t2, t3 = struct.unpack_from(">IBBxxQQQ", buf)
    return (t1, t2, t3) if magic == MAGIC and msg_type == MSG_SYNC_RESP else None


def sync_offset(t1, t2, t3, t4):
    """NTP-style: (air - pc offset, round trip) in us; the offset's error is at most half the round trip."""
    return ((t2 - t1) + (t3 - t4)) // 2, (t4 - t1) - (t3 - t2)


class SyncBook:
    """The last `keep` SYNC samples; best() = the lowest-RTT one as (offset_us, rtt_us), or None."""

    def __init__(self, keep=6):
        self.keep = keep
        self.samples = []

    def add(self, offset_us, rtt_us):
        if rtt_us < 0:
            return
        self.samples = (self.samples + [(offset_us, rtt_us)])[-self.keep:]

    def best(self):
        return min(self.samples, key=lambda s: s[1]) if self.samples else None


def format_row(pc_recv, f, sync):
    """One TSV row: the old columns, then capture/ready/send (air us) and the best SYNC (empty before the first)."""
    off, rtt = sync if sync else ("", "")
    return TAB.join([f"{pc_recv:.6f}", f"{f['ssrc']:08x}", str(f["frame_id"]), str(f["rtp_ts"]), str(f["seq_count"]),
                     str(f["ready_minus_capture_us"]), str(f["send_minus_ready_us"]), str(f["size"]), str(f["ftype"]),
                     str(f["qp"]), str(f["capture_us"]), str(f["ready_us"]), str(f["send_us"]), str(off), str(rtt)])


def main():
    air, seconds, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 5602
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    end = time.time() + seconds
    next_sub = next_sync = 0.0
    book = SyncBook()
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEADER + "\n")
        while time.time() < end:
            if time.time() >= next_sub:
                sock.sendto(subscribe_packet(), (air, port))
                next_sub = time.time() + 2.0
            if time.time() >= next_sync:   # at the start, then every SYNC_EVERY_S (PC epoch us, like pc_recv)
                sock.sendto(sync_request(int(time.time() * 1e6)), (air, port))
                next_sync = time.time() + SYNC_EVERY_S
            try:
                buf, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            t4 = int(time.time() * 1e6)
            resp = parse_sync_resp(buf)
            if resp:
                book.add(*sync_offset(*resp, t4))
                continue
            f = parse_frame(buf)
            if f is None:
                continue
            n += 1
            fh.write(format_row(t4 / 1e6, f, book.best()) + "\n")
    print(f"{n} frames -> {out}")


if __name__ == "__main__":
    main()
