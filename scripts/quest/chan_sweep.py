"""Find the channel of a wfb-ng air unit: for each channel start PixelPilot (2D) on the Quest's RTL
and read its link-quality log (-1024 = no wfb packets).
Usage: python3 chan_sweep.py [channel ...]   (default: a 5.8 GHz-first list)"""
import re, subprocess, sys, time
import quest_env as env
import quest_lever_test as t

PKG, ACT = env.PKG, env.ACTIVITY_2D
order = [int(c) for c in sys.argv[1:]] or [157, 149, 153, 165, 36, 40, 44, 48, 161, 52, 56, 60, 64, 100, 104, 108,
                                           112, 116, 120, 124, 128, 132, 136, 140, 144, 32, 68, 96, 1, 6, 11, 2, 3, 4, 5, 7, 8, 9, 10, 12, 13]
for ch in order:
    t.adb("shell", "am", "force-stop", PKG)
    t.set_prefs({"wifi-channel": ch})
    t.adb("logcat", "-c")
    t.adb("shell", "am", "start", "-n", f"{PKG}/{ACT}")
    time.sleep(8)
    pid = t.adb("shell", "pidof", PKG).strip()
    log = t.adb("logcat", "-d", f"--pid={pid}") if pid else ""
    q = [int(x) for x in re.findall(r"quality (-?\d+)", log)]
    good = [x for x in q if x > -1024]
    crash = "FATAL/abort" if re.search(r"Fatal signal|FATAL EXCEPTION", t.adb("logcat", "-d", "-b", "crash")) else ""
    print(f"ch {ch:3d}: samples={len(q):3d} above_floor={len(good):3d} max={max(q) if q else 'n/a'} {crash}", flush=True)
    if len(good) > 5:
        print("FOUND channel", ch); break
