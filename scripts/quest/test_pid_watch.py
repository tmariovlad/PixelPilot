"""Offline checks of pid_watch.sh against a fake adb (quest_env's ADB override). Run: python3 test_pid_watch.py"""
import os
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASH = shutil.which("bash") or "bash"


def fake_adb(tmp, pids):
    """An adb that answers `pidof` with pids[i] on its i-th call (the last one repeats; "" = app gone)."""
    state = os.path.join(tmp, "n").replace("\\", "/")
    answers = " ".join(f"'{p}'" for p in pids)
    path = os.path.join(tmp, "adb.sh")
    with open(path, "w", newline="\n") as f:
        f.write(f"#!/bin/bash\nA=({answers})\nn=$(cat '{state}' 2>/dev/null || echo 0)\n"
                f"echo $((n + 1)) > '{state}'\ni=$(( n < ${{#A[@]}} ? n : ${{#A[@]}} - 1 ))\n"
                "[ -n \"${A[$i]}\" ] && echo \"${A[$i]}\"\nexit 0\n")
    return path.replace("\\", "/")


def run(tmp, pids, until_in_s, step_s, **env):
    e = dict(os.environ, ADB=fake_adb(tmp, pids), **env)
    t0 = time.monotonic()
    p = subprocess.run([BASH, "pid_watch.sh", str(int(time.time()) + until_in_s), str(step_s)], cwd=HERE, env=e,
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, time.monotonic() - t0


def test_returns_at_until_not_one_interval_later():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, dt = run(tmp, ["4242"], until_in_s=3, step_s=60)
    assert rc == 0 and "until reached, app alive" in out, out
    assert dt < 15, f"took {dt:.1f} s for a 3 s watch with a 60 s interval (overshoot)"


def test_gone_exits_at_once():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, dt = run(tmp, ["4242", ""], until_in_s=60, step_s=1)
    assert rc == 1 and "GONE" in out and dt < 15, (rc, out, dt)


def test_changed_pid_fails_unless_restart_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, _ = run(tmp, ["4242", "5151"], until_in_s=60, step_s=1)
    assert rc == 1 and "CHANGED 4242 -> 5151" in out, out
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, _ = run(tmp, ["4242", "5151"], until_in_s=3, step_s=1, ALLOW_RESTART="1")
    assert rc == 0 and "restarted 4242 -> 5151 (allowed)" in out, out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
