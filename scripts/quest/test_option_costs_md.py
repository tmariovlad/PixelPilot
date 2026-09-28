"""Offline checks of option_costs_md.py: the doc matches the JSON, and the row format. Run: python3 test_option_costs_md.py"""
import subprocess
import sys

import option_costs_md as m


def test_doc_is_in_sync_with_the_json():
    r = subprocess.run([sys.executable, m.__file__, "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_on_off_values_and_delta_render():
    o = {"id": "lever.fif", "label": "FIF", "key": "feed_incomplete_frames", "tag": "PROVEN",
         "source": "docs/xr/link-envelope.md", "measured": "2026-09-29", "note": "smears on loss",
         "costs": {"fps": {"off": 84.0, "on": 89.5}, "delta_ms": {"mean": 0.1, "vs": "lever.fif.off"}}}
    r = m.row(o)
    assert "84 → 89.5" in r and "Δ +0.1 ms" in r and "smears on loss" in r and "[PROVEN]" in r, r


def test_missing_values_stay_empty():
    o = {"id": "mcs.m2", "label": "MCS2", "key": "m2", "tag": "PROVEN", "source": "x", "measured": "2026-09-27",
         "costs": {"post_fec_pct": 0.1}}
    cells = m.row(o).split(" | ")
    assert cells[4] == "" and cells[5] == "" and cells[6] == "0.1 %", cells


def test_ranges_render_as_spread():
    o = {"id": "mode.hd", "label": "HD", "key": "hd", "tag": "INFERRED", "source": "x", "measured": "2026-09-27",
         "costs": {"g2g_ms": [46.6, 51.9], "fps": {"off": [82.4, 84.1], "on": 89.5},
                   "delta_ms": {"mean": [-3.0, -2.3], "p95": 1.9, "vs": "bitrate.8000"}}}
    r = m.row(o)
    assert "G2G 46.6…51.9 ms" in r and "82.4…84.1 → 89.5" in r and "Δ -3…-2.3 (p95 1.9) ms" in r, r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
