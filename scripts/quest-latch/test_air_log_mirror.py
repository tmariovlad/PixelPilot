"""Offline checks of air_log_mirror.sh against a fake scp (SCP override). Run: python3 test_air_log_mirror.py"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BASH = shutil.which("bash") or "bash"

# The fake scp: its i-th call follows FAKE_PLAN[i] (the last entry repeats): "down" = the air does not answer
# (exit 255, nothing copied), "ok:<dir>" = serve the air's filesystem from $FAKE_ROOT/<dir> (remote globs expand
# there, a path that matches nothing is an error for that path only, like scp -O). Every call's arguments are logged.
FAKE_SCP = r"""#!/bin/bash
echo "$*" >> "$FAKE_ROOT/calls.log"
n=$(cat "$FAKE_ROOT/n" 2>/dev/null || echo 0); echo $((n + 1)) > "$FAKE_ROOT/n"
IFS=, read -ra P <<< "$FAKE_PLAN"
i=$(( n < ${#P[@]} ? n : ${#P[@]} - 1 )); step=${P[$i]}
[ "$step" = down ] && { echo "ssh: connect to host 192.168.100.132 port 22: Connection timed out" >&2; exit 255; }
dir="$FAKE_ROOT/${step#ok:}"
args=("$@"); dest=${args[$(( ${#args[@]} - 1 ))]}; spec=${args[$(( ${#args[@]} - 2 ))]}
set -f; paths=( ${spec#*:} ); set +f
rc=0
for p in "${paths[@]}"; do
  m=( $dir$p )
  if [ -e "${m[0]}" ]; then cp "${m[@]}" "$dest"; else echo "scp: $p: No such file or directory" >&2; rc=1; fi
done
exit $rc
"""


def air(root, name, files):
    """A fake air filesystem $root/<name>/ with {absolute path: content}; /etc/hostname is always there."""
    for path, content in {"/etc/hostname": "openipc-ssc338q\n", **files}.items():
        full = os.path.join(root, name, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", newline="\n") as fh:
            fh.write(content)


def run(root, out, plan, end_in_s, *files, interval_s=0, rounds=None):
    """rounds defaults to the plan's length (MIRROR_ROUNDS), so a test does not race the wall clock (a round takes
    1-2 s of process starts in Git Bash); rounds=0 with a near end_in_s checks the end epoch itself."""
    scp = os.path.join(root, "scp.sh")
    with open(scp, "w", newline="\n") as fh:
        fh.write(FAKE_SCP)
    env = dict(os.environ, SCP=scp.replace("\\", "/"), FAKE_ROOT=root.replace("\\", "/"), FAKE_PLAN=plan,
               MIRROR_INTERVAL_S=str(interval_s),
               MIRROR_ROUNDS=str(rounds if rounds is not None else len(plan.split(","))))
    p = subprocess.run([BASH, "air_log_mirror.sh", out.replace("\\", "/"), str(int(time.time()) + end_in_s), *files],
                       cwd=HERE, env=env, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Mirror(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "slot")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_good_round_copies_the_default_list_by_glob_and_logs_it(self):
        air(self.tmp, "a", {"/tmp/ab_l6.log": "SET f320 epoch=1\n", "/tmp/air_health.log": "EV t=1 code=ROTATE\n",
                            "/tmp/wfbtx.log": "5000\tPKT\t1:2\n"})
        rc, log = run(self.tmp, self.out, "ok:a", 0)
        self.assertEqual(rc, 0, log)
        self.assertEqual(read(os.path.join(self.out, "ab_l6.log")), "SET f320 epoch=1\n")
        self.assertEqual(read(os.path.join(self.out, "air_health.log")), "EV t=1 code=ROTATE\n")
        self.assertTrue(os.path.exists(os.path.join(self.out, "wfbtx.log")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "hostname")))    # the probe is not a log
        calls = read(os.path.join(self.tmp, "calls.log"))
        self.assertIn("-O", calls.split())
        self.assertIn("-q", calls.split())
        self.assertIn("root@192.168.100.132:", calls)
        mlog = read(os.path.join(self.out, "mirror.log"))
        self.assertRegex(mlog, r"\d+ OK .*updated=3")
        self.assertIn("END", mlog)

    def test_an_empty_or_missing_file_keeps_the_last_good_copy(self):
        air(self.tmp, "a", {"/tmp/ab_hdp.log": "SET p2400 epoch=1\n", "/tmp/air_health.log": "EV t=1\n"})
        air(self.tmp, "b", {"/tmp/ab_hdp.log": ""})          # emptied, and air_health.log gone
        rc, log = run(self.tmp, self.out, "ok:a,ok:b", 600)
        self.assertEqual(rc, 0, log)
        self.assertEqual(read(os.path.join(self.out, "ab_hdp.log")), "SET p2400 epoch=1\n")
        self.assertEqual(read(os.path.join(self.out, "air_health.log")), "EV t=1\n")

    def test_a_shorter_copy_after_a_reboot_keeps_the_pre_reboot_one_aside(self):
        air(self.tmp, "a", {"/tmp/air_health.log": "EV t=1 long pre-hang history\nAH t=2\nAH t=3\n"})
        air(self.tmp, "b", {"/tmp/air_health.log": "EV t=99 boot\n"})
        rc, log = run(self.tmp, self.out, "ok:a,ok:b", 600)
        self.assertEqual(rc, 0, log)
        self.assertEqual(read(os.path.join(self.out, "air_health.log")), "EV t=99 boot\n")
        pre = [f for f in os.listdir(self.out) if f.startswith("air_health.log.") and f.endswith(".pre")]
        self.assertEqual(len(pre), 1, os.listdir(self.out))
        self.assertIn("pre-hang history", read(os.path.join(self.out, pre[0])))

    def test_a_hang_is_logged_once_polling_goes_on_and_the_return_is_logged(self):
        # slots include planned reboots and power cycles: the logs after the recovery matter too (coordinator)
        air(self.tmp, "a", {"/tmp/ab_l6.log": "SET f384 epoch=789220 and the pre-hang lines\n"})
        air(self.tmp, "b", {"/tmp/ab_l6.log": "after boot\n"})
        rc, log = run(self.tmp, self.out, "ok:a,down,down,down,down,ok:b", 600)
        self.assertEqual(rc, 2, log)                            # the air was unreachable >= 3 rounds
        mlog = read(os.path.join(self.out, "mirror.log"))
        for k in (1, 2, 3, 4):
            self.assertRegex(mlog, rf"\d+ UNREACHABLE {k}\b")
        self.assertEqual(len([l for l in mlog.splitlines() if " HANG? " in l]), 1, mlog)
        self.assertRegex(mlog, r"\d+ HANG\? unreachable since (\d+)")
        self.assertRegex(mlog, r"\d+ BACK at \d+ after 4 unreachable rounds")
        self.assertEqual(read(os.path.join(self.out, "ab_l6.log")), "after boot\n")   # mirrored after the recovery
        pre = [f for f in os.listdir(self.out) if f.startswith("ab_l6.log.") and f.endswith(".pre")]
        self.assertIn("pre-hang lines", read(os.path.join(self.out, pre[0])))
        self.assertGreaterEqual(int(read(os.path.join(self.tmp, "n"))), 6)

    def test_a_short_outage_is_no_hang_and_exits_0(self):
        air(self.tmp, "a", {"/tmp/ab_l6.log": "x\n"})
        rc, log = run(self.tmp, self.out, "ok:a,down,down,ok:a", 600)
        self.assertEqual(rc, 0, log)
        mlog = read(os.path.join(self.out, "mirror.log"))
        self.assertNotIn("HANG?", mlog)
        self.assertRegex(mlog, r"\d+ BACK at \d+ after 2 unreachable rounds")

    def test_a_reachable_air_without_the_files_is_not_a_hang(self):
        air(self.tmp, "a", {})                                  # only /etc/hostname: early in a slot
        rc, log = run(self.tmp, self.out, "ok:a", 600, rounds=3)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("UNREACHABLE", read(os.path.join(self.out, "mirror.log")))

    def test_the_end_epoch_stops_the_polling(self):
        air(self.tmp, "a", {"/tmp/ab_l6.log": "x\n"})
        t0 = time.time()
        rc, log = run(self.tmp, self.out, "ok:a", 3, interval_s=1, rounds=0)
        self.assertEqual(rc, 0, log)
        self.assertLess(time.time() - t0, 30)
        self.assertTrue(read(os.path.join(self.out, "mirror.log")).rstrip().endswith("END"))

    def test_an_explicit_file_list_replaces_the_default(self):
        air(self.tmp, "a", {"/tmp/ab_l6.log": "x\n", "/tmp/custom.txt": "y\n"})
        rc, log = run(self.tmp, self.out, "ok:a", 0, "custom.txt")
        self.assertEqual(rc, 0, log)
        self.assertTrue(os.path.exists(os.path.join(self.out, "custom.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "ab_l6.log")))


if __name__ == "__main__":
    unittest.main()
