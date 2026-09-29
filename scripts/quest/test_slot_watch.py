"""Offline checks of slot_watch.py: probe parsing, the alert rules (edge-triggered), the alert line format and the
end-of-slot timeline. No air, no Quest. Run: python3 test_slot_watch.py"""
import slot_watch as sw

PROBE = """now=1790640646
uptime=7397.11
boot_id=f6af7ca6-4241-4d37-9fa4-6298bd8f29c8
temp=46
tx_packets=19064075
wfb_lines=14845
wfb_drop=0
wfb_inj=3400
wfb_pkt_lines=5
wb_verbose=[verbose] 926s | 90 fps | 16243 kbps | frame 83700 | avg 22984 B/frame | 1 packs
idr_stats={"ok":true,"data":{"min_spacing_us":100000,"channels":[{"idx":0,"honored":432,"dropped":26}]}}
bcn=1790633335 bcn_off 0x550 0x18 -> 0x10
cfg_bitrate=16000
cfg_fps=90
radio=stbc=1 ldpc=1 short_gi=0 bandwidth=20 mcs_index=7 vht_mode=0 vht_nss=1 
fec=k=4 n=8 
iw=Interface wlan0  ifindex 3  wdev 0x1  addr 98:03:cf:cf:a5:2b  type monitor  wiphy 0  channel 157 (5785 MHz), width: 20 MHz, center1: 5785 MHz  txpower 17.00 dBm 
"""


def sample(**over):
    s = sw.parse_air_probe(PROBE)
    s.update(over)
    return s


def test_probe_parses_every_field():
    s = sw.parse_air_probe(PROBE)
    # the fixture is a real capture from air .132 (2026-09-29 03:10, HD 16 Mbit/s m7 FEC 4/8, alink off)
    assert s["now"] == 1790640646 and s["uptime"] == 7397.11 and s["boot_id"].startswith("f6af7ca6"), s
    assert s["temp"] == 46 and s["wfb_drop"] == 0 and s["wfb_lines"] == 14845, s
    assert s["fps"] == 90.0 and s["cfg_fps"] == 90 and s["cfg_bitrate"] == 16000, s
    assert s["idr_honoured"] == 432 and s["idr_dropped"] == 26, s
    assert s["mcs"] == 7 and s["fec"] == "4/8", s
    assert s["channel"] == 157 and s["txpower"] == 17.0, s
    assert s["bcn_550"] == "0x10", s


def test_missing_sources_are_none_not_errors():
    s = sw.parse_air_probe("now=1\nuptime=5.0\nboot_id=b\nwb_verbose=\nidr_stats=\nradio=\niw=\nbcn=\n")
    assert s["fps"] is None and s["mcs"] is None and s["channel"] is None and s["bcn_550"] is None, s
    assert s["idr_honoured"] is None, s


def test_bcn_skip_line_is_not_a_value():
    s = sw.parse_air_probe("now=1\nbcn=1790 bcn_off SKIP not monitor\n")
    assert s["bcn_550"] is None, s


def codes(alerts):
    return [(a.level, a.code) for a in alerts]


def test_a_reboot_is_an_alert():
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(), pc_time=100.0)
    a = w.update(sample(boot_id="bbbb-2222", uptime=12.0), pc_time=105.0)
    assert ("ALERT", "AIR_REBOOT") in codes(a), codes(a)


def test_uptime_going_back_is_a_reboot_even_with_the_same_boot_id():
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(), pc_time=100.0)
    a = w.update(sample(uptime=3.0), pc_time=105.0)
    assert ("ALERT", "AIR_REBOOT") in codes(a), codes(a)


def test_drops_alert_once_then_clear():
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(), pc_time=100.0)
    a1 = w.update(sample(wfb_drop=76), pc_time=105.0)
    a2 = w.update(sample(wfb_drop=12), pc_time=110.0)
    a3 = w.update(sample(wfb_drop=0), pc_time=115.0)
    assert ("ALERT", "WFB_DROP") in codes(a1), codes(a1)
    assert "WFB_DROP" not in [c for _, c in codes(a2)], codes(a2)      # still on: no repeat every 5 s
    assert ("INFO", "WFB_DROP_OK") in codes(a3), codes(a3)


