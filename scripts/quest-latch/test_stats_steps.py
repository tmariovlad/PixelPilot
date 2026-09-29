"""Offline checks of stats_steps: the median of PPXR_STATS fields per air step. Run: python3 test_stats_steps.py"""

from stats_steps import medians_per_step

LINES = [
    "  1000.500 1 2 I PPXR_STATS: t=1 rssiA=-30 rssiB=-32 snrA=20 kb=14",   # air 1000.0 (offset 0.5): guard
    "  1006.500 1 2 I PPXR_STATS: t=2 rssiA=-40 rssiB=-42 snrA=21 kb=14",   # air 1006: step 0
    "  1008.500 1 2 I PPXR_STATS: t=3 rssiA=-38 rssiB=-44 snrA=- kb=14",    # step 0; snrA unknown
    "  1025.500 1 2 I PPXR_STATS: t=4 rssiA=-20 rssiB=-22 snrA=25 kb=14",   # air 1025: step 1
    "  1027.500 1 2 I PPXR_EVENT: t_mono_ms=5 code=IDR level=INFO",           # not a stats line
]


def test_medians_per_step_inside_the_guarded_windows_on_the_air_clock():
    # steps (air) at 1000 and 1020, END 1040, guard 5: windows [1005, 1015) and [1025, 1035)
    out = medians_per_step(LINES, [(1000.0, "a"), (1020.0, "b")], 1040.0, 5.0, quest_minus_air_s=0.5,
                           keys=["rssiA", "rssiB", "snrA"])
    assert out == [("a", 2, {"rssiA": -39.0, "rssiB": -43.0, "snrA": 21.0}),
                   ("b", 1, {"rssiA": -20.0, "rssiB": -22.0, "snrA": 25.0})], out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
