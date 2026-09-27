"""Scripted run of the headset's preset menu against the fake air (vmode_fake.py on this PC), without hands on the
controller: menu -> apply -> countdown -> commit, or with --fail the air's revert. Input goes through the debug
broadcast (DebugInput, debug builds only), which feeds the same event path as the thumbsticks. Screenshots of each
stage go to out/preset_flow_<label>/.

The fake changes no video. So the success path targets "race-b", a listed mode at the 640x480 that already streams
(the app commits only after 30 frames at the new mode's size). The --fail path targets "wide", which never reaches
pending, so the air's revert timer fires.

Needs: the XR app streaming (air on Race), the Quest reaching this PC over Wi-Fi on UDP 9998. The headset's prefs are
kept as they are; only vmode_air (-> this PC) is added for the run, and the original file is written back at the end.
Usage: python3 preset_flow.py <label> [--fail] [--port 9998] [--video-wait-s 15]
Check first that Windows lets the UDP port in to Python; if 9998 is blocked, --port 5610 (the PPXR1 report port, which
reached the PC on 2026-09-26). Do not change firewall rules for this.
"""
import argparse
import os
import re
import subprocess
import threading
import time

import quest_adb as q
import quest_env as env
from vmode_fake import FakeAir

ACTION = "com.openipc.pixelpilot.xr.DEBUG_INPUT"   # DebugInput.ACTION in app/xr
VMODE_PREF = re.compile(r'\s*<string name="vmode_air">[^<]*</string>')


def inp(name):
    q.adb("shell", "am", "broadcast", "-a", ACTION, "--es", "input", name)


def shot(out, name):
    r = subprocess.run([env.ADB, "-s", env.QUEST, "exec-out", "screencap", "-p"], capture_output=True, timeout=30)
    path = os.path.join(out, name + ".png")
    with open(path, "wb") as f:
        f.write(r.stdout)
    print("  screenshot", path, len(r.stdout), "bytes", flush=True)


def restart_xr(prefs_xml):
    q.adb("shell", "am", "force-stop", env.PKG)
    q.write_prefs(prefs_xml)
    q.prox_close()
    q.start_xr()


def with_vmode_air(xml, target):
    """The headset's prefs with vmode_air set to target (every other pref unchanged)."""
    xml = VMODE_PREF.sub("", xml)
    return xml.replace("</map>", q.pref_xml("vmode_air", target) + "</map>", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--port", type=int, default=9998)
    ap.add_argument("--video-wait-s", type=float, default=15)
    a = ap.parse_args()
    out = os.path.join(env.OUT_DIR, "preset_flow_" + a.label)
    os.makedirs(out, exist_ok=True)
    target, steps = ("wide", 3) if a.fail else ("race-b", 4)   # rights from Race in the fake's list order

    air = FakeAir(port=a.port, switch_s=3, fail="wide" if a.fail else None, same_size=True)
    threading.Thread(target=air.serve, daemon=True).start()
    t0 = time.monotonic()
    original = q.adb("shell", "run-as", env.PKG, "cat", q.PREFS_FILE).replace(chr(13), "")
    if "</map>" not in original:
        raise SystemExit("could not read the headset's prefs")
    try:
        restart_xr(with_vmode_air(original, f"{env.PC_IP}:{a.port}"))
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
        restart_xr(VMODE_PREF.sub("", original))   # back to the headset's own prefs (no vmode_air)
    ok = (done == "reverted") if a.fail else (done == "committed" and air.active == target)
    print("PASS" if ok else "FAIL", "| log:", os.path.join(out, "fake_air.log"))


if __name__ == "__main__":
    main()
