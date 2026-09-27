"""Offline checks of w3_budget.py. Run: python3 test_w3_budget.py"""
from w3_budget import PANEL_MS, TX_FLOOR_MS, budget, decide, parse_air, parse_quest

SEGMENT = """# 2_a 2026-09-27
3000 packets / 810 frames in 9.0s = 90.0 fps, 8.10 pkt/frame; sequence gaps (lost before the app) = 3, reordered = 0
frame packet spread (first -> last packet)     n=  810 mean=  5.50 p5=  4.00 p50=  5.40 p95=  7.00 max=  9.00 ms
frame complete -> decoded frame ready          n=  800 mean=  2.10 p5=  1.50 p50=  2.00 p95=  3.00 max=  5.00 ms
frame ready (queueBuffer) -> latch                  n= 700 mean=  4.20 p5=  0.20 p50=  4.10 p95=  8.00 max=  9.00 ms
"""


def test_parse_quest_reads_the_three_means():
    assert parse_quest(SEGMENT) == {"spread": 5.5, "decode": 2.1, "wait": 4.2}


def test_parse_air_averages_rows_of_one_mode():
    rows = [{"mode": "2", "s_air_med": "6.5", "readout_ms": "11", "isp_lo": "1", "isp_hi": "6"},
            {"mode": "2", "s_air_med": "6.7", "readout_ms": "11", "isp_lo": "1", "isp_hi": "6"}]
    a = parse_air(rows)["2"]
    assert abs(a["s_air"] - 6.6) < 1e-9 and a["readout"] == 11


def test_budget_sums_segments_with_the_shared_constants():
    air = {"2": {"s_air": 6.5, "readout": 11.0, "isp_lo": 1.0, "isp_hi": 6.0}}
    r = budget(air, {"2": [parse_quest(SEGMENT)]})["2"]
    fixed = 6.5 + 11.0 + TX_FLOOR_MS + 5.5 + 2.1 + 4.2
    assert abs(r["total_lo"] - (fixed + 1.0 + PANEL_MS[0])) < 1e-9
    assert abs(r["total_hi"] - (fixed + 6.0 + PANEL_MS[1])) < 1e-9


def test_decide_needs_non_overlapping_ranges():
    clear = {"A": {"own_lo": 20, "own_hi": 22}, "B": {"own_lo": 25, "own_hi": 30}}
    assert decide(clear) == "A"
    overlap = {"A": {"own_lo": 20, "own_hi": 26}, "B": {"own_lo": 25, "own_hi": 30}}
    assert decide(overlap) is None  # the ISP ranges overlap: no winner


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
