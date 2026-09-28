"""Scripted check of the in-headset menu (docs/xr/menu-design.md) through the debug broadcast (DebugInput, debug
builds only), which feeds the same event path as the right thumbstick. No air change is made.

Steps:
1. Open the menu (click held 1.4 s).
2. Stats > Summary, Latency and Link pages (screenshots for the plausibility check of docs/xr/stats-backend.md §5).
3. Picture > Tight reorder toggled twice. PASS if the pref flips and flips back, with no relaunch (the same pid).
4. Display > Timestamps toggled. PASS if the pref flips and the XR activity relaunches (a new pid); then toggled back.
5. Close.
Screenshots of each stage (both eyes, as screencap gives them) go to out/quality_private/menu_<label>/; they may show
the room, so they stay local. At the end the headset's prefs file is written back exactly as it was, and XR restarts.

The display must be on for input to be processed (a sleeping headset pauses the activity): wear the headset, or pass
--keep-awake (prox_close for the run, automation_disable at the end).
Usage: python3 menu_check.py <label> [--keep-awake]
"""
import argparse
import os
import re
import subprocess
import sys
import time

import quest_adb as q
import quest_env as env

ACTION = "com.openipc.pixelpilot.xr.DEBUG_INPUT"   # DebugInput.ACTION in app/xr


def inp(name, wait=0.35):
    q.adb("shell", "am", "broadcast", "-a", ACTION, "--es", "input", name)
    time.sleep(wait)


def hold(seconds):
    inp("press", 0)
    time.sleep(seconds)
    inp("release", 0.5)


def moves(name, n):
    for _ in range(n):
        inp(name)


def shot(out, name):
    r = subprocess.run([env.ADB, "-s", env.QUEST, "exec-out", "screencap", "-p"], capture_output=True, timeout=30)
    path = os.path.join(out, name + ".png")
    with open(path, "wb") as f:
        f.write(r.stdout)
    print("  screenshot", path, len(r.stdout), "bytes", flush=True)


def prefs():
    return q.adb("shell", "run-as", env.PKG, "cat", q.PREFS_FILE).replace(chr(13), "")


def pref_bool(xml, key):
    m = re.search(r'<boolean name="%s" value="(true|false)"' % re.escape(key), xml)
    return None if m is None else m.group(1) == "true"


def pid():
    return q.adb("shell", "pidof", env.PKG).strip()


def check(ok, what, results):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + what, flush=True)


def open_menu():
    hold(1.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--keep-awake", action="store_true")
    a = ap.parse_args()
    out = os.path.join(env.OUT_DIR, "quality_private", "menu_" + a.label)
    os.makedirs(out, exist_ok=True)
    original = prefs()
    if "</map>" not in original:
        raise SystemExit("could not read the headset's prefs")
    results = []
    try:
        if a.keep_awake:
            q.prox_close()
        p0 = pid()
        open_menu()
        shot(out, "1-root")
        inp("right")                     # Stats folder
        inp("right", 1.5)                # Summary page (the stats refresh at 2 Hz)
        shot(out, "2-stats-summary")
        inp("left")                      # back to the Stats folder, highlight on Summary
        inp("down")                      # Latency
        inp("right", 1.5)
        shot(out, "2b-stats-latency")
        inp("left")
        inp("down")                      # Link
        inp("right", 1.5)
        shot(out, "2c-stats-link")
        moves("left", 2)                 # back to the root
        inp("down")                      # Picture
        inp("right")
        shot(out, "3-picture")
        before = pref_bool(prefs(), "rtp_tight_reorder")
        moves("down", 4)                 # Tight reorder (5th line)
        inp("right", 1.0)                # toggle
        mid = pref_bool(prefs(), "rtp_tight_reorder")
        shot(out, "4-reorder-toggled")
        inp("right", 1.0)                # toggle back
        after = pref_bool(prefs(), "rtp_tight_reorder")
        was = True if before is None else before
        check(mid is (not was) and after is was and pid() == p0,
              f"live lever: rtp_tight_reorder {was} -> {mid} -> {after}, same pid", results)

        inp("left")                      # back to the root, highlight on Picture
        moves("down", 2)                 # Display
        inp("right")
        shot(out, "5-display")
        moves("down", 4)                 # Timestamps (5th line)
        ts_before = pref_bool(prefs(), "xr_use_timestamps")
        inp("right", 0.5)                # toggle -> relaunch
        time.sleep(6)
        p1 = pid()
        ts_mid = pref_bool(prefs(), "xr_use_timestamps")
        was_ts = False if ts_before is None else ts_before
        check(ts_mid is (not was_ts) and p1 != "" and p1 != p0,
              f"relaunch lever: xr_use_timestamps {was_ts} -> {ts_mid}, pid {p0} -> {p1}", results)
        shot(out, "6-after-relaunch")
        # A relaunch starts a new menu: open it again and toggle back (root -> Display is 3 downs).
        open_menu()
        moves("down", 3)
        inp("right")
        moves("down", 4)
        inp("right", 0.5)
        time.sleep(6)
        check(pref_bool(prefs(), "xr_use_timestamps") is was_ts, "relaunch lever toggled back", results)
        open_menu()
        moves("up", 1)                   # Close (the last root line)
        inp("press", 0.1)
        inp("release", 0.8)
        shot(out, "7-closed")
    finally:
        q.force_stop()
        q.write_prefs(original)
        if a.keep_awake:
            q.adb("shell", "am", "broadcast", "-a", "com.oculus.vrpowermanager.automation_disable")
        q.start_xr()
        print("prefs restored exactly; XR restarted", flush=True)
    print(f"{sum(results)}/{len(results)} checks passed", flush=True)
    sys.exit(0 if results and all(results) else 1)


if __name__ == "__main__":
    main()
