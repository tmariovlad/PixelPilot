"""Offline check of hold_steps.convert. Run: python3 test_hold_steps.py"""
from hold_steps import convert

LOG = """\
100.0 mark ADAPT1 tx=10 temp=47
100.5 PWR_BEGIN p17 was=p12 tx=11 temp=47
101.0 PWR p17 tx=12 temp=47
131.0 PWR_BEGIN p12 was=p17 tx=40 temp=47
131.4 PWR p12 tx=41 temp=48
161.0 mark CTRL tx=70 temp=48
161.5 SET_BEGIN p12m2b2f48 was=x tx=71 temp=48
162.0 SET p12m2b2f48 tx=72 temp=48
167.0 PWR p17 tx=80 temp=48
197.0 mark IDR tx=100 temp=48
197.5 mark IDR_ON tx=101 temp=48
217.5 mark IDR_OFF tx=120 temp=48
237.5 mark END tx=140 temp=48
""".splitlines()


def test_phases_power_steps_idr_and_end():
    got = convert(LOG)
    assert got == [
        "101.0 ADAPT1_p17 tx=12 temp=47",
        "131.4 ADAPT1_p12 tx=41 temp=48",
        "167.0 CTRL_p17 tx=80 temp=48",
        "197.5 IDR_ON tx=101 temp=48",
        "217.5 IDR_OFF tx=120 temp=48",
        "237.5 END tx=140 temp=48",
    ], got


def test_power_step_without_phase_keeps_plain_label():
    assert convert(["5.0 PWR p8 tx=1 temp=40"]) == ["5.0 p8 tx=1 temp=40"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
