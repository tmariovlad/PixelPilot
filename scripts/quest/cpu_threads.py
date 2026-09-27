"""CPU use per thread of the running PixelPilotXr over a window, from /proc/<pid>/task/*/stat (utime+stime).

More precise than one `top -H` sample: the tick counts are read twice, N seconds apart, over adb.
Usage: python3 cpu_threads.py [seconds=20] [top_n=8]
Prints each busy thread's CPU in % of one core, the process total, and the VpnToUdpThread line.
"""
import re
import subprocess
import sys
import time

from quest_env import ADB, PKG, QUEST

CLK_TCK = 100  # USER_HZ on Android/Linux


def adb_shell(cmd):
    return subprocess.run([ADB, "-s", QUEST, "shell", cmd], capture_output=True, text=True, check=True).stdout


def ticks(pid):
    """{tid: (name, utime+stime)} from /proc/<pid>/task/*/stat. The name field may contain spaces."""
    out = adb_shell(f"cat /proc/{pid}/task/*/stat 2>/dev/null")
    res = {}
    for line in out.splitlines():
        m = re.match(r"(\d+) \((.*)\) (.*)", line)
        if not m:
            continue
        rest = m.group(3).split()
        res[int(m.group(1))] = (m.group(2), int(rest[11]) + int(rest[12]))  # fields 14, 15: utime, stime
    return res


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    pid = adb_shell(f"pidof {PKG}").strip()
    if not pid:
        sys.exit("app not running")
    a, t0 = ticks(pid), time.time()
    time.sleep(secs)
    b, t1 = ticks(pid), time.time()
    wall = t1 - t0
    rows = []
    for tid, (name, tb) in b.items():
        ta = a.get(tid, (name, tb))[1]
        rows.append((100.0 * (tb - ta) / CLK_TCK / wall, tid, name))
    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)
    print(f"pid {pid}, {wall:.1f} s window, process total {total:.1f} % of one core")
    for pct, tid, name in rows[:top_n]:
        print(f"  {pct:6.1f} %  {tid:6d}  {name}")
    vpn = [r for r in rows if r[2] == "VpnToUdpThread"]
    print("VpnToUdpThread:", ", ".join(f"{r[0]:.1f} %" for r in vpn) if vpn else "not found")


if __name__ == "__main__":
    main()
