"""Offline checks of mavlink_fake.py: payload sizes match the app's MAVLink headers and the CRC matches a known
frame. Run: python3 test_mavlink_fake.py"""
import mavlink_fake as m


def test_payload_lengths_match_the_headers():
    # MAVLINK_MSG_ID_*_LEN (GPS_RAW_INT: the v1 base length, MIN_LEN 30)
    assert len(m.heartbeat()) == 9
    assert len(m.sys_status()) == 31
    assert len(m.gps_raw_int(0, 0)) == 30
    assert len(m.global_position_int(0, 0)) == 28


def test_x25_known_vector():
    # X.25 / MCRF4XX of "123456789" is 0x6F91
    assert m.x25(b"123456789") == 0x6F91


def test_frame_layout():
    f = m.frame(7, m.HEARTBEAT, m.heartbeat())
    assert f[0] == 0xFE and f[1] == 9 and f[2] == 7 and f[5] == 0
    assert len(f) == 6 + 9 + 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
