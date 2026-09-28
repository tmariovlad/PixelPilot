"""Tests for sidecar_log.parse_frame (waybeam RtpSidecarFrame, include/rtp_sidecar.h @ f8742fe)."""
import struct
import unittest

import sidecar_log


def frame_bytes(flags=0, trailer=b""):
    return struct.pack(">IBBBBIIQQHHQQ", 0x52545053, 1, 2, 0, flags, 0xAABBCCDD, 123456, 7,
                       2_000_000, 100, 26, 1_990_000, 2_000_900) + trailer


class ParseFrame(unittest.TestCase):
    def test_fields_and_derived_times(self):
        f = sidecar_log.parse_frame(frame_bytes())
        self.assertEqual(f["ssrc"], 0xAABBCCDD)
        self.assertEqual(f["rtp_ts"], 123456)
        self.assertEqual(f["frame_id"], 7)
        self.assertEqual(f["seq_count"], 26)
        self.assertEqual(f["ready_minus_capture_us"], 10_000)   # includes the air's MONO-RAW offset
        self.assertEqual(f["send_minus_ready_us"], 900)
        self.assertIsNone(f["size"])

    def test_enc_info_trailer(self):
        trailer = struct.pack(">IBBB", 41000, 2, 30, 99) + b"\x00" * 5
        f = sidecar_log.parse_frame(frame_bytes(flags=0x02, trailer=trailer))
        self.assertEqual(f["size"], 41000)
        self.assertEqual(f["ftype"], 2)
        self.assertEqual(f["qp"], 30)

    def test_rejects_other_messages(self):
        self.assertIsNone(sidecar_log.parse_frame(b"\x00" * 52))
        self.assertIsNone(sidecar_log.parse_frame(frame_bytes()[:40]))
        sync = struct.pack(">IBBBB", 0x52545053, 1, 4, 0, 0) + b"\x00" * 60
        self.assertIsNone(sidecar_log.parse_frame(sync))

    def test_missing_capture_time(self):
        raw = bytearray(frame_bytes())
        raw[36:44] = b"\x00" * 8          # capture_us = 0 -> not available
        f = sidecar_log.parse_frame(bytes(raw))
        self.assertIsNone(f["ready_minus_capture_us"])


if __name__ == "__main__":
    unittest.main()