def test_idr_rate_uses_the_counter_delta():
    w = sw.AirWatch(sw.Thresholds(idr_per_s_max=2.0))
    w.update(sample(idr_honoured=16, idr_dropped=6), pc_time=100.0)
    calm = w.update(sample(idr_honoured=20, idr_dropped=6), pc_time=105.0)      # 0.8/s
    storm = w.update(sample(idr_honoured=40, idr_dropped=10), pc_time=110.0)    # 24 in 5 s = 4.8/s
    assert "IDR_RATE" not in [c for _, c in codes(calm)], codes(calm)
    assert ("WARN", "IDR_RATE") in codes(storm), codes(storm)


def test_fps_low_is_relative_to_the_configured_fps():
    w = sw.AirWatch(sw.Thresholds())
    assert ("ALERT", "AIR_FPS_LOW") in codes(w.update(sample(fps=84.0), pc_time=100.0))
    w2 = sw.AirWatch(sw.Thresholds())
    assert "AIR_FPS_LOW" not in [c for _, c in codes(w2.update(sample(fps=165.0, cfg_fps=167), pc_time=100.0))]
    w3 = sw.AirWatch(sw.Thresholds())
    assert ("ALERT", "AIR_FPS_LOW") in codes(w3.update(sample(fps=150.0, cfg_fps=167), pc_time=100.0))


def test_unknown_fps_raises_nothing():
    w = sw.AirWatch(sw.Thresholds())
    assert "AIR_FPS_LOW" not in [c for _, c in codes(w.update(sample(fps=None), pc_time=100.0))]


def test_temperature_warn_then_alert():
    w = sw.AirWatch(sw.Thresholds(temp_warn=60, temp_alert=70))
    assert ("WARN", "AIR_TEMP") in codes(w.update(sample(temp=63), pc_time=100.0))
    assert ("ALERT", "AIR_TEMP") in codes(w.update(sample(temp=71), pc_time=105.0))


def test_expected_values_are_checked():
    w = sw.AirWatch(sw.Thresholds(), expect={"channel": "157", "txpower": "12"})
    a = w.update(sample(), pc_time=100.0)    # txpower 17 != 12
    assert ("ALERT", "AIR_TXPOWER") in codes(a), codes(a)
    assert "AIR_CHANNEL" not in [c for _, c in codes(a)], codes(a)


def test_an_unplanned_radio_change_is_a_warning():
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(), pc_time=100.0)
    a = w.update(sample(mcs=2, channel=161), pc_time=105.0)
    assert ("WARN", "AIR_MCS") in codes(a) and ("WARN", "AIR_CHANNEL") in codes(a), codes(a)


def test_bcn_register_not_0x10_is_an_alert():
    w = sw.AirWatch(sw.Thresholds())
    assert ("ALERT", "AIR_BCN_550") in codes(w.update(sample(bcn_550="0x18"), pc_time=100.0))


def test_unreachable_needs_two_misses_and_recovers():
    w = sw.AirWatch(sw.Thresholds(unreachable_after=2))
    w.update(sample(), pc_time=100.0)
    assert codes(w.update(None, pc_time=105.0)) == []
    assert ("ALERT", "AIR_UNREACHABLE") in codes(w.update(None, pc_time=110.0))
    assert ("INFO", "AIR_UNREACHABLE_OK") in codes(w.update(sample(), pc_time=115.0))


def test_air_clock_offset_is_recorded():
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(now=1790700000), pc_time=1790700003.5)  # PC ahead of the air by 3.5 s
    assert w.clock_offset == 3.5, w.clock_offset


QUEST_OK = {"wakefulness": "Awake", "pid": "4242", "guardian_pause": "1", "prox": "CLOSE", "headset": "HEADSET_MOUNTED",
            "usb": ["0bda:8812"], "data_free_mb": 20000, "battery": 80}


def test_quest_between_all_good():
    assert sw.quest_alerts(QUEST_OK, sw.Thresholds(), {"guardian_pause": "1", "prox": "CLOSE"}) == []


