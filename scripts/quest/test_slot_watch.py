"""Offline checks of slot_watch.py: probe parsing, the alert rules (edge-triggered), the alert line format and the
end-of-slot timeline. No air, no Quest. Run: python3 test_slot_watch.py"""
import sys

import quest_env as env
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


def test_one_poll_bounds_the_clock_offset_to_the_whole_second():
    """`date +%s` has 1 s resolution: one poll only says the offset lies in (pc - date - 1, pc - date]."""
    w = sw.AirWatch(sw.Thresholds())
    w.update(sample(now=1790700000), pc_time=1790700003.5)  # PC 3.5 s after the air's whole second began
    assert 2.5 <= w.clock_offset <= 3.5 and 0.4 < w.clock_err < 0.6, (w.clock_offset, w.clock_err)


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
    air = [ev(900, "WB_PID", "WARN", kind="restart"), ah(1200, 2, temp=55)]
    rows = sw.timeline(alerts, app, air, start=990.0, end=1010.0, air_anchor=(1010.0, 20.0), periodic=True)
    assert [r[2] for r in rows] == ["WB_PID", "HEALTH", "WFB_DROP", "SIGNAL_LOST", "AH"], rows
    assert rows[0][0] == 999.0, rows[0]           # anchor PC time - (anchor uptime - the line's uptime)


def test_timeline_keeps_only_events_and_alerts_from_periodic_lines():
    rows = sw.timeline([], ["PPXR_HEALTH t_wall_ms=1000000 code=HEALTH level=INFO"],
                       [ah(100, 1)], start=0, end=2000, air_anchor=(1000.0, 1.0), periodic=False)
    assert rows == [], rows


def test_the_probe_goes_to_the_air_with_lf_only():
    """core.autocrlf=true checks air_probe.sh out with CRLF; busybox sh on the air would read the CR as part of every
    command, so the script is normalised before it is sent."""
    import os
    import tempfile
    cr = bytes([13])
    crlf = os.path.join(tempfile.mkdtemp(), "probe.sh")
    with open(crlf, "wb") as f:
        f.write(b"#!/bin/sh" + cr + b"\n" + b"echo now=1" + cr + b"\n")
    old, sw.AIR_PROBE = sw.AIR_PROBE, crlf
    try:
        script = sw.AirProbe().script
    finally:
        sw.AIR_PROBE = old
    assert cr not in script and script == b"#!/bin/sh\necho now=1\n", script



def test_timeline_reads_the_app_health_lines_in_both_formats():
    """pixelpilot-xr-36's real-format lines (scripts/quest-latch/test_health_log.py FILE, build db2142a) and a line
    from a detached logcat capture both land on the timeline, parsed by health_log.parse (one parser)."""
    sys.path.insert(0, env.LATCH_DIR)
    from test_health_log import FILE, LOGCAT
    rows = sw.timeline([], FILE + [LOGCAT], [], start=1790640000, end=1790640100)
    codes_seen = [r[2] for r in rows]
    assert codes_seen.count("SIGNAL_LOST") == 3 and "IDR_FAILED" in codes_seen and "HEALTH" not in codes_seen, rows
    lost = [r for r in rows if r[2] == "SIGNAL_LOST" and "to=VIDEO_STALLED" in r[4]][0]
    assert lost[0] == 1790640010.0 and lost[3] == "ALERT", lost


def test_the_report_carries_the_app_summary():
    sys.path.insert(0, env.LATCH_DIR)
    from test_health_log import FILE
    md = sw.render_report([], 0, 1, app_summary=sw.app_summary(FILE))
    assert "## App health summary" in md and "| stalls_per_min | 2.0 |" in md, md

def _polls(n, offset=0.749, latency=(0.3, 1.2), interval=5.137, t0=1790640000.0, up0=7000.0):
    """Simulated polls: the air's clock = PC time - offset. The remote probe runs `lat_in` s after the PC starts the
    ssh call and prints `date +%s` (integer) and /proc/uptime (10 ms); the call returns `lat_out` s later. This is
    what made the old estimate a 1.1 -> 2.2 s sawtooth in the live run of 2026-09-29 03:27-03:37."""
    import random
    rnd = random.Random(7)
    for i in range(n):
        pc_before = t0 + i * interval
        lat_in, lat_out = rnd.uniform(0.05, latency[0]), rnd.uniform(0.2, latency[1])
        pc_at_probe = pc_before + lat_in
        air_epoch = pc_at_probe - offset
        s = sample(now=int(air_epoch), uptime=round(up0 + (pc_at_probe - t0), 2))
        yield s, pc_before, pc_at_probe + lat_out


