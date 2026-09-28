"""Offline checks of ab_link: step-line fields, air TX rate, per-step counter windows, pre-FEC loss, thermal join.
Run: python3 test_ab_link.py"""
import os
import tempfile

from ab_link import per_state, per_step, read_step_fields, tx_rates

S = 1e9


def write_steps(text):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_step_fields_and_tx_rate():
    path = write_steps("99.0 PRE p12m2b8 tx=900 temp=61\n"
                       "100.0 m2b8 tx=1000 temp=61.5\n"
                       "112.0 m4b16 tx=13000 temp=63\n"
                       "112.5 ERR set_radio failed\n"
                       "124.0 END tx=37000 temp=64\n")
    f = read_step_fields(path)
    os.remove(path)
    assert [x["label"] for x in f] == ["m2b8", "m4b16", "END"]
    assert f[0]["temp"] == 61.5
    assert tx_rates(f) == [1000.0, 2000.0]


def test_read_steps_skips_the_pre_line():
    from ab_segments import read_steps
    path = write_steps("99.0 PRE p12m2b8\n100.0 A tx=1\n112.0 B tx=2\n124.0 END tx=3 reverted=p12m2b8\n")
    steps, end = read_steps(path, 0.0, 0)
    os.remove(path)
    assert [lab for _, lab in steps] == ["A", "B"]
    assert end == 124.0 * S


def test_tx_rate_needs_tx_on_both_ends():
    assert tx_rates([{"t": 0.0, "tx": 5.0}, {"t": 12.0}]) == [None]


def synth_counters(steps_s, end_s, rx_rate, lost_rate, period=0.3):
    """One sample per period with rate*period packets; rates per step index."""
    c = {"ppxr_wfb_p_all": [], "ppxr_wfb_fec_rec": [], "ppxr_wfb_lost": [], "ppxr_wfb_rssi": []}
    t = steps_s[0]
    while t < end_s:
        i = max(k for k, s in enumerate(steps_s) if s <= t)
        c["ppxr_wfb_p_all"].append((t * S, rx_rate[i] * period))
        c["ppxr_wfb_fec_rec"].append((t * S, 3 * period))
        c["ppxr_wfb_lost"].append((t * S, lost_rate[i] * period))
        c["ppxr_wfb_rssi"].append((t * S, 70.0 - 10 * i))
        t += period
    return c


def test_per_step_rates_pre_fec_loss_and_thermal():
    steps = [(100 * S, "A"), (112 * S, "B"), (124 * S, "A")]
    end = 136 * S
    fields = [{"t": 100.0, "tx": 0.0, "temp": 60.0}, {"t": 112.0, "tx": 12000.0, "temp": 62.0},
              {"t": 124.0, "tx": 36000.0, "temp": 61.0}, {"t": 136.0, "tx": 48000.0}]
    counters = synth_counters([100, 112, 124], 136, rx_rate=[1000, 1800, 1000], lost_rate=[0, 5, 0])
    thermal = [(t * S, {"thermal_status": 1.0 if t == 116 else 0.0, "cpu_max_c": 60 + t / 100, "batt_level": 90.0})
               for t in range(100, 136, 4)]
    rows = per_step(counters, thermal, fields, steps, end, 2 * S)
    r = {i: row for i, _, row in rows}
    assert abs(r[0]["rx_per_s"] - 1000) < 40, r[0]["rx_per_s"]
    assert abs(r[1]["rx_per_s"] - 1800) < 60, r[1]["rx_per_s"]
    assert r[1]["tx_per_s"] == 2000.0
    assert abs(r[1]["pre_fec_loss_pct"] - 10.0) < 3.0, r[1]["pre_fec_loss_pct"]
    assert abs(r[0]["pre_fec_loss_pct"]) < 4.0, r[0]["pre_fec_loss_pct"]
    assert r[0]["wfb_lost_per_s"] == 0
    assert abs(r[1]["wfb_lost_per_s"] - 5) < 0.5
    assert r[1]["air_c"] == 62.0
    assert r[1]["quest_status_max"] == 1.0
    assert r[0]["quest_status_max"] == 0.0
    s = dict(per_state(rows))
    assert s["A"]["air_c"] == 61.0
    assert s["B"]["quest_status_max"] == 1.0


