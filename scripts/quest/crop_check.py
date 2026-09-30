"""Does the XR layer draw the decoder's padding rows? For each stream (edges_*.rtp: a 4-row green
band at the top, a red band of the same height at the bottom, rtp_gen_edges.sh): relaunch XR, replay it over Wi-Fi, screencap mid-replay,
and measure both bands' thickness in screen rows in the left eye. x264 pads 360 -> 368 and 1080 -> 1088 by repeating the
last rows, so a layer that draws the padding shows red/green ~3 (12 vs 4 rows); one that honours the crop shows ~1.
Also saves the decoder's format-change lines (the crop keys). No image is printed; only numbers.
Usage: python3 crop_check.py <label> <stream> [<stream> ...]   (APK installed, guardian_pause 1; one line per stream)
First measured 2026-09-30 (docs/xr/link-envelope.md, S2 section): 3b37a562 drew the padding (red/green 2.86 at 360),
the crop fix shows 1.00."""
import os
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
import quest_adb as q          # noqa: E402
import quest_env as env        # noqa: E402

OUT = os.path.join(HERE, "out", "crop_check")


def bands(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    eye = a[:, : a.shape[1] // 2]
    r, g, b = eye[..., 0], eye[..., 1], eye[..., 2]
    red = (r > 150) & (g < 90) & (b < 90)
    green = (g > 150) & (r < 120) & (b < 120)
    out = {}
    for name, m in (("green", green), ("red", red)):
        frac = m.mean(axis=1)
        if frac.max() < 0.05:
            out[name] = (0, -1, 0.0)
            continue
        rows = np.where(frac >= 0.6 * frac.max())[0]
        # contiguous runs of band rows
        runs, start = [], rows[0]
        for i in range(1, len(rows) + 1):
            if i == len(rows) or rows[i] != rows[i - 1] + 1:
                runs.append((start, rows[i - 1]))
                if i < len(rows):
                    start = rows[i]
        # the band is the topmost green run / the bottommost red run (testsrc2 has green areas mid-picture)
        s, e = runs[0] if name == "green" else runs[-1]
        out[name] = (int(e - s + 1), int(s), float(frac.max()))
    return out


def check(label, stream):
    q.adb("shell", "am", "force-stop", env.PKG)
    q.adb("logcat", "-c")
    q.prox_close()
    q.start_xr(wait=True)
    time.sleep(4)
    play = threading.Thread(target=lambda: subprocess.run(
        [sys.executable, os.path.join(HERE, "rtp_play.py"), env.stream_path(stream), str(env.VIDEO_PORT), "2",
         env.QUEST_HOST], capture_output=True, env={**os.environ, "KEEPAWAKE": "1"}))
    play.start()
    time.sleep(6)
    png = os.path.join(OUT, f"{label}-{os.path.splitext(stream)[0]}.png")
    with open(png, "wb") as f:
        subprocess.run([env.ADB, "-s", env.QUEST, "exec-out", "screencap", "-p"], stdout=f, check=True)
    play.join()
    log = q.adb("logcat", "-d", "-s", "VideoDecoder:D")
    fmt = [l for l in log.splitlines() if "Actual Width" in l or "OUTPUT_FORMAT_CHANGED" in l]
    with open(png[:-4] + "-format.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(fmt) + "\n")
    b = bands(png)
    ratio = b["red"][0] / b["green"][0] if b["green"][0] else float("nan")
    print(f"{label:10s} {stream:16s} green rows {b['green'][0]:3d} @{b['green'][1]:4d}  red rows {b['red'][0]:3d} "
          f"@{b['red'][1]:4d}  red/green {ratio:4.2f}  format lines {len(fmt)}", flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for s in sys.argv[2:]:
        check(sys.argv[1], s)
