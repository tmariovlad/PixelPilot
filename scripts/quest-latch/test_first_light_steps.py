"""Offline checks of first_light_steps.py (the rig-side detector for a sustained first-light step, e.g. the HD
+25 ms pre-VENC state). Run: python3 test_first_light_steps.py"""
import csv
import os
import subprocess
import sys
import tempfile

import first_light_steps as fls

PERIOD = 1.4   # s between flashes, as the rig runs


def series(ms_at, t0=1000.0, seconds=120.0, label="hd", period=PERIOD):
    """[(epoch, label, first_ms)] one flash per period; ms_at(t since t0) gives the value."""
    out, t = [], 0.0
    while t < seconds:
        out.append((t0 + t, label, ms_at(t)))
        t += period
    return out


def test_a_sustained_step_is_flagged_where_it_starts():
    f = series(lambda t: 45.0 + (22.0 if 70.0 <= t < 95.0 else 0.0) + (0.8 if int(t / PERIOD) % 2 else -0.8))
    ev = fls.detect(f)
    assert len(ev) == 1, ev
    e = ev[0]
    assert e.label == "hd"
    assert abs(e.start - 1070.0) <= PERIOD + 0.01, e   # the grid is t += 1.4 in floats
    assert e.end - e.start >= 10.0, e
    assert 20.0 <= e.median_ms - e.baseline_ms <= 24.0, e


def test_a_short_step_is_not_an_event():
    # enough high flashes for min_n, but they span < 10 s: only the duration rule may reject it
    f = series(lambda t: 45.0 + (22.0 if 70.0 <= t < 78.0 else 0.0))
    highs = [t for t, _, v in f if v > 60.0]
    assert len(highs) >= 5, highs
    assert highs[-1] - highs[0] < 10.0, highs
    assert fls.detect(f) == []


def test_a_step_below_the_threshold_is_not_an_event():
    f = series(lambda t: 45.0 + (10.0 if t >= 70.0 else 0.0))
    assert fls.detect(f) == []


def test_isolated_outliers_are_not_an_event():
    f = series(lambda t: 45.0 + (40.0 if int(t / PERIOD) % 5 == 0 else 0.0))
    assert fls.detect(f) == []


def test_one_normal_flash_inside_a_step_does_not_split_it():
    def ms(t):
        k = int(t / PERIOD)
        return 45.0 + (22.0 if 70.0 <= t < 100.0 and k != int(85.0 / PERIOD) else 0.0)
    assert len(fls.detect(ms_series := series(ms))) == 1, fls.detect(ms_series)


def test_a_fixed_reference_catches_a_run_that_starts_in_the_bad_state():
    f = series(lambda t: 71.0, seconds=40.0)
    assert fls.detect(f) == []                        # rolling: 71 becomes the baseline
    ev = fls.detect(f, fixed={"hd": 45.0})
    assert len(ev) == 1, ev
    assert abs(ev[0].start - 1000.0) < 1e-6, ev
    assert ev[0].baseline_ms == 45.0


def test_too_few_high_flashes_are_not_an_event_at_a_slow_flash_rate():
    # every other flash high at a 3 s period: 3 high flashes span 12 s, fewer than min_n
    def ms(t):
        k = round(t / 3.0)
        return 45.0 + (22.0 if 60.0 <= t < 73.0 and k % 2 == 0 else 0.0)
    f = series(ms, period=3.0)
    highs = [t for t, _, v in f if v > 60.0]
    assert len(highs) < 5, highs
    assert highs[-1] - highs[0] >= 10.0, highs
    assert fls.detect(f) == []


def test_a_pause_between_rig_runs_splits_the_event():
    # two 40 s runs 60 s apart, both high (Part A's two hd runs): two events, not one spanning the pause
    a = series(lambda t: 71.0, seconds=40.0)
    b = series(lambda t: 71.0, t0=1100.0, seconds=40.0)
    ev = fls.detect(a + b, fixed={"hd": 46.0})
    assert len(ev) == 2, ev
    assert ev[0].end < 1041.0, ev
    assert ev[1].start >= 1100.0, ev


def test_labels_keep_their_own_baseline():
    race = series(lambda t: 27.0, seconds=60.0, label="race")
    hd = series(lambda t: 45.0, t0=1060.0, seconds=60.0, label="hd")
    assert fls.detect(race + hd) == []                # a planned mode change is not a step


def test_the_csv_reader_keeps_labelled_ok_rows_only():
    # an empty step = a flash inside a switch guard or outside the schedule, not a label (latency-test-0d)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "per_flash.csv")
        with open(p, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["run", "id", "pc_epoch", "result", "first_us", "full_us", "step"])
            w.writerow(["01", "1", "1000.5", "ok", "45000", "45300", "hd"])
            w.writerow(["01", "2", "1001.9", "TIMEOUT", "", "", "hd"])
            w.writerow(["01", "3", "1003.3", "ok", "46000", "", ""])
        rows = fls.read_per_flash([p])
    assert rows == [(1000.5, "hd", 45.0)], rows


def test_cli_prints_the_event_and_exits_1():
    f = series(lambda t: 45.0 + (22.0 if t >= 70.0 else 0.0))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "per_flash.csv")
        with open(p, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["run", "id", "pc_epoch", "result", "first_us", "full_us", "step"])
            for i, (t, lab, ms) in enumerate(f):
                w.writerow(["01", i, f"{t:.3f}", "ok", int(ms * 1000), "", lab])
        r = subprocess.run([sys.executable, str(fls.__file__), p], capture_output=True, text=True)
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "STEP hd" in r.stdout, r.stdout


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
