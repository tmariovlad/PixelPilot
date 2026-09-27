"""Offline checks of sps_vui.py on SPS NAL units built bit by bit. Run: python3 test_sps_vui.py"""
from sps_vui import parse_sps, rbsp, verdict


class Writer:
    def __init__(self):
        self.bits = []

    def u(self, n, v):
        self.bits += [(v >> (n - 1 - i)) & 1 for i in range(n)]

    def ue(self, v):
        v += 1
        n = v.bit_length()
        self.u(n - 1, 0)
        self.u(n, v)

    def nal(self) -> bytes:
        bits = self.bits + [1]  # rbsp_stop_one_bit
        bits += [0] * (-len(bits) % 8)
        raw = bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))
        out, zeros = bytearray(), 0  # insert emulation prevention like an encoder does
        for b in raw:
            if zeros >= 2 and b <= 3:
                out.append(3)
                zeros = 0
            out.append(b)
            zeros = zeros + 1 if b == 0 else 0
        return b"\x00\x00\x00\x01\x67" + bytes(out)


def sps(width=640, height=480, vui=True, restriction=True, reorder=0, dpb=1, timing=True, profile=66):
    w = Writer()
    w.u(8, profile)
    w.u(8, 0)
    w.u(8, 31)
    w.ue(0)
    if profile == 100:
        w.ue(1)
        w.ue(0)
        w.ue(0)
        w.u(1, 0)
        w.u(1, 0)
    w.ue(0)             # log2_max_frame_num_minus4
    w.ue(2)             # pic_order_cnt_type 2 (no POC lsb)
    w.ue(1)             # max_num_ref_frames
    w.u(1, 0)
    w.ue(width // 16 - 1)
    w.ue(height // 16 - 1)
    w.u(1, 1)           # frame_mbs_only
    w.u(1, 1)           # direct_8x8
    w.u(1, 0)           # no cropping
    w.u(1, int(vui))
    if vui:
        w.u(1, 0)  # aspect, overscan, video signal, chroma loc
        w.u(1, 0)
        w.u(1, 0)
        w.u(1, 0)
        w.u(1, int(timing))
        if timing:
            w.u(32, 1)  # 167 fps
            w.u(32, 334)
            w.u(1, 1)
        w.u(1, 0)  # no NAL / VCL HRD
        w.u(1, 0)
        w.u(1, 0)                                     # pic_struct_present
        w.u(1, int(restriction))
        if restriction:
            w.u(1, 1)
            w.ue(0)
            w.ue(0)
            w.ue(16)
            w.ue(16)
            w.ue(reorder)
            w.ue(dpb)
    return w.nal()


def test_restriction_with_zero_reorder_is_recognised():
    s = parse_sps(sps())
    assert (s["width"], s["height"]) == (640, 480)
    assert s["bitstream_restriction"] and s["max_num_reorder_frames"] == 0 and s["max_dec_frame_buffering"] == 1
    assert verdict(s).startswith("no reordering")


def test_missing_vui_or_restriction_means_reordering_not_ruled_out():
    for nal in (sps(vui=False), sps(restriction=False)):
        s = parse_sps(nal)
        assert not s["bitstream_restriction"]
        assert verdict(s).startswith("reordering not ruled out")


def test_nonzero_reorder_is_not_enough():
    assert verdict(parse_sps(sps(reorder=2, dpb=3))).startswith("reordering not ruled out")


def test_high_profile_and_1080p():
    s = parse_sps(sps(width=1920, height=1088, profile=100))
    assert (s["profile_idc"], s["width"], s["height"]) == (100, 1920, 1088)
    assert s["max_num_reorder_frames"] == 0


def test_emulation_prevention_bytes_are_removed():
    assert rbsp(b"\x00\x00\x01\x67\x00\x00\x03\x01\xff") == b"\x00\x00\x01\xff"


# Real SPS from the air unit (waybeam, 480p167), logged by the app as csd-0 on 2026-09-27, and the OpenIPC AU-10
# offline rewrite of it (openipc repo e0e0050): the live one allows reordering, the rewritten one rules it out.
LIVE_480P167 = "0000000167420020e901407b42000007d200092a1808"
REWRITTEN_480P167 = "0000000167420020e901407b42000007d200092a181e1108d4"


def test_real_waybeam_sps_allows_reordering():
    s = parse_sps(bytes.fromhex(LIVE_480P167))
    assert (s["profile_idc"], s["width"], s["height"], s["vui"]) == (66, 640, 480, True)
    assert not s["bitstream_restriction"]


def test_au10_rewrite_of_the_real_sps_rules_it_out():
    s = parse_sps(bytes.fromhex(REWRITTEN_480P167))
    assert s["bitstream_restriction"] and s["max_num_reorder_frames"] == 0 and s["max_dec_frame_buffering"] == 1
    assert (s["width"], s["height"]) == (640, 480)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
