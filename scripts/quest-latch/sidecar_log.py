"""Log waybeam's per-frame RTP sidecar (encode timing) from the air unit to a TSV, without the RTP stream.

Usage: python3 sidecar_log.py <air_ip> <seconds> <out.tsv> [port=5602]

waybeam (f8742fe) listens on `outgoing.sidecarPort` and stays silent until it receives MSG_SUBSCRIBE; from then on it
sends one 52-byte MSG_FRAME per encoded frame to the subscriber (include/rtp_sidecar.h). The subscription expires after
5 s, so we re-subscribe every 2 s. Columns: PC receive time, frame id, RTP timestamp, packets, frame_ready - capture
(encode path; capture is CLOCK_MONOTONIC and frame_ready CLOCK_MONOTONIC_RAW, so the value carries the air's constant
MONO-RAW offset: compare codecs within one boot, not absolute), last send - frame_ready (packetise + send), and the
optional encoder trailer (frame size, type, QP).
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
MSG_SUBSCRIBE, MSG_FRAME = 1, 2


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
    }


def subscribe_packet():
    return struct.pack(">IBBxx", MAGIC, 1, MSG_SUBSCRIBE)


def main():
    air, seconds, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 5602
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    end = time.time() + seconds
    next_sub = 0.0
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("pc_recv\tssrc\tframe_id\trtp_ts\tseq_count\tready_minus_capture_us\tsend_minus_ready_us"
                 "\tsize\tftype\tqp\n")
        while time.time() < end:
            if time.time() >= next_sub:
                sock.sendto(subscribe_packet(), (air, port))
                next_sub = time.time() + 2.0
            try:
                buf, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            f = parse_frame(buf)
            if f is None:
                continue
            n += 1
            fh.write(f"{time.time():.6f}\t{f['ssrc']:08x}\t{f['frame_id']}\t{f['rtp_ts']}\t{f['seq_count']}\t"
                     f"{f['ready_minus_capture_us']}\t{f['send_minus_ready_us']}\t{f['size']}\t{f['ftype']}\t{f['qp']}\n")
    print(f"{n} frames -> {out}")


if __name__ == "__main__":
    main()