def test_drop_stale_zeroes_polls_with_no_rtp_since_the_previous_poll():
    from ab_link import drop_stale
    # polls every 0.3 s; RTP packets arrive until 0.99 s, then the link is dead: the 1.2 s poll still covers
    # arrivals in (0.9, 1.2], the polls from 1.5 s on repeat stale counts
    polls = [0.3 * k * S for k in range(1, 8)]
    counters = {"ppxr_wfb_p_all": [(t, 40) for t in polls], "ppxr_wfb_rssi": [(t, 70) for t in polls]}
    rtp = [x * 0.01 * S for x in range(0, 100)]
    out = drop_stale(counters, rtp)
    assert [v for _, v in out["ppxr_wfb_p_all"]] == [40, 40, 40, 40, 0, 0, 0]
    assert len(out["ppxr_wfb_rssi"]) == 4


def test_per_chain_levels_per_step_snr_in_db_and_stale_dropped():
    from ab_link import drop_stale
    steps = [(0.0, "S1"), (12 * S, "S0")]
    polls = [0.3 * k * S for k in range(0, 80)]  # 0 .. 23.7 s
    chain = lambda a, b: [(t, a if t < 12 * S else b) for t in polls]
    counters = {"ppxr_wfb_p_all": [(t, 40) for t in polls],
                "ppxr_wfb_rssi_a": chain(56, 48), "ppxr_wfb_rssi_b": chain(41, 47),
                "ppxr_wfb_snr_a": chain(40, 22), "ppxr_wfb_snr_b": chain(18, 20)}
    # the link dies at 20 s: later polls repeat the last values and must not count
    rtp = [x * 0.01 * S for x in range(0, 2000)]
    out = drop_stale(counters, rtp)
    assert all(t <= 20.1 * S for t, _ in out["ppxr_wfb_snr_a"])
    rows = per_step(out, [], [{"t": 0.0}, {"t": 12.0}], steps, 24 * S, 2 * S)
    r = {lab: row for _, lab, row in rows}
    assert (r["S1"]["rssi_a"], r["S1"]["rssi_b"]) == (56, 41)
    assert (r["S0"]["rssi_a"], r["S0"]["rssi_b"]) == (48, 47)
    assert (r["S1"]["snr_a_db"], r["S1"]["snr_b_db"]) == (20.0, 9.0)
    assert (r["S0"]["snr_a_db"], r["S0"]["snr_b_db"]) == (11.0, 10.0)


def test_per_chain_levels_absent_in_old_traces():
    rows = per_step({"ppxr_wfb_rssi": [(1 * S, 70)]}, [], [{"t": 0.0}], [(0.0, "A")], 12 * S, 0)
    assert rows[0][2]["rssi_a"] is None and rows[0][2]["snr_b_db"] is None


def test_same_window_data_loss_from_quest_counters_only():
    # 12 s step, guard 2 s -> window [2, 10) s. 100 RTP packets/s with every 20th sequence number missing
    # (5 % lost after FEC), FEC repairs 10/s. p_data = (fec_rec + lost) / (received + lost).
    steps = [(0.0, "A")]
    rtp, seq = [], 0
    for k in range(1200):
        seq += 1
        if seq % 20 == 0:
            continue                      # lost after FEC: a gap in the RTP sequence
        rtp.append((k / 100 * S, seq & 0xFFFF))
    fec = [(t * 0.3 * S, 3) for t in range(40)]          # 3 repairs per 0.3 s poll = 10/s
    rows = per_step({"rtp": rtp, "ppxr_wfb_fec_rec": fec}, [], [{"t": 0.0}], steps, 12 * S, 2 * S)
    r = rows[0][2]
    received = sum(1 for t, _ in rtp if 2 * S <= t < 10 * S)
    lost = 800 // 20                                        # 40 gaps inside the window
    fec_in = sum(v for t, v in fec if 2 * S <= t < 10 * S)
    assert abs(r["data_loss_pct"] - 100.0 * (fec_in + lost) / (received + lost)) < 0.3, r["data_loss_pct"]


