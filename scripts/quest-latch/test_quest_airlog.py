"""Offline checks of quest_airlog.py (an ab_run.sh-style air log rebuilt from a steps file and the Quest's decoded fps,
for ab_fit.py when the air's own log is lost). Run: python3 test_quest_airlog.py"""
import os
import tempfile

import quest_airlog as qa


def _write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return p


def test_set_lines_follow_the_steps_and_end_closes():
    with tempfile.TemporaryDirectory() as d:
        steps = _write(d, "s.txt", "# header\n1000 a\n1060 b\n1120 END\n")
        cap = _write(d, "c.txt", "")
        lines = qa.air_log(steps, cap, quest_minus_air_s=0.0, guard_s=15.0)
    assert lines[0] == "SET a epoch=1000", lines
    assert "SET b epoch=1060" in lines
    assert lines[-1] == "END epoch=1120", lines


def test_fps_samples_come_from_n_per_window_outside_the_guard_on_the_air_clock():
    stats = ("   1003.000 1 2 I PPXR_STATS: t=1 n=0 fps=0.0\n"          # inside a's guard: skipped
             "   1030.000 1 2 I PPXR_STATS: t=2 n=332 fps=167.0\n"      # a, air 1030.5
             "   1070.000 1 2 I PPXR_STATS: t=3 n=154 fps=50.0\n"       # b, air 1070.5 -> 77 fps
             "   1200.000 1 2 I PPXR_STATS: t=4 n=332 fps=167.0\n")     # after END: skipped
    with tempfile.TemporaryDirectory() as d:
        steps = _write(d, "s.txt", "1000 a\n1060 b\n1120 END\n")
        cap = _write(d, "c.txt", stats)
        lines = qa.air_log(steps, cap, quest_minus_air_s=-0.5, guard_s=5.0)
    s = [l for l in lines if l.startswith("S ")]
    assert s == ["S t=1030.500 fps=166.0", "S t=1070.500 fps=77.0"], s


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
