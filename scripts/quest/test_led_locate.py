"""Offline checks of led_locate.py (where the rig's flashing LED sits in the Quest's video layer, from a burst of
screencaps; numbers only). Run: python3 test_led_locate.py"""
import numpy as np

import led_locate as ll

W, H = 400, 200                          # one screencap, both eyes side by side
BOX = (40, 30, 160, 120)                 # the video layer in the left eye: x0, y0, x1, y1 (exclusive)
PANEL = (70, 130, 130, 160)              # the stats panel under it, half the width


def frame(led_on, led_xy=(100, 60), seed=0):
    rng = np.random.default_rng(seed)
    a = np.zeros((H, W, 3), dtype=np.uint8)                        # compositor background: exactly black
    x0, y0, x1, y1 = BOX
    a[y0:y1, x0:x1] = rng.integers(3, 9, size=(y1 - y0, x1 - x0, 1))  # a dark room: encoder noise only
    px0, py0, px1, py1 = PANEL
    a[py0:py1, px0:px1] = 200                                       # the panel's text, bright
    if led_on:
        x, y = led_xy
        a[y - 2:y + 3, x - 2:x + 3] = 250
    a[:, W // 2:] = a[:, :W // 2]                                   # the right eye mirrors the left
    return a


def test_layer_box_is_found_in_a_dark_room_and_the_panel_is_left_out():
    frames = [frame(i % 3 == 0, seed=i) for i in range(9)]
    assert ll.layer_box(frames) == BOX, ll.layer_box(frames)


def test_the_led_centre_is_given_as_fractions_of_the_video_frame():
    frames = [frame(i % 3 == 0, seed=i) for i in range(9)]
    r = ll.locate(frames)
    assert r["found"], r
    assert abs(r["col_frac"] - (100 - 40 + 0.5) / 120) < 0.01, r      # pixel centres
    assert abs(r["row_frac"] - (60 - 30 + 0.5) / 90) < 0.01, r
    assert r["inside_central_75"] is True


def test_an_led_near_the_top_edge_is_outside_the_central_75_percent():
    frames = [frame(i % 3 == 0, led_xy=(100, 34), seed=i) for i in range(9)]
    r = ll.locate(frames)
    assert r["found"], r
    assert r["row_frac"] < 0.125, r
    assert r["inside_central_75"] is False


def test_no_flash_in_the_burst_is_reported_not_guessed():
    frames = [frame(False, seed=i) for i in range(9)]
    r = ll.locate(frames)
    assert not r["found"], r


def test_geometry_box_keeps_the_reference_width_centre_and_pixel_scale():
    # LayerLayout.compute: width from the FOV only, the layer centred; height = width / aspect. The eye buffer's pixels
    # do not cover equal angles both ways, so the reference's pixel aspect (1226 x 963 for a 4:3 picture) is kept.
    ref = (237, 431, 1463, 1394)
    assert ll.box_from_geometry(ref, 4 / 3, ref_aspect=4 / 3) == ref
    x0, y0, x1, y1 = ll.box_from_geometry(ref, 16 / 9, ref_aspect=4 / 3)
    assert (x0, x1) == (237, 1463)
    assert abs((y0 + y1) / 2 - (431 + 1394) / 2) <= 0.5
    assert abs((y1 - y0) - 963 * (4 / 3) / (16 / 9)) <= 1.0


def test_an_auto_box_with_the_wrong_aspect_falls_back_to_the_geometry_box():
    frames = [frame(i % 3 == 0, seed=i) for i in range(9)]  # auto box 120 x 90 = 4:3
    box, how = ll.choose_box(frames, aspect=4 / 3, ref_box=(0, 0, 120, 90))
    assert (box, how) == (BOX, "auto"), (box, how)
    box, how = ll.choose_box(frames, aspect=16 / 9, ref_box=(40, 30, 160, 120))
    assert how == "geometry", how
    assert (box[0], box[2]) == (40, 160)


def test_an_explicit_box_wins():
    frames = [frame(i % 3 == 0, seed=i) for i in range(9)]
    r = ll.locate(frames, box=(40, 30, 160, 120))
    assert r["found"], r
    assert r["box_from"] == "given", r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
