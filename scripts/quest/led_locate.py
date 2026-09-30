"""Where does the G2G rig's flashing LED sit in the Quest's video picture? For latency-test's L1 plan ("the LED in the
picture, not at a cropped edge"), without putting any image in the analyst's context: a burst of screencaps catches the
LED both on and off, then
- the video layer's box in the left eye = where any frame of the burst is above near-black. The compositor's
  background is exactly black, while the video carries encoder noise even in a dark room (mean luma ~3-5 there). The
  stats panel under the layer is half its width, so a row threshold at 0.75 of the widest row leaves it out;
- the LED = the pixels whose on/off difference over the burst is at least half the largest one; its centroid is
  reported as row/column fractions of the video box (pixel centres), with the check "inside the central 75 %
  vertically" (rows 0.125-0.875).
Prints numbers only. The screencaps stay under the git-ignored out/led_locate/.

Usage: python3 led_locate.py capture <label> [--n 15] [--interval-s 0.7] [--aspect 16:9] [--box x0,y0,x1,y1]
       python3 led_locate.py analyze <dir of PNGs> [--aspect 16:9] ...   (Quest awake, video running, LED flashing)
With --aspect, an auto box whose aspect is off by > 5 % is replaced by the geometry box (REF_BOX's width and
centre, height = width / aspect).
"""
import glob
import os
import subprocess
import sys
import time

import numpy as np

MIN_DELTA = 60          # luma: a flash, not compression noise
NEAR_BLACK = 2          # luma above this in any frame = the video layer, not the compositor background


