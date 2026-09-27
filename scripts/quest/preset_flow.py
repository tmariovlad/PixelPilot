"""Scripted run of the headset's preset menu against the fake air (vmode_fake.py on this PC), without hands on the
controller: menu -> apply -> countdown -> commit, or with --fail the air's revert. Input goes through the debug
broadcast (DebugInput, debug builds only), which feeds the same event path as the thumbsticks. Screenshots of each
stage go to out/preset_flow_<label>/.

The fake changes no video. So the success path targets "race-b", a listed mode at the 640x480 that already streams
(the app commits only after 30 frames at the new mode's size). The --fail path targets "wide", which never reaches
pending, so the air's revert timer fires.

Needs: the XR app streaming (air on Race), the Quest reaching this PC over Wi-Fi on UDP 9998. Prefs are rewritten for
the run (vmode_air -> this PC) and restored at the end (quest_adb.set_prefs keeps gs.key only, plus these flags).
Usage: python3 preset_flow.py <label> [--fail] [--video-wait-s 15]
Check first that Windows lets UDP 9998 in to Python (the PPXR1 reports to the PC's UDP 5610 worked on 2026-09-26).
"""
import argparse
import os
import subprocess
import threading
import time

import quest_adb as q
import quest_env as env
from vmode_fake import FakeAir

ACTION = "com.openipc.pixelpilot.xr.DEBUG_INPUT"   # DebugInput.ACTION in app/xr
PREFS = {"adaptive_link_enabled": True}             # the prefs the headset runs with; vmode_air is added for the run


def inp(name):
    q.adb("shell", "am", "broadcast", "-a", ACTION, "--es", "input", name)


def shot(out, name):
    r = subprocess.run([env.ADB, "-s", env.QUEST, "exec-out", "screencap", "-p"], capture_output=True, timeout=30)
    path = os.path.join(out, name + ".png")
    with open(path, "wb") as f:
        f.write(r.stdout)
    print("  screenshot", path, len(r.stdout), "bytes", flush=True)


def restart_xr(prefs):
    q.adb("shell", "am", "force-stop", env.PKG)
    q.set_prefs(prefs)
    q.prox_close()
    q.start_xr()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--video-wait-s", type=float, default=15)
    a = ap.parse_args()
    out = os.path.join(env.OUT_DIR, "preset_flow_" + a.label)
    os.makedirs(out, exist_ok=True)
    target, steps = ("wide", 3) if a.fail else ("race-b", 4)   # rights from Race in the fake's list order

    air = FakeAir(port=9998, switch_s=3, fail="wide" if a.fail else None, same_size=True)
    threading.Thread(target=air.serve, daemon=True).start()
    t0 = time.monotonic()
    try:
        restart_xr(dict(PREFS, vmode_air=f"{env.PC_IP}:9998"))
        time.sleep(a.video_wait_s)
        print("list requests so far:", sum("list" in e for _, e in air.log), flush=True)
        inp("right")                      # opens the menu on the active mode
        time.sleep(0.6)
        shot(out, "1-menu")
        for _ in range(steps):
            inp("right")
            time.sleep(0.3)
        shot(out, "2-target")
        inp("press")
        time.sleep(1.4)                   # PresetMenu.HOLD_APPLY_MS = 1 s, plus a stats tick
        inp("release")
        time.sleep(1.5)
        shot(out, "3-switching")
        done = None
        end = time.monotonic() + 40
        while time.monotonic() < end and done is None:
            time.sleep(0.5)
            if any(e.startswith("VMODE1 commit") for _, e in air.log):
                done = "committed"
            elif any("-> reverted" in e for _, e in air.log):
                done = "reverted"
        time.sleep(0.8)
        shot(out, "4-result")
        print("result:", done, "| active on the fake:", air.active, flush=True)
    finally:
        with open(os.path.join(out, "fake_air.log"), "w", encoding="utf-8") as f:
            for t, e in air.log:
                f.write(f"{t - t0:8.2f} {e}\n")
        air.close()
        restart_xr(PREFS)                 # back to the real air unit's receiver
    ok = (done == "reverted") if a.fail else (done == "committed" and air.active == target)
    print("PASS" if ok else "FAIL", "| log:", os.path.join(out, "fake_air.log"))


if __name__ == "__main__":
    main()