def test_the_clock_offset_converges_instead_of_a_sawtooth():
    w = sw.AirWatch(sw.Thresholds())
    seen = []
    for s, before, after in _polls(40):
        w.update(s, after, pc_before=before)
        seen.append(w.clock_offset)
    assert abs(seen[-1] - 0.749) < 0.1, seen[-5:]
    assert max(seen[-10:]) - min(seen[-10:]) < 0.05, seen[-10:]      # stable, no sawtooth
    assert w.clock_err is not None and w.clock_err < 0.2, w.clock_err


def test_the_clock_estimate_restarts_after_a_reboot():
    w = sw.AirWatch(sw.Thresholds())
    for s, before, after in _polls(20):
        w.update(s, after, pc_before=before)
    s, before, after = next(_polls(1, offset=-3.0, t0=1790640200.0, up0=5.0))
    w.update(dict(s, boot_id="new-boot"), after, pc_before=before)
    assert abs(w.clock_offset - (-3.0)) < 1.5, w.clock_offset          # re-anchored, not stuck on 0.749


def test_expectations_stop_at_expect_until():
    w = sw.AirWatch(sw.Thresholds(), expect={"txpower": "17"}, expect_until=200.0)
    assert codes(w.update(sample(txpower=17.0), pc_time=100.0)) == []
    a = w.update(sample(txpower=12.0), pc_time=300.0)                  # the planned revert after the run
    assert ("ALERT", "AIR_TXPOWER") not in codes(a) and ("WARN", "AIR_TXPOWER") in codes(a), codes(a)


def test_idr_rate_uses_a_window_and_does_not_flap():
    w = sw.AirWatch(sw.Thresholds(idr_per_s_max=2.0, idr_window_s=30.0))
    h, t, flips = 0, 100.0, 0
    for i in range(40):                                                 # 2.2/s and 1.8/s in turns, mean 2.0
        h += 11 if i % 2 else 9
        t += 5.0
        flips += len([a for a in w.update(sample(idr_honoured=h, idr_dropped=0), pc_time=t) if "IDR_RATE" in a.code])
    assert flips <= 1, flips


def test_idr_rate_still_fires_on_a_sustained_storm():
    w = sw.AirWatch(sw.Thresholds(idr_per_s_max=2.0, idr_window_s=30.0))
    h, t, got = 0, 100.0, []
    for _ in range(10):
        h += 20                                                         # 4/s
        t += 5.0
        got += codes(w.update(sample(idr_honoured=h, idr_dropped=0), pc_time=t))
    assert ("WARN", "IDR_RATE") in got, got


def test_expect_until_accepts_an_epoch_or_seconds_after_the_start():
    assert sw.parse_until(None, 100.0) is None
    assert sw.parse_until("+600", 100.0) == 700.0
    assert sw.parse_until("1790641000", 100.0) == 1790641000.0


# ---------------------------------------------------------------- air_health as the air source (openipc-…-40, 444d017)

def ah(up, seq, sa=0, boot="6f1c2a3b", **kv):
    """An AH line with every key of the schema (parse_air_health.AH_KEYS, the one list), NA unless given."""
    pah = sw.air_health_parser()
    vals: dict = {k: "NA" for k in pah.AH_KEYS}
    vals.update(t=1790000000 + up // 100, up=up, boot=boot, seq=seq, sa=sa, temp=45, fps=90, kbps=16243, mcs=7,
                fec_k=4, fec_n=8, ch=157, txpwr=17, idr_h=432, idr_d=26, bcn="0x10", wfb_drop=0, wfb_inj=3400,
                udp_ddrops=0)
    vals.update(kv)
    return "AH " + " ".join(f"{k}={vals[k]}" for k in pah.AH_KEYS)


def ev(up, code, level="INFO", boot="6f1c2a3b", **kv):
    rest = "".join(f" {k}={v}" for k, v in kv.items())
    return f"EV t={1790000000 + up // 100} up={up} boot={boot} code={code} level={level}{rest}"