def test_same_window_data_loss_absent_without_rtp():
    rows = per_step({"ppxr_wfb_fec_rec": [(1 * S, 3)]}, [], [{"t": 0.0}], [(0.0, "A")], 12 * S, 0)
    assert rows[0][2]["data_loss_pct"] is None


def test_rx_diag_counters_per_step():
    # RxDiag (T6) writes one sample per ~300 ms stats window: counts per window (-> per second) and ring levels
    # (min_armed -> the lowest, cb_max_us -> the highest in the step window).
    steps = [(0.0, "async"), (12 * S, "spsc")]
    polls = [0.3 * k * S for k in range(0, 80)]
    def per(a, b):
        return [(t, a if t < 12 * S else b) for t in polls]
    counters = {"ppxr_rx_crc_err": per(3, 0), "ppxr_usb_completions": per(300, 300), "ppxr_usb_empties": per(6, 0),
                "ppxr_usb_dropped": per(0, 3), "ppxr_usb_min_armed": [(t, 8 - (int(t / S) % 3)) for t in polls],
                "ppxr_usb_cb_max_us": [(t, 1000 + int(t / S) * 100) for t in polls]}
    rows = per_step(counters, [], [{"t": 0.0}, {"t": 12.0}], steps, 24 * S, 2 * S)
    r = {lab: row for _, lab, row in rows}
    assert abs(r["async"]["rx_crc_per_s"] - 10.0) < 0.5, r["async"]["rx_crc_per_s"]
    assert abs(r["async"]["usb_empties_per_s"] - 20.0) < 0.5
    assert r["spsc"]["usb_empties_per_s"] == 0
    assert abs(r["spsc"]["usb_dropped_per_s"] - 10.0) < 0.5
    assert abs(r["async"]["usb_completions_per_s"] - 1000.0) < 20
    assert r["async"]["usb_min_armed"] == 6
    assert r["async"]["usb_cb_max_us"] == 1000 + 9 * 100      # window [2, 10) s
    assert r["spsc"]["usb_cb_max_us"] == 1000 + 21 * 100      # window [14, 22) s


def test_rx_diag_absent_gives_none():
    rows = per_step({}, [], [{"t": 0.0}], [(0.0, "A")], 12 * S, 0)
    assert rows[0][2]["usb_empties_per_s"] is None and rows[0][2]["usb_min_armed"] is None


def test_quest_tx_rate_per_step_and_zero_when_off():
    steps = [(0.0, "on"), (12 * S, "off"), (24 * S, "on")]
    # 50 frames/s while "on" (0-12 s, 24-36 s), nothing while "off"
    tx = [(k / 50 * S, 1) for k in range(0, 600)] + [(24 * S + k / 50 * S, 1) for k in range(0, 600)]
    rows = per_step({"quest_tx": tx}, [], [{"t": 0.0}, {"t": 12.0}, {"t": 24.0}], steps, 36 * S, 2 * S)
    r = {lab + str(i): row["quest_tx_per_s"] for i, lab, row in rows}
    assert abs(r["on0"] - 50) < 1, r
    assert r["off1"] == 0.0, r
    assert abs(r["on2"] - 50) < 1, r
    assert per_step({}, [], [{"t": 0.0}], [(0.0, "A")], 12 * S, 2 * S)[0][2]["quest_tx_per_s"] is None


def test_missing_counters_give_none_not_a_crash():
    steps = [(0.0, "A")]
    rows = per_step({}, [], [{"t": 0.0}], steps, 12 * S, 2 * S)
    assert rows[0][2]["rx_per_s"] is None
    assert rows[0][2]["pre_fec_loss_pct"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
