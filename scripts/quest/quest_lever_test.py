"""One decoder-lever run on the Quest: set prefs, launch the XR activity, replay a recorded RTP
stream over Wi-Fi, and report what the decoder did. Each run also prints the AMediaFormat keys the
decoder was actually configured with, so a lever that did not take effect is visible.

Library for quest_lever_repeat.py / quest_codec_matrix.py / quest_recheck.py (and set_prefs() for the
bash runners). Configuration: quest_env.py."""
import os
import re
import subprocess
import sys
import time

import quest_env as env
from quest_adb import adb, pref_xml, prox_close, set_prefs, start_xr  # noqa: F401  (re-exported: t.adb / t.set_prefs)

PKG = env.PKG
KEY_NAMES = ["low-latency", "vendor.low-latency.enable", "vendor.qti-ext-dec-low-latency.enable",
             "vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req",
             "vendor.rtc-ext-dec-low-latency.enable", "priority", "vendor.qti-ext-dec-picture-order.enable",
             "operating-rate", "max-input-size"]
SHORT = {"low-latency": "LL", "vendor.low-latency.enable": "vLL", "vendor.qti-ext-dec-low-latency.enable": "qti",
         "vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req": "hisi",
         "vendor.rtc-ext-dec-low-latency.enable": "rtc", "priority": "prio",
         "vendor.qti-ext-dec-picture-order.enable": "PO", "operating-rate": "OR", "max-input-size": "MIS"}


def applied_keys(log):
    """Keys present in the last 'Configuring decoder ...: <format>' line."""
    lines = re.findall(r"Configuring decoder [^:]*: (.*)", log)
    if not lines:
        return "?"
    fmt = lines[-1]
    return "+".join(SHORT[k] for k in KEY_NAMES if (k + ":") in fmt) or "none"


def run(name, flags, stream, loops=2):
    """stream = a file name in streams/ or a path. Returns (log, decode_ms, frames, 'keys@component')."""
    adb("shell", "am", "force-stop", PKG)
    set_prefs(flags)
    adb("logcat", "-c")
    prox_close()
    start_xr(wait=True)
    time.sleep(4)
    subprocess.run([sys.executable, os.path.join(env.HERE, "rtp_play.py"), env.stream_path(stream),
                    str(env.VIDEO_PORT), str(loops), env.QUEST_HOST],
                   capture_output=True, env={**os.environ, "KEEPAWAKE": "1"})
    time.sleep(2)
    pid = adb("shell", "pidof", PKG).strip()
    log = adb("logcat", "-d", f"--pid={pid}") if pid else adb("logcat", "-d")
    dec = [float(x) for x in re.findall(r"\| Decoding:([0-9.]+)", log)][1:]  # skip the warm-up window
    frames = [int(x) for x in re.findall(r"N Decoded Frames:([0-9]+)", log)]
    errs = len(re.findall(r"Input buffer too small|AMediaCodec_(?:configure|start) failed|FATAL", log))
    decode = sum(dec) / len(dec) if dec else -1.0
    comp = (re.findall(r"Configuring decoder (\S+)[^:]*:", log) or ["?"])[-1]
    print(f"{name:36s} comp={comp:26s} keys={applied_keys(log):12s} frames={max(frames) if frames else 0:4d} "
          f"decode_ms={decode:6.2f} errors={errs}", flush=True)
    return log, decode, (max(frames) if frames else 0), applied_keys(log) + "@" + comp
