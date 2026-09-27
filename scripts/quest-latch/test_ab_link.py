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
    path = write_steps("100.0 m2b8 tx=1000 temp=61.5\n"
                       "112.0 m4b16 tx=13000 temp=63\n"
                       "112.5 ERR set_radio failed\n"
                       "124.0 END tx=37000 temp=64\n")
    f = read_step_fields(path)
    os.remove(path)
    assert [x["label"] for x in f] == ["m2b8", "m4b16", "END"]
    assert f[0]["temp"] == 61.5
    assert tx_rates(f) == [1000.0, 2000.0]


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
