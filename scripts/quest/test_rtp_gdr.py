"""Checks of rtp_gdr: the NAL-type histogram and the "no-IDR" cut of a recorded GDR stream (OpenIPC O118 S0, T1).
Synthetic RTP packets only. Run: python3 test_rtp_gdr.py"""

import struct

from rtp_gdr import access_units, cut_no_idr, histogram, nal_types


def rtp(payload, ts, seq, pt=96, marker=False):
    return struct.pack("!BBHII", 0x80, (0x80 if marker else 0) | pt, seq, ts, 1234) + payload


def h264(t):                  # one-byte H.264 NAL header, nal_ref_idc 3
    return bytes([0x60 | t]) + b"\x11\x22"


def h265(t):                  # two-byte H.265 NAL header, layer 0, tid 1
    return bytes([t << 1, 1]) + b"\x11\x22"


def test_h264_single_stap_a_and_fu_a_start_only():
    stap = bytes([0x78]) + struct.pack("!H", 3) + h264(7) + struct.pack("!H", 3) + h264(8)
    fu_start = bytes([0x7C, 0x80 | 5]) + b"\x00"   # FU-A, S bit, type 5
    fu_mid = bytes([0x7C, 0x00 | 5]) + b"\x00"     # continuation: not a new NAL
    assert nal_types(rtp(h264(6), 0, 0), "h264") == [6]
    assert nal_types(rtp(stap, 0, 1), "h264") == [7, 8]
    assert nal_types(rtp(fu_start, 0, 2), "h264") == [5]
    assert nal_types(rtp(fu_mid, 0, 3), "h264") == []


def test_h265_ap_and_fu():
    ap = bytes([48 << 1, 1]) + struct.pack("!H", 4) + h265(32) + struct.pack("!H", 4) + h265(33)
    fu_start = bytes([49 << 1, 1, 0x80 | 19]) + b"\x00"
    fu_end = bytes([49 << 1, 1, 0x40 | 19]) + b"\x00"
    assert nal_types(rtp(ap, 0, 0, pt=97), "h265") == [32, 33]
    assert nal_types(rtp(fu_start, 0, 1, pt=97), "h265") == [19]
    assert nal_types(rtp(fu_end, 0, 2, pt=97), "h265") == []


def gdr_h264():
    """IDR AU, then P AUs; SPS/PPS repeated at AU 3 (the start of the second refresh cycle)."""
    pkts, seq = [], 0
    layout = [[7, 8, 5], [1], [1], [7, 8, 6, 1], [1], [1]]
    for au, types in enumerate(layout):
        for i, t in enumerate(types):
            pkts.append((au * 0.01, rtp(h264(t), 3000 * au, seq, marker=i == len(types) - 1)))
            seq += 1
    return pkts


def test_access_units_group_by_rtp_timestamp():
    aus = access_units(gdr_h264(), "h264")
    assert [types for _, types in aus] == [[7, 8, 5], [1], [1], [7, 8, 6, 1], [1], [1]]


def test_histogram_counts_nals_and_idr():
    h = histogram(gdr_h264(), "h264")
    assert h["counts"][7] == 2 and h["counts"][5] == 1 and h["counts"][1] == 5
    assert h["idr"] == 1 and h["aus"] == 6 and h["aus_with_sps"] == 2


def test_cut_starts_at_the_first_sps_au_without_idr_and_rebases_time():
    cut = cut_no_idr(gdr_h264(), "h264")
    h = histogram(cut, "h264")
    assert h["idr"] == 0 and h["aus"] == 3 and h["counts"][7] == 1
    assert cut[0][0] == 0.0                       # time rebased to the first kept packet
    assert nal_types(cut[0][1], "h264") == [7]


def test_cut_refuses_a_stream_without_a_later_sps():
    pkts = [p for p in gdr_h264() if 7 not in nal_types(p[1], "h264") or p[0] == 0.0]
    try:
        cut_no_idr(pkts, "h264")
    except ValueError:
        return
    raise AssertionError("cut a stream that never repeats SPS")


def test_h265_irap_types_count_as_idr():
    pkts = [(0.0, rtp(h265(32), 0, 0, pt=97)), (0.0, rtp(h265(33), 0, 1, pt=97)),
            (0.0, rtp(h265(34), 0, 2, pt=97)), (0.0, rtp(h265(21), 0, 3, pt=97, marker=True)),
            (0.01, rtp(h265(1), 3000, 4, pt=97, marker=True))]
    assert histogram(pkts, "h265")["idr"] == 1    # CRA (21) is IRAP: a decoder can start there


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
