"""Reads the parts of an H.264 SPS that decide whether a decoder may output frames at once.

Without VUI bitstream_restriction (max_num_reorder_frames = 0), a decoder must assume B-frame reordering and may hold
up to max_dec_frame_buffering frames before output. The Quest 2's Qualcomm decoder held ~16 frames (~96 ms at 166 fps)
on the OpenIPC stream until the app set vendor.qti-ext-dec-picture-order.enable (docs/xr/real-link.md). W4 / AU-10 asks
waybeam to signal max_num_reorder_frames = 0 instead; this tool checks what the air unit's SPS actually says.

Usage:
  python3 sps_vui.py <sps hex>                  e.g. the "csd-0 ..." line the app logs when it configures the decoder
  adb logcat -d | grep "csd-0" | python3 sps_vui.py -
"""
import sys

HIGH_PROFILES = {100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135}


def rbsp(nal: bytes) -> bytes:
    """NAL payload without its start code, header byte and emulation-prevention bytes (00 00 03 -> 00 00)."""
    i = 0
    while i + 3 <= len(nal) and nal[i:i + 3] != b"\x00\x00\x01":
        i += 1
    if i + 3 <= len(nal):
        nal = nal[i + 3:]
    body = nal[1:]  # skip the NAL header (0x67 for an SPS)
    out, zeros = bytearray(), 0
    for b in body:
        if zeros >= 2 and b == 3:
            zeros = 0
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


class Bits:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            byte = self.data[self.pos >> 3]
            v = (v << 1) | ((byte >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return v

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0:
            zeros += 1
        return (1 << zeros) - 1 + (self.u(zeros) if zeros else 0)

    def se(self) -> int:
        k = self.ue()
        return (k + 1) // 2 if k & 1 else -(k // 2)


def _skip_scaling_list(b: Bits, size: int) -> None:
    last, nxt = 8, 8
    for _ in range(size):
        if nxt:
            nxt = (last + b.se() + 256) % 256
        last = nxt or last


def _skip_hrd(b: Bits) -> None:
    cnt = b.ue() + 1
    b.u(4)
    b.u(4)
    for _ in range(cnt):
        b.ue()
        b.ue()
        b.u(1)
    b.u(5)
    b.u(5)
    b.u(5)
    b.u(5)


def parse_sps(nal: bytes) -> dict:
    b = Bits(rbsp(nal))
    s = {"profile_idc": b.u(8)}
    b.u(8)  # constraint flags
    s["level_idc"] = b.u(8)
    b.ue()  # seq_parameter_set_id
    if s["profile_idc"] in HIGH_PROFILES:
        if b.ue() == 3:  # chroma_format_idc
            b.u(1)
        b.ue()
        b.ue()
        b.u(1)
        if b.u(1):  # seq_scaling_matrix_present_flag
            for i in range(8):
                if b.u(1):
                    _skip_scaling_list(b, 16 if i < 6 else 64)
    b.ue()  # log2_max_frame_num_minus4
    poc = b.ue()
    if poc == 0:
        b.ue()
    elif poc == 1:
        b.u(1)
        b.se()
        b.se()
        for _ in range(b.ue()):
            b.se()
    s["max_num_ref_frames"] = b.ue()
    b.u(1)
    s["width"] = (b.ue() + 1) * 16
    map_units = b.ue() + 1
    frame_mbs_only = b.u(1)
    if not frame_mbs_only:
        b.u(1)
    s["height"] = map_units * 16 * (2 - frame_mbs_only)
    b.u(1)  # direct_8x8_inference_flag
    if b.u(1):  # frame_cropping_flag
        b.ue()
        b.ue()
        b.ue()
        b.ue()
    s["vui"] = bool(b.u(1))
    s["bitstream_restriction"] = False
    if s["vui"]:
        if b.u(1) and b.u(8) == 255:  # aspect_ratio_info_present, idc == Extended_SAR
            b.u(16)
            b.u(16)
        if b.u(1):
            b.u(1)
        if b.u(1):
            b.u(3)
            b.u(1)
            if b.u(1):
                b.u(8)
                b.u(8)
                b.u(8)
        if b.u(1):
            b.ue()
            b.ue()
        if b.u(1):  # timing_info_present_flag
            b.u(32)
            b.u(32)
            b.u(1)
        nal_hrd = b.u(1)
        if nal_hrd:
            _skip_hrd(b)
        vcl_hrd = b.u(1)
        if vcl_hrd:
            _skip_hrd(b)
        if nal_hrd or vcl_hrd:
            b.u(1)
        b.u(1)  # pic_struct_present_flag
        if b.u(1):  # bitstream_restriction_flag
            s["bitstream_restriction"] = True
            b.u(1)
            b.ue()
            b.ue()
            b.ue()
            b.ue()
            s["max_num_reorder_frames"] = b.ue()
            s["max_dec_frame_buffering"] = b.ue()
    return s


def verdict(s: dict) -> str:
    if s.get("bitstream_restriction") and s.get("max_num_reorder_frames") == 0:
        return "no reordering signalled: a conforming decoder can output each frame at once"
    return "reordering not ruled out: the decoder may hold frames (up to the DPB size) before output"


def main(argv):
    text = sys.stdin.read() if argv[1:] == ["-"] else " ".join(argv[1:])
    hexes = [w for w in text.replace(",", " ").split() if len(w) > 8 and all(c in "0123456789abcdefABCDEF" for c in w)]
    if not hexes:
        sys.exit("no SPS hex found")
    s = parse_sps(bytes.fromhex(hexes[-1]))
    print(s)
    print(verdict(s))


if __name__ == "__main__":
    main(sys.argv)