def test_quest_between_problems():
    q = dict(QUEST_OK, wakefulness="Asleep", pid="", usb=[], guardian_pause="0", prox="FAR", data_free_mb=500,
             battery=20)
    got = codes(sw.quest_alerts(q, sw.Thresholds(), {"guardian_pause": "1", "prox": "CLOSE"}))
    for want in [("ALERT", "QUEST_ASLEEP"), ("ALERT", "QUEST_XR_NOT_RUNNING"), ("ALERT", "QUEST_NO_ADAPTER"),
                 ("WARN", "QUEST_GUARDIAN"), ("WARN", "QUEST_PROX"), ("WARN", "QUEST_STORAGE"),
                 ("WARN", "QUEST_BATTERY")]:
        assert want in got, (want, got)


def test_quest_parsers():
    assert sw.parse_wakefulness("  mWakefulness=Asleep\n  mWakefulnessChanging=false\n") == "Asleep"
    # real outputs, Quest 2, 2026-09-29 03:10 (in-slot state: guardian paused, prox_close)
    assert sw.parse_df_free_mb("Filesystem       1K-blocks     Used Available Use% Mounted on\n"
                               "/dev/block/dm-49 242680204 81352368 161196764  34% /data/user/0\n") == 157418
    assert sw.parse_battery("Current Battery Service state:\n  AC powered: true\n  level: 77\n  scale: 100\n") == 77
    vr = "Virtual proximity state: CLOSE\nisAutosleepDisabled: false\nState: HEADSET_MOUNTED\nDevice idle state: Not idle\n"
    assert sw.parse_vrpower(vr) == ("CLOSE", "HEADSET_MOUNTED")
    usb = ("  host_manager={\n    devices={\n      name=/dev/bus/usb/001/002\n      vendor_id=3034\n"
           "      product_id=34834\n      class=0\n      manufacturer_name=Realtek\n")
    assert sw.parse_usb_ids(usb) == ["0bda:8812"]


def test_quest_script_output_splits_into_fields():
    text = ("  mWakefulness=Awake\n@@\n23379\n@@\n1\n@@\nVirtual proximity state: CLOSE\nState: HEADSET_MOUNTED\n@@\n"
            "      vendor_id=3034\n      product_id=34834\n@@\nFilesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/dm-49 242680204 81352368 161196764  34% /data/user/0\n@@\n  level: 77\n")
    q = sw.parse_quest(text)
    assert q == {"wakefulness": "Awake", "pid": "23379", "guardian_pause": "1", "prox": "CLOSE",
                 "headset": "HEADSET_MOUNTED", "usb": ["0bda:8812"], "data_free_mb": 157418, "battery": 77}, q


def test_alert_line_round_trips():
    a = sw.Alert(t=1790700005.25, level="ALERT", source="air", code="WFB_DROP", detail={"drop": "76", "note": "a b"})
    line = a.line()
    assert line.split()[1:4] == ["ALERT", "air", "WFB_DROP"], line
    back = sw.Alert.parse(line)
    assert back.code == "WFB_DROP" and back.detail == {"drop": "76", "note": "a_b"} and abs(back.t - a.t) < 0.01, back


def test_timeline_merges_sources_in_the_slot_window():
    alerts = [sw.Alert(t=1000.0, level="ALERT", source="air", code="WFB_DROP", detail={})]
    app = ["PPXR_EVENT t_mono_ms=5 t_wall_ms=1001500 code=SIGNAL_LOST level=ALERT to=VIDEO_STALLED",
           "PPXR_HEALTH t_mono_ms=6 t_wall_ms=999000 code=HEALTH level=INFO fps=90",
           "PPXR_EVENT t_mono_ms=7 t_wall_ms=5000000 code=SIGNAL_OK level=INFO"]           # outside the window
    air = ["EV t=998 up_cs=100 code=WAYBEAM_RESTART", "t=1002 up_cs=500 temp=55"]
    rows = sw.timeline(alerts, app, air, start=990.0, end=1010.0, air_offset=1.0, periodic=True)
    assert [r[2] for r in rows] == ["WAYBEAM_RESTART", "HEALTH", "WFB_DROP", "SIGNAL_LOST", "AIR_HEALTH"], rows
    assert rows[0][0] == 999.0, rows[0]           # air epoch + offset -> PC time


def test_timeline_keeps_only_events_and_alerts_from_periodic_lines():
    rows = sw.timeline([], ["PPXR_HEALTH t_wall_ms=1000000 code=HEALTH level=INFO"],
                       ["t=1000 up_cs=1 temp=50"], start=0, end=2000, air_offset=0.0, periodic=False)
    assert rows == [], rows


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