def head(uptime, boot="6f1c2a3b-0000-4000-8000-000000000000", now=None, **kv):
    return {"now": now if now is not None else 1790000000 + int(uptime), "uptime": uptime, "boot_id": boot,
            "cfg_bitrate": kv.get("cfg_bitrate"), "cfg_fps": kv.get("cfg_fps", 90)}


def feed():
    return sw.HealthFeed(sw.AirWatch(sw.Thresholds()), sw.Thresholds())


def test_an_ah_line_becomes_a_watch_sample():
    pah = sw.air_health_parser()
    s = sw.sample_from_ah(pah.parse_line(ah(123456, 7, bcn="0xA", wfb_drop=2, udp_ddrops=3, wfb_ps="0:1:1:2:0")))
    assert (s["uptime"], s["boot_id"], s["temp"], s["fps"], s["mcs"], s["fec"], s["channel"], s["txpower"]) == \
        (1234.56, "6f1c2a3b", 45, 90, 7, "4/8", 157, 17), s
    assert (s["idr_honoured"], s["idr_dropped"], s["bcn_550"]) == (432, 26, "0xa"), s
    assert s["wfb_drop"] == 5 and s["udp_ddrops"] == 3 and s["wfb_ps"] == "0:1:1:2:0", s   # wfb_tx + socket drops


def test_a_cached_line_does_not_count_the_window_drops_again():
    """sa>0 lines repeat the slow group (00-DESIGN-air-health.md §2): its window sums must not be counted twice."""
    s = sw.sample_from_ah(sw.air_health_parser().parse_line(ah(100, 1, sa=2, wfb_drop=4)))
    assert s["wfb_drop"] is None and s["fps"] == 90, s


def test_the_boot_id_stays_a_string_even_when_it_looks_like_a_number():
    for boot in ("00123456", "1e345678"):
        rec = sw.air_health_record(ah(100, 1, boot=boot))
        assert rec["boot"] == boot, rec["boot"]
    for boot in ("", "NA"):                                                  # no boot: no record key to trust
        assert sw.air_health_record(ah(100, 1, boot=boot))["boot"] is None


def test_the_first_poll_is_a_baseline_and_later_polls_take_only_new_lines():
    f = feed()
    lines = [ev(100, "WB_PID", "WARN", kind="restart", old=1, new=2), ah(100, 1), ah(300, 2)]
    assert f.poll(head(3.5), lines, 1000.0, 1000.2) == []                    # no replay of old events
    lines2 = lines[1:] + [ah(500, 3), ev(700, "WB_PID", "WARN", kind="restart", old=2, new=3), ah(700, 4)]
    a = f.poll(head(7.5), lines2, 1005.0, 1005.2)
    assert codes(a) == [("WARN", "WB_PID")], codes(a)                         # the new event, once
    assert a[0].source == "air_health" and a[0].detail["new"] == 3, a[0]
    assert f.poll(head(8.0), lines2, 1005.5, 1005.7) == []                    # the same tail again: nothing


def test_a_line_is_placed_on_pc_time_by_its_uptime():
    f = feed()
    f.poll(head(3.0), [ah(100, 1)], 1000.0, 1000.2)
    a = f.poll(head(9.0), [ah(100, 1), ah(300, 2, wfb_drop=7)], 1006.0, 1006.2)
    drop = [x for x in a if x.code == "WFB_DROP"][0]
    assert abs(drop.t - (1006.1 - (9.0 - 3.0))) < 1e-6, drop.t               # mid-call - (now_up - line_up)


def test_events_the_rules_already_cover_are_not_repeated():
    f = feed()
    f.poll(head(3.0), [ah(100, 1)], 1000.0, 1000.2)
    a = f.poll(head(5.0), [ah(100, 1), ev(300, "THERMAL", "WARN", temp=71, thr=70), ah(300, 2, temp=71),
                           ev(300, "ROTATE", n=2)], 1002.0, 1002.2)
    assert codes(a) == [("ALERT", "AIR_TEMP")], codes(a)


