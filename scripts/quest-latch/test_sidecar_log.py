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
        self.assertEqual(f["ready_minus_capture_us"], 10_000)   # encode path (all CLOCK_MONOTONIC on 13b85893)
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


class AbsoluteTimesAndSync(unittest.TestCase):
    def test_absolute_air_times_are_kept(self):
        f = sidecar_log.parse_frame(frame_bytes())
        self.assertEqual(f["capture_us"], 1_990_000)
        self.assertEqual(f["ready_us"], 2_000_000)
        self.assertEqual(f["send_us"], 2_000_900)

    def test_sync_request_and_response(self):
        req = sidecar_log.sync_request(123_456_789)
        self.assertEqual(struct.unpack(">IBBxxQ", req), (0x52545053, 1, 3, 123_456_789))
        resp = struct.pack(">IBBxxQQQ", 0x52545053, 1, 4, 10, 20, 30)
        self.assertEqual(sidecar_log.parse_sync_resp(resp), (10, 20, 30))
        self.assertIsNone(sidecar_log.parse_sync_resp(resp[:31]))
        self.assertIsNone(sidecar_log.parse_sync_resp(frame_bytes()))

    def test_offset_is_air_minus_pc_ntp_style(self):
        # air clock = pc clock + 5 s; 1 ms each way; 10 us turnaround on the air
        off, rtt = sidecar_log.sync_offset(1_000_000, 6_001_000, 6_001_010, 1_002_010)
        self.assertEqual(off, 5_000_000)
        self.assertEqual(rtt, 2_000)

    def test_best_sync_is_the_lowest_rtt_recent_sample(self):
        s = sidecar_log.SyncBook(keep=2)
        self.assertIsNone(s.best())
        s.add(5_000_000, 3_000)
        s.add(5_000_400, 800)
        self.assertEqual(s.best(), (5_000_400, 800))
        s.add(5_001_000, 2_000)          # the 3 ms sample ages out; 0.8 ms still wins
        self.assertEqual(s.best(), (5_000_400, 800))
        s.add(5_002_000, 1_500)          # now the 0.8 ms one is gone too
        self.assertEqual(s.best(), (5_002_000, 1_500))

    def test_row_keeps_the_old_columns_first_and_appends_the_new(self):
        f = sidecar_log.parse_frame(frame_bytes())
        old = sidecar_log.HEADER_OLD.split("	")
        head = sidecar_log.HEADER.split("	")
        self.assertEqual(head[:len(old)], old)
        self.assertEqual(head[len(old):], ["capture_us", "ready_us", "send_us", "air_minus_pc_us", "sync_rtt_us"])
        row = sidecar_log.format_row(1790634692.5, f, (5_000_000, 900)).split("	")
        self.assertEqual(len(row), len(head))
        self.assertEqual(row[1], "aabbccdd")
        self.assertEqual(row[len(old):], ["1990000", "2000000", "2000900", "5000000", "900"])
        no_sync = sidecar_log.format_row(1.0, f, None).split("	")
        self.assertEqual(no_sync[-2:], ["", ""])


if __name__ == "__main__":
    unittest.main()
