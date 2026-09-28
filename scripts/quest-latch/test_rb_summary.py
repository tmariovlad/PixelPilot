"""Offline test for rb_summary.parse (no trace, no device): python3 test_rb_summary.py"""
import rb_summary

LATCH_OUT = """vsync callbacks=1080 period=8.3336 ms  interval jitter p95=41.0 us
video surface: SurfaceTexture-1-2345-0
TW pass start: phase after vsync             n=1079 mean=  3.10 p5=  2.90 p50=  3.10 p95=  3.40 max=  4.00 ms
TW pass interval                             n=2086 mean=  4.18 p5=  4.02 p50=  4.17 p95=  4.33 max=  4.58 ms
frame ready (queueBuffer) -> latch           n=1070 mean=  4.25 p5=  0.40 p50=  4.10 p95=  8.00 max=  9.10 ms
frames that missed a latch (wait > half a period): 49.0 %
decoded frames queued=1500 latched=1070 (never shown=430)
latch -> next vsync                          n=1075 mean=  5.20 p5=  5.00 p50=  5.20 p95=  5.50 max=  6.00 ms
"""
BQ_OUT = """decoder queueBuffer: 1500 in 9.0s = 166.7/s ; compositor latched 1070 = 118.9/s
BufferQueue queued-depth counter (SurfaceTexture-1-2345-0): mean=0.40 max=1
"""


def test_parse_full():
    r = rb_summary.parse(LATCH_OUT, BQ_OUT)
    assert abs(r["vsync_period_ms"] - 8.3336) < 1e-9
    assert abs(r["panel_hz"] - 1000 / 8.3336) < 1e-6
    assert r["ready_to_latch_mean_ms"] == 4.25 and r["ready_to_latch_p50_ms"] == 4.10
    assert r["ready_to_latch_p95_ms"] == 8.00
    assert r["latch_to_vsync_mean_ms"] == 5.20
    assert r["tw_pass_interval_p50_ms"] == 4.17
    assert r["queued"] == 1500 and r["latched"] == 1070 and r["never_shown"] == 430
    assert r["decoder_fps"] == 166.7 and r["latch_fps"] == 118.9
    assert r["bq_depth_mean"] == 0.40 and r["bq_depth_max"] == 1


def test_parse_missing_lines_gives_none():
    r = rb_summary.parse("no vsync callbacks in this trace: vsync-phase lines skipped\n", "")
    assert r["vsync_period_ms"] is None and r["panel_hz"] is None
    assert r["ready_to_latch_mean_ms"] is None and r["queued"] is None and r["bq_depth_max"] is None
    assert r["tw_pass_interval_p50_ms"] is None


if __name__ == "__main__":
    test_parse_full()
    test_parse_missing_lines_gives_none()
    print("ok")