def test_a_stale_log_is_an_alert_then_clears():
    f = feed()
    f.poll(head(3.0), [ah(100, 1)], 1000.0, 1000.2)
    a = f.poll(head(30.0), [ah(100, 1)], 1027.0, 1027.2)                      # the logger stopped 29 s ago
    assert ("ALERT", "AIR_HEALTH_STALE") in codes(a), codes(a)
    a = f.poll(head(32.0), [ah(100, 1), ah(3100, 2)], 1029.0, 1029.2)
    assert ("INFO", "AIR_HEALTH_STALE_OK") in codes(a), codes(a)


def test_no_log_at_all_is_stale():
    a = feed().poll(head(3.0), [], 1000.0, 1000.2)
    assert codes(a) == [("ALERT", "AIR_HEALTH_STALE")] and a[0].detail["reason"] == "nolog", a


def test_a_reboot_seen_by_the_poll_is_an_alert_once_even_when_the_logger_restarts():
    f = feed()
    f.poll(head(501.0), [ah(49800, 1), ah(50000, 2)], 1000.0, 1000.2)        # up 500 s: longer than the new boot
    a = f.poll(head(4.0, boot="99999999-new"), [], 1060.0, 1060.2)            # rebooted, logger not running
    assert ("ALERT", "AIR_REBOOT") in codes(a) and ("ALERT", "AIR_HEALTH_STALE") in codes(a), codes(a)
    a = f.poll(head(9.0, boot="99999999-new"), [ev(600, "AH_START", boot="99999999"), ah(600, 1, boot="99999999"),
                                                  ah(800, 2, boot="99999999")], 1065.0, 1065.2)
    assert ("ALERT", "AIR_REBOOT") not in codes(a), codes(a)
    assert ("INFO", "AIR_HEALTH_STALE_OK") in codes(a) and ("INFO", "AH_START") in codes(a), codes(a)


def test_lines_written_around_the_poll_raise_no_false_reboot():
    """The poll reads the air's uptime, then the tail: lines written in between are newer than that uptime."""
    f = feed()
    got = []
    for i in range(10):
        up = 1000 + i * 250                                                   # cs
        lines = [ah(up - 400 + 200 * j, i * 3 + j) for j in range(4)]        # the last line is after the head read
        got += codes(f.poll(head(up / 100.0), lines, 2000.0 + i * 5, 2000.2 + i * 5))
    assert ("ALERT", "AIR_REBOOT") not in got, got


def test_a_seq_jump_is_a_gap_warning():
    f = feed()
    f.poll(head(3.0), [ah(100, 1)], 1000.0, 1000.2)
    a = f.poll(head(9.0), [ah(100, 1), ah(700, 5)], 1006.0, 1006.2)
    assert codes(a) == [("WARN", "AIR_HEALTH_GAP")] and a[0].detail["missed"] == 3, a


def test_the_idr_storm_is_seen_from_the_totals_of_consecutive_lines():
    f = feed()
    f.poll(head(3.0), [ah(100, 1, idr_h=0)], 1000.0, 1000.2)
    got, lines, h = [], [ah(100, 1, idr_h=0)], 0
    for i in range(2, 20):
        h += 8                                                                # 4 per 2 s tick
        lines = (lines + [ah(i * 200 - 100, i, idr_h=h)])[-15:]
        got += codes(f.poll(head((i * 200 - 100) / 100.0), lines, 1000.0 + 2 * i, 1000.2 + 2 * i))
    assert ("WARN", "IDR_RATE") in got, got


def test_the_clock_offset_comes_from_the_poll_head():
    f = feed()
    for i in range(30):
        pc = 2000.0 + i * 5.13
        up = 700.0 + i * 5.13 + 0.1
        f.poll(head(round(up, 2), now=int(pc + 0.1 - 0.75)), [ah(int(up * 100), i + 1)], pc, pc + 0.4)
    assert abs(f.watch.clock_offset - 0.75) < 0.25 and f.watch.clock_err < 0.25, (f.watch.clock_offset,
                                                                                  f.watch.clock_err)


