"""Offline checks of first_light_follow.py (the live, start-anchored follower of latency-test's run files that fires a
command when first_light_steps.detect sees a sustained step). Run: python3 test_first_light_follow.py"""
import os
import tempfile

import first_light_follow as ff


def _run_text(values_ms, t0_us=1_000_000, period_us=1_400_000, timeouts=()):
    """A runNN.txt body: 'T0' then 'ok' (or TIMEOUT + a retry T0) per flash, like latency-test prints it."""
    lines, t0, k = ["Running Measurements..."], t0_us, 0
    for i, v in enumerate(values_ms):
        lines.append(f"T0 id={k} t0_esp_us={t0}")
        if i in timeouts:
            lines.append("TIMEOUT")
            t0 += 200_000
            k += 1
            lines.append(f"T0 id={k} t0_esp_us={t0}")     # the retry's LED-on
        lines.append(f"ok50:{int(v)} first_us={int(v * 1000)} full_us=NA")
        t0 += period_us
        k += 1
    return "\n".join(lines) + "\n"


def _dir(runs):
    """runs: [(name, start_epoch, values_ms, timeouts)] -> a temp dir with stamps.raw + <name>.txt."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "stamps.raw"), "w", newline="\n") as fh:
        for name, start, _, _ in runs:
            fh.write(f"{name} start {start:.9f}\n")
    for name, _, vals, tos in runs:
        with open(os.path.join(d, f"{name}.txt"), "w", newline="\n") as fh:
            fh.write(_run_text(vals, timeouts=tos))
    return d


def test_flash_epochs_are_start_anchored_and_results_pair_with_the_latest_t0():
    d = _dir([("run01", 1000.0, [45.0, 46.0, 47.0], {1})])
    fl = ff.read_flashes(d, "hd")
    # flash 0 at start; flash 1 retried 0.2 s after its first LED-on (1.4 s later); flash 2 at 1.4 + 0.2 + 1.4
    assert [round(t, 3) for t, _, _ in fl] == [1000.0, 1001.6, 1003.0], fl
    assert [v for _, _, v in fl] == [45.0, 46.0, 47.0]
    assert {lab for _, lab, _ in fl} == {"hd"}


def test_an_unterminated_last_line_waits_until_it_is_complete():
    d = _dir([("run01", 1000.0, [45.0, 46.0], ())])
    with open(os.path.join(d, "run01.txt"), "a", newline="\n") as fh:
        fh.write("T0 id=9 t0_esp_us=3800000\nok50:47 first_us=47")          # still being written
    assert len(ff.read_flashes(d, "hd")) == 2


def test_runs_without_a_file_yet_and_several_runs_are_read():
    d = _dir([("run01", 1000.0, [45.0] * 3, ()), ("run02", 1100.0, [46.0] * 2, ())])
    with open(os.path.join(d, "stamps.raw"), "a", newline="\n") as fh:
        fh.write("run03 start 1200.0\n")                                    # started, no file yet
    fl = ff.read_flashes(d, "hd")
    assert len(fl) == 5
    assert fl[3][0] == 1100.0


def test_calibration_stamps_are_not_runs():
    # latency-test's stamps.raw also carries "cal start/end" lines (latency-test-0d); only runNN are measurement runs
    d = _dir([("run01", 1000.0, [45.0] * 3, ())])
    with open(os.path.join(d, "stamps.raw"), "a", newline="\n") as fh:
        fh.write("cal start 990.0\ncal end 995.0\nrun01 end 1010.0\n")
    with open(os.path.join(d, "cal.txt"), "w", newline="\n") as fh:
        fh.write(_run_text([99.0] * 3))                               # must not be read as flashes
    fl = ff.read_flashes(d, "hd")
    assert [v for _, _, v in fl] == [45.0, 45.0, 45.0], fl


def test_a_run_that_appears_mid_follow_is_picked_up_and_can_fire():
    fired = []
    d = _dir([("run01", 1000.0, [46.0] * 20, ())])
    f = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=False,
                    runner=lambda cmd, env: fired.append(cmd), log=lambda s: None)
    f.poll(now=1030.0)
    assert fired == []
    with open(os.path.join(d, "stamps.raw"), "a", newline="\n") as fh:
        fh.write("run02 start 1062.0\n")
    with open(os.path.join(d, "run02.txt"), "w", newline="\n") as fh:
        fh.write(_run_text([72.0] * 12, timeouts={3}))                 # the state, with a TIMEOUT + retry inside
    f.poll(now=1080.0)
    assert fired == ["snap"], fired


def test_a_sustained_step_fires_once_and_dry_run_only_prints():
    fired, printed = [], []
    d = _dir([("run01", 1000.0, [46.0] * 5 + [72.0] * 12, ())])
    f = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=False,
                    runner=lambda cmd, env: fired.append((cmd, env)), log=printed.append)
    f.poll(now=2000.0)
    f.poll(now=2005.0)                                  # the same event again: no second fire
    assert len(fired) == 1, fired
    cmd, env = fired[0]
    assert cmd == "snap"
    assert env["STEP_LABEL"] == "hd"
    assert float(env["STEP_MEDIAN_MS"]) == 72.0
    assert float(env["STEP_BASELINE_MS"]) == 46.0
    dry = []
    g = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=True,
                    runner=lambda cmd, env: dry.append(cmd), log=printed.append)
    g.poll(now=2000.0)
    assert dry == [], dry
    assert any("DRY-RUN" in p and "snap" in p for p in printed), printed


def test_normal_flashes_never_fire():
    fired = []
    d = _dir([("run01", 1000.0, [45.0, 47.0, 46.0, 48.0] * 10, ())])
    f = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=False,
                    runner=lambda cmd, env: fired.append(cmd), log=lambda s: None)
    f.poll(now=2000.0)
    assert fired == []


def test_a_new_event_inside_the_cooldown_does_not_fire():
    fired = []
    runs = [("run01", 1000.0, [72.0] * 12, ()), ("run02", 1100.0, [72.0] * 12, ())]
    d = _dir(runs)
    f = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=False, cooldown_s=300.0,
                    runner=lambda cmd, env: fired.append(cmd), log=lambda s: None)
    f.poll(now=1200.0)
    assert len(fired) == 1, fired                       # two events (a pause splits them), one fire
    f2 = ff.Follower(d, "hd", {"hd": 46.0}, on_step="snap", dry_run=False, cooldown_s=0.0,
                     runner=lambda cmd, env: fired.append(cmd), log=lambda s: None)
    f2.poll(now=1200.0)
    assert len(fired) == 3, fired


def test_the_real_fire_does_not_block_and_logs_a_timeout_and_an_rc():
    import sys
    import threading
    import time
    logged = []
    done = threading.Event()

    def log(s):
        logged.append(s)
        if "rc=" in s or "timeout" in s:
            done.set()
    sleeper = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    t = time.monotonic()
    ff.fire(sleeper, {}, timeout_s=0.5, log=log)
    assert time.monotonic() - t < 0.3, "fire() blocked"
    assert done.wait(4.0), logged
    assert any("timeout" in s for s in logged), logged
    logged.clear()
    done.clear()
    ff.fire(f'"{sys.executable}" -c "import sys; sys.exit(3)"', {}, timeout_s=5.0, log=log)
    assert done.wait(5.0), logged
    assert any("rc=3" in s for s in logged), logged


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
