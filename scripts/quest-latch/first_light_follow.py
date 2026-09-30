"""Live follower of a latency-test rig run: reads the rig's files while they grow and runs a command the moment
first_light_steps.detect sees a sustained first-light step, so an air-side snapshot can be taken while a rare state
(the HD 71 ms state of 2026-09-30 Part A) still exists. A post-hoc detection comes too late for that.

Input: the rig's run directory as latency-test writes it during a slot: stamps.raw ("<run> start <epoch>" written just
before each run) and <run>.txt, the serial capture ("T0 id=<n> t0_esp_us=<us>" per LED-on, a retry after a timeout
prints a second T0, then "ok<ldr>:<ms> first_us=<n> full_us=<n|NA>" or "TIMEOUT"). A flash's PC epoch is
start + (t0 - first t0 of the run) / 1e6, as latency-test's per_flash.py --anchor start (error <~0.3 s, latency-test-0d).
An unterminated last line is left for the next poll.

On each new event (after --cooldown-s since the last fire) it runs --on-step in the background with a timeout and logs
its rc, with STEP_LABEL / STEP_START / STEP_MEDIAN_MS / STEP_BASELINE_MS in the environment; --dry-run only prints.

Usage: python3 first_light_follow.py <rig run dir> --label hd --fixed hd=46 --on-step "<cmd>" [--dry-run]
           [--poll-s 5] [--cooldown-s 300] [--fire-timeout-s 15] [--until <epoch>]
"""
import argparse
import os
import re
import signal
import subprocess
import tempfile
import threading
import time

import first_light_steps as fls

_EV = re.compile(r"^(T0 id=(\d+) t0_esp_us=(\d+)|ok\d+:\d+ first_us=(\d+) full_us=(\d+|NA)|TIMEOUT)\s*$")


def _complete_lines(path):
    """The file's lines that end in a newline (the last one may still be being written)."""
    try:
        with open(path, encoding="utf-8", errors="ignore", newline="") as fh:
            text = fh.read()
    except FileNotFoundError:
        return []
    return text.split("\n")[:-1]


_RUN = re.compile(r"^run\d+$")   # stamps.raw also carries "cal start/end" lines, which are not measurement runs


def _starts(run_dir):
    starts = {}
    for line in _complete_lines(os.path.join(run_dir, "stamps.raw")):
        w = line.split()
        if len(w) >= 3 and w[1] == "start" and _RUN.match(w[0]):
            starts[w[0]] = float(w[2])
    return starts


def _run_flashes(path, start, label):
    out, first_t0, cur = [], None, None
    for line in _complete_lines(path):
        m = _EV.match(line.strip())
        if not m:
            continue
        if m.group(2):
            t0 = int(m.group(3))
            first_t0 = t0 if first_t0 is None else first_t0
            cur = t0
        elif cur is not None and first_t0 is not None:
            if m.group(4):
                out.append((start + (cur - first_t0) / 1e6, label, int(m.group(4)) / 1000.0))
            cur = None
    return out


def read_flashes(run_dir, label):
    """[(pc_epoch, label, first_ms)] of every ok flash so far, in time order."""
    flashes = []
    for run, start in _starts(run_dir).items():
        flashes += _run_flashes(os.path.join(run_dir, f"{run}.txt"), start, label)
    return sorted(flashes)


def _kill_tree(p):
    """Kill the shell and what it started (on Windows killing cmd.exe alone leaves e.g. a hung ssh running)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        os.killpg(p.pid, signal.SIGKILL)


def fire(cmd, env, timeout_s=15.0, log=print):
    """Run cmd in the background with a timeout; log its rc or the timeout. Returns at once.
    cmd is the operator's own command line (--on-step), so it runs through the shell on purpose. Its output goes to a
    temp file, not a pipe: a grandchild holding a pipe would keep the wait going past the timeout."""
    def work():
        with tempfile.TemporaryFile() as out:
            p = subprocess.Popen(cmd, shell=True, env={**os.environ, **env}, stdout=out, stderr=subprocess.STDOUT,
                                 start_new_session=os.name != "nt")
            try:
                rc = p.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                _kill_tree(p)
                log(f"{time.time():.1f} on-step timeout after {timeout_s:.1f} s (killed)")
                return
            out.seek(0)
            text = out.read().decode("utf-8", "replace").strip()
            log(f"{time.time():.1f} on-step rc={rc} {text[:200]}")
    threading.Thread(target=work, daemon=True).start()


class Follower:
    """Polls a rig run directory; fires on_step once per new sustained step, at most once per cooldown."""

    def __init__(self, run_dir, label, fixed, on_step, dry_run, cooldown_s=300.0, runner=None, log=print,
                 fire_timeout_s=15.0):
        self.run_dir, self.label, self.fixed = run_dir, label, fixed
        self.on_step, self.dry_run, self.cooldown_s, self.log = on_step, dry_run, cooldown_s, log
        self.runner = runner or (lambda cmd, env: fire(cmd, env, fire_timeout_s, log))
        self.seen = set()
        self.last_fire = None

    def poll(self, now):
        """One look at the files; returns the events that fired (or would have, in dry-run)."""
        fired = []
        for e in fls.detect(read_flashes(self.run_dir, self.label), self.fixed):
            if e.start in self.seen:
                continue
            self.seen.add(e.start)
            self.log(f"{now:.1f} STEP {e.label} start={e.start:.1f} n={e.n} median={e.median_ms:.1f} "
                     f"baseline={e.baseline_ms:.1f} (+{e.median_ms - e.baseline_ms:.1f} ms)")
            if self.last_fire is not None and now - self.last_fire < self.cooldown_s:
                self.log(f"{now:.1f} cooldown: not firing ({now - self.last_fire:.0f} s since the last)")
                continue
            env = {"STEP_LABEL": e.label, "STEP_START": f"{e.start:.1f}", "STEP_MEDIAN_MS": f"{e.median_ms:.1f}",
                   "STEP_BASELINE_MS": f"{e.baseline_ms:.1f}"}
            self.last_fire = now
            fired.append(e)
            if self.dry_run:
                self.log(f"{now:.1f} DRY-RUN would run: {self.on_step}")
            else:
                self.runner(self.on_step, env)
        return fired


def main():
    ap = argparse.ArgumentParser(description="Live rig follower: fire a command on a sustained first-light step")
    ap.add_argument("run_dir")
    ap.add_argument("--label", default="hd")
    ap.add_argument("--fixed", default="", help="label=ms,... (e.g. hd=46)")
    ap.add_argument("--on-step", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--poll-s", type=float, default=5.0)
    ap.add_argument("--cooldown-s", type=float, default=300.0)
    ap.add_argument("--fire-timeout-s", type=float, default=15.0)
    ap.add_argument("--until", type=float, default=float("inf"), help="stop at this PC epoch")
    a = ap.parse_args()
    f = Follower(a.run_dir, a.label, fls._fixed(a.fixed), a.on_step, a.dry_run, a.cooldown_s,
                 log=lambda s: print(s, flush=True), fire_timeout_s=a.fire_timeout_s)
    print(f"{time.time():.1f} following {a.run_dir} label={a.label} fixed={a.fixed or '-'} "
          f"{'DRY-RUN' if a.dry_run else 'LIVE'}", flush=True)
    try:
        while time.time() < a.until:
            f.poll(time.time())
            time.sleep(a.poll_s)
    except KeyboardInterrupt:
        pass
    print(f"{time.time():.1f} follower end", flush=True)


if __name__ == "__main__":
    main()
