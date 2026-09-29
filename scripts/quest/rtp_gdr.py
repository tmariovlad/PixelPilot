"""NAL-type histogram and "no-IDR" cut of a recorded RTP stream, for the GDR (intra refresh) decoder tests
(OpenIPC O118 S0: T1 cold start without an IDR, T3 heal time, T4 slices).

The cut drops every packet before the first access unit that carries an SPS but no IDR/IRAP slice, so a replay
starts on SPS/PPS + P frames only, which is what a headset joining a GDR stream mid-way sees.

Usage:
  python3 rtp_gdr.py <in.rtp> <h264|h265>                  print the histogram
  python3 rtp_gdr.py <in.rtp> <h264|h265> --cut <out.rtp>  also write the cut and print its histogram
Files use rtp_record.py's format: [f64 t][u16 len][datagram] per packet.
"""
import struct
import sys
from collections import Counter

SPS = {"h264": 7, "h265": 33}
NAMES = {
    "h264": {1: "slice", 5: "IDR", 6: "SEI", 7: "SPS", 8: "PPS", 9: "AUD"},
    "h265": {0: "TRAIL_N", 1: "TRAIL_R", 19: "IDR_W_RADL", 20: "IDR_N_LP", 21: "CRA", 32: "VPS", 33: "SPS",
             34: "PPS", 35: "AUD", 39: "SEI_PREFIX", 40: "SEI_SUFFIX"},
}


def is_idr(t, codec):
    """A NAL a decoder can start on: H.264 IDR (5); H.265 IRAP (BLA/IDR/CRA, 16-21)."""
    return 16 <= t <= 21 if codec == "h265" else t == 5


def read(path):
    pkts = []
    with open(path, "rb") as f:
        while True:
            h = f.read(10)
            if len(h) < 10:
                return pkts
            t, n = struct.unpack("<dH", h)
            pkts.append((t, f.read(n)))


def write(path, pkts):
    with open(path, "wb") as f:
        for t, d in pkts:
            f.write(struct.pack("<dH", t, len(d)) + d)


def _payload(pkt):
    cc = pkt[0] & 0x0F
    off = 12 + 4 * cc
    if pkt[0] & 0x10:                                  # header extension
        off += 4 + 4 * struct.unpack("!H", pkt[off + 2:off + 4])[0]
    return pkt[off:]


def rtp_ts(pkt):
    return struct.unpack("!I", pkt[4:8])[0]


def _aggregated(body, codec):
    out, i = [], 0
    while i + 2 <= len(body):
        n = struct.unpack("!H", body[i:i + 2])[0]
        nal = body[i + 2:i + 2 + n]
        if nal:
            out.append(nal[0] & 0x1F if codec == "h264" else (nal[0] >> 1) & 0x3F)
        i += 2 + n
    return out


def nal_types(pkt, codec):
    """NAL types that START in this RTP packet (FU continuations start nothing)."""
    p = _payload(pkt)
    if not p:
        return []
    if codec == "h264":
        t = p[0] & 0x1F
        if t == 24:                                    # STAP-A
            return _aggregated(p[1:], codec)
        if t == 28:                                    # FU-A
            return [p[1] & 0x1F] if p[1] & 0x80 else []
        return [t]
    t = (p[0] >> 1) & 0x3F
    if t == 48:                                        # AP
        return _aggregated(p[2:], codec)
    if t == 49:                                        # FU
        return [p[2] & 0x3F] if p[2] & 0x80 else []
    return [t]


def access_units(pkts, codec):
    """[(index of the AU's first packet, NAL types in order)], an AU = consecutive packets with one RTP timestamp."""
    aus, last = [], None
    for i, (_, pkt) in enumerate(pkts):
        ts = rtp_ts(pkt)
        if ts != last:
            aus.append((i, []))
            last = ts
        aus[-1][1].extend(nal_types(pkt, codec))
    return aus


def histogram(pkts, codec):
    aus = access_units(pkts, codec)
    counts = Counter(t for _, types in aus for t in types)
    return {
        "packets": len(pkts),
        "aus": len(aus),
        "counts": counts,
        "idr": sum(n for t, n in counts.items() if is_idr(t, codec)),
        "aus_with_sps": sum(1 for _, types in aus if SPS[codec] in types),
    }


def cut_no_idr(pkts, codec):
    for k, (start, types) in enumerate(access_units(pkts, codec)):
        if k > 0 and SPS[codec] in types and not any(is_idr(t, codec) for t in types):
            t0 = pkts[start][0]
            return [(t - t0, d) for t, d in pkts[start:]]
    raise ValueError("no later access unit carries an SPS without an IDR: the stream never repeats its headers")


def describe(h, codec):
    names = NAMES[codec]
    parts = ", ".join(f"{names.get(t, t)}={n}" for t, n in sorted(h["counts"].items()))
    return (f"packets={h['packets']} aus={h['aus']} idr={h['idr']} aus_with_sps={h['aus_with_sps']} | {parts}")


def main(argv):
    if len(argv) not in (2, 4) or argv[1] not in SPS or (len(argv) == 4 and argv[2] != "--cut"):
        print(__doc__)
        return 2
    pkts = read(argv[0])
    print(argv[0], describe(histogram(pkts, argv[1]), argv[1]))
    if len(argv) == 4:
        cut = cut_no_idr(pkts, argv[1])
        write(argv[3], cut)
        h = histogram(cut, argv[1])
        print(argv[3], describe(h, argv[1]))
        if h["idr"]:
            print("ERROR: the cut still contains an IDR/IRAP", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