def _luma_left_eye(frames):
    a = np.stack([np.asarray(f)[..., :3].astype(np.int16).mean(axis=2) for f in frames])
    return a[:, :, : a.shape[2] // 2]


def _longest_run(idx):
    """[i0, i1) of the longest run of consecutive indices, or None."""
    if len(idx) == 0:
        return None
    best, start = (idx[0], idx[0] + 1), idx[0]
    for a, b in zip(idx, list(idx[1:]) + [None]):
        if b is None or b != a + 1:
            if a + 1 - start > best[1] - best[0]:
                best = (start, a + 1)
            start = b
    return best


def layer_box(frames):
    """(x0, y0, x1, y1), exclusive, of the video layer in the left eye; None if nothing is lit."""
    lum = _luma_left_eye(frames)
    mask = lum.max(axis=0) > NEAR_BLACK
    row = mask.mean(axis=1)
    if row.max() == 0:
        return None
    rows = _longest_run(list(np.where(row >= 0.75 * row.max())[0]))
    if rows is None:
        return None
    y0, y1 = rows
    col = mask[y0:y1].mean(axis=0)
    cols = _longest_run(list(np.where(col > 0.5)[0]))
    if cols is None:
        return None
    x0, x1 = cols
    return int(x0), int(y0), int(x1), int(y1)


# The 640x480 layer on APK 086a64aa at the default FOV, measured from a screencap (x 237-1462, y 431-1393 inclusive;
# docs/xr/data/quality-2026-09-30-086a-race.md) [INFERRED: one visual measurement]. The layer is head-locked, so its
# box in the eye buffer is fixed for a given FOV pref and aspect.
REF_BOX = (237, 431, 1463, 1394)
REF_ASPECT = 4 / 3          # the picture aspect REF_BOX was measured with (640x480)


def box_from_geometry(ref_box, aspect, ref_aspect=REF_ASPECT):
    """The layer box for another picture aspect. LayerLayout.compute takes the width from the FOV only and centres the
    layer, so the width and the centre stay, and the height scales by ref_aspect / aspect. The eye buffer's pixels do
    not cover equal angles horizontally and vertically, so the reference's pixel height, not its width / aspect, is the
    base (REF_BOX is 1226 x 963 px for a 4:3 picture, not 1226 x 920)."""
    x0, y0, x1, y1 = ref_box
    cy, h = (y0 + y1) / 2, (y1 - y0) * ref_aspect / aspect
    return x0, int(round(cy - h / 2)), x1, int(round(cy + h / 2))


def choose_box(frames, aspect=None, ref_box=REF_BOX, ref_aspect=REF_ASPECT):
    """(box, how): the auto box when its pixel aspect matches the geometry's within 5 % (or no aspect is given), else
    the geometry box. In a dark room the picture's black decodes to exactly 0, like the compositor background, and the
    auto box shrinks."""
    auto = layer_box(frames)
    if auto is not None and aspect is None:
        return auto, "auto (aspect unchecked)"
    geo = box_from_geometry(ref_box, aspect, ref_aspect)
    if auto is not None:
        a = (auto[2] - auto[0]) / (auto[3] - auto[1])
        g = (geo[2] - geo[0]) / (geo[3] - geo[1])
        if abs(a / g - 1) <= 0.05:
            return auto, "auto"
    return geo, "geometry"


def locate(frames, box=None, aspect=None, ref_box=REF_BOX):
    how = "given"
    if box is None:
        box, how = choose_box(frames, aspect, ref_box)
    if box is None:
        return {"found": False, "why": "no video layer in the screencaps"}
    x0, y0, x1, y1 = box
    lum = _luma_left_eye(frames)[:, y0:y1, x0:x1]
    delta = lum.max(axis=0) - lum.min(axis=0)
    peak = float(delta.max())
    if peak < MIN_DELTA:
        return {"found": False, "box": box, "box_from": how, "peak_delta": peak,
                "why": f"no flash caught (largest on/off difference {peak:.0f} < {MIN_DELTA})"}
    ys, xs = np.where(delta >= 0.5 * peak)
    col = (xs.mean() + 0.5) / (x1 - x0)
    row = (ys.mean() + 0.5) / (y1 - y0)
    return {"found": True, "box": box, "box_from": how, "peak_delta": peak, "blob_px": int(len(xs)),
            "blob_w_frac": float((xs.max() - xs.min() + 1) / (x1 - x0)),
            "blob_h_frac": float((ys.max() - ys.min() + 1) / (y1 - y0)),
            "col_frac": float(col), "row_frac": float(row), "inside_central_75": bool(0.125 <= row <= 0.875)}


def _load(paths):
    from PIL import Image
    return [np.asarray(Image.open(p).convert("RGB")) for p in paths]


def capture(label, n=15, interval_s=0.7):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import quest_env as env
    out = os.path.join(env.OUT_DIR, "led_locate", label)
    os.makedirs(out, exist_ok=True)
    paths = []
    for i in range(n):
        p = os.path.join(out, f"{i:02d}.png")
        with open(p, "wb") as fh:
            subprocess.run([env.ADB, "-s", env.QUEST, "exec-out", "screencap", "-p"], stdout=fh, check=True)
        paths.append(p)
        time.sleep(interval_s)
    return paths


def report(r):
    for k in ("found", "why", "box", "box_from", "peak_delta", "blob_px", "blob_w_frac", "blob_h_frac", "col_frac",
              "row_frac", "inside_central_75"):
        if k in r:
            v = r[k]
            print(f"{k:18s} {v:.3f}" if isinstance(v, float) else f"{k:18s} {v}")


def _ints(s):
    return tuple(int(x) for x in s.split(","))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Where the rig LED sits in the Quest's video picture (numbers only)")
    ap.add_argument("mode", choices=["capture", "analyze"])
    ap.add_argument("target", help="capture: a label; analyze: a directory of PNGs")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--interval-s", type=float, default=0.7)
    ap.add_argument("--aspect", default=None, help="the decoded picture's aspect, e.g. 16:9")
    ap.add_argument("--box", default=None, help="x0,y0,x1,y1 (exclusive) of the video layer, overrides the rest")
    ap.add_argument("--ref-box", default=",".join(map(str, REF_BOX)), help="a measured layer box for the geometry")
    a = ap.parse_args()
    aspect = None
    if a.aspect:
        w, h = a.aspect.split(":")
        aspect = float(w) / float(h)
    paths = capture(a.target, a.n, a.interval_s) if a.mode == "capture" else sorted(glob.glob(os.path.join(a.target, "*.png")))
    print(f"{len(paths)} screencaps")
    report(locate(_load(paths), _ints(a.box) if a.box else None, aspect, _ints(a.ref_box)))


if __name__ == "__main__":
    main()
