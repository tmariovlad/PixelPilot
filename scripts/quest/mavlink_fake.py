"""Send synthetic MAVLink v1 telemetry to the Quest's MAVLink listener (UDP 14550), to check the app's telemetry
path (listener -> callback -> XR panel line) with known values when the air unit sends no MAVLink.

Messages and field order follow the app's own MAVLink headers (app/mavlink/src/main/cpp/mavlink/common):
HEARTBEAT (armed), SYS_STATUS (battery), GPS_RAW_INT (fix, sats), GLOBAL_POSITION_INT (position, relative alt).
Expected XR line for the defaults: "BAT 15.8V 3.95V/c 4.2A  ALT 12.3m  ARMED  GPS 9  HOME ...".

Usage: python3 mavlink_fake.py [seconds=30] [host=QUEST_HOST] [port=14550] [--arm-after S]
  --arm-after S  disarmed for the first S seconds, then armed: checks that home is taken at arming and that
                 HOME then grows as the position drifts north (~1.1 m per 0.2 s tick).
"""
import struct
import socket
import sys
import time

import quest_env as env

# (msg id, CRC_EXTRA) from the app's MAVLink headers (MAVLINK_MSG_ID_*_CRC)
HEARTBEAT = (0, 50)
SYS_STATUS = (1, 124)
GPS_RAW_INT = (24, 24)
GLOBAL_POSITION_INT = (33, 104)
MAV_MODE_FLAG_SAFETY_ARMED = 128


def x25(data, crc=0xFFFF):
    for b in data:
        tmp = (b ^ (crc & 0xFF)) & 0xFF
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def frame(seq, msg, payload, sysid=1, compid=1):
    """One MAVLink v1 frame: 0xFE len seq sys comp id payload crc16 (CRC over len..payload + CRC_EXTRA)."""
    msgid, extra = msg
    body = bytes([len(payload), seq & 0xFF, sysid, compid, msgid]) + payload
    crc = x25(body + bytes([extra]))
    return b"\xfe" + body + struct.pack("<H", crc)


def heartbeat(armed=True):
    return struct.pack("<IBBBBB", 0, 2, 3, MAV_MODE_FLAG_SAFETY_ARMED if armed else 0, 4, 3)


def sys_status(mv=15800, ca=420):
    return struct.pack("<IIIHHhHHHHHHb", 0, 0, 0, 0, mv, ca, 0, 0, 0, 0, 0, 0, 80)


def gps_raw_int(lat, lon, fix=3, sats=9):
    return struct.pack("<qiiiHHHHBB", 0, lat, lon, 0, 100, 100, 0, 0, fix, sats)


def global_position_int(lat, lon, rel_alt_mm=12_300, hdg_cdeg=9000):
    return struct.pack("<IiiiihhhH", 0, lat, lon, 0, rel_alt_mm, 0, 0, 0, hdg_cdeg)


def main():
    args = sys.argv[1:]
    arm_after = 0.0
    if "--arm-after" in args:
        k = args.index("--arm-after")
        arm_after = float(args[k + 1])
        del args[k:k + 2]
    secs = float(args[0]) if len(args) > 0 else 30
    host = args[1] if len(args) > 1 else env.QUEST_HOST
    port = int(args[2]) if len(args) > 2 else 14550
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lat0, lon0 = 444_268_000, 261_025_000          # 1e-7 deg
    t0 = time.time()
    seq, end, i = 0, t0 + secs, 0
    while time.time() < end:
        armed = time.time() - t0 >= arm_after
        lat, lon = lat0 + i * 100, lon0                  # drift north ~1.1 m per tick (1e-5 deg), so HOME grows
        for msg, payload in ((GPS_RAW_INT, gps_raw_int(lat, lon)), (HEARTBEAT, heartbeat(armed)),
                             (SYS_STATUS, sys_status()), (GLOBAL_POSITION_INT, global_position_int(lat, lon))):
            s.sendto(frame(seq, msg, payload), (host, port))
            seq += 1
        i += 1
        time.sleep(0.2)
    print(f"sent {seq} frames to {host}:{port}")


if __name__ == "__main__":
    main()