def test_the_watch_ends_with_the_clock_offset_for_the_joins():
    """pixelpilot-xr-66, 2026-09-29: every alerts file carries the PC - air offset to use when joining air and Quest
    data by the second (the night's 0.749 s came from an asymmetric rtt/2 and shifted those joins by ~0.7 s)."""
    f = feed()
    for i in range(30):
        pc = 2000.0 + i * 5.13
        up = 700.0 + i * 5.13 + 0.1
        f.poll(head(round(up, 2), now=int(pc + 0.1 - 0.75)), [ah(int(up * 100), i + 1)], pc, pc + 0.4)
    a = sw.clock_alert(f.watch, 3000.0)
    assert (a.level, a.source, a.code) == ("INFO", "watch", "AIR_CLOCK"), a
    assert a.detail["pc_minus_air_s"] == f.watch.clock_offset and a.detail["err_s"] == f.watch.clock_err, a
    assert "pc_minus_air_s=0." in a.line(), a.line()
    empty = sw.clock_alert(sw.AirWatch(sw.Thresholds()), 3000.0)                 # no poll answered: says so
    assert empty.detail == {"pc_minus_air_s": None, "err_s": None} and "pc_minus_air_s=-" in empty.line(), empty


def test_the_tail_output_splits_into_head_and_lines():
    text = ("now=1790000009\nuptime=9.01\nboot_id=6f1c2a3b-0000\ncfg_bitrate=16000\ncfg_fps=90\n"
            + ah(700, 4) + "\n" + ev(700, "ROTATE", n=2) + "\n")
    h, lines = sw.parse_tail(text)
    assert (h["now"], h["uptime"], h["boot_id"], h["cfg_bitrate"], h["cfg_fps"]) == \
        (1790000009, 9.01, "6f1c2a3b-0000", 16000, 90), h
    assert len(lines) == 2 and lines[0].startswith("AH ") and lines[1].startswith("EV "), lines


def test_the_tail_script_goes_to_the_air_with_lf_only():
    cr = bytes([13])
    script = sw.HealthTail().script
    assert cr not in script and b"/tmp/air_health.log" in script, script[:80]


def test_auto_picks_air_health_only_when_its_log_is_live():
    assert sw.pick_air_source("auto", head(9.0), [ah(800, 4)]) == "health"
    assert sw.pick_air_source("auto", head(9.0), []) == "probe"
    assert sw.pick_air_source("auto", head(90.0), [ah(800, 4)]) == "probe"                    # stale
    assert sw.pick_air_source("auto", head(9.0, boot="77777777-x"), [ah(800, 4)]) == "probe"  # an old boot
    assert sw.pick_air_source("auto", None, []) == "probe"
    assert sw.pick_air_source("health", head(9.0), []) == "health"


def test_the_report_reads_air_health_lines_on_pc_time():
    lines = [ev(500, "WB_PID", "WARN", kind="restart", old=1, new=2), ah(700, 4, temp=52)]
    rows = sw.timeline([], [], lines, start=0, end=5000, air_anchor=(1010.0, 9.0), periodic=True)
    assert [(r[1], r[2], r[3]) for r in rows] == [("air_health", "WB_PID", "WARN"), ("air_health", "AH", "INFO")], rows
    assert rows[0][0] == 1010.0 - (9.0 - 5.0) and "kind=restart" in rows[0][4] and "boot=" not in rows[0][4], rows
    assert "temp=52" in rows[1][4], rows
    assert sw.timeline([], [], lines[1:], start=0, end=5000, air_anchor=(1010.0, 9.0)) == []    # AH = periodic


def test_the_report_does_not_list_a_forwarded_event_twice():
    alerts = [sw.Alert(1006.0, "WARN", "air_health", "WB_PID", {"new": 2}),
              sw.Alert(1006.0, "ALERT", "air", "WFB_DROP", {})]
    lines = [ev(500, "WB_PID", "WARN", kind="restart", old=1, new=2)]
    rows = sw.timeline(alerts, [], lines, start=0, end=5000, air_anchor=(1010.0, 9.0))
    assert sorted((r[1], r[2]) for r in rows) == [("air", "WFB_DROP"), ("air_health", "WB_PID")], rows


def test_the_report_carries_the_air_summary():
    recs = [sw.air_health_record(x) for x in (ah(100, 1, temp=44), ah(300, 2, temp=48))]
    md = sw.render_report([], 0, 1, air_summary=sw.air_summary(recs))
    assert "## Air health summary" in md and "lines_ah | 2 |" in md and "| events |" not in md, md


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
