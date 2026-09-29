"""Offline checks of drop_seconds: per air second of the guarded step windows, the radio's post-FEC loss (wfb PKT_LOST)
and the app's IDR requests, split into the seconds in which the air's wfb_tx dropped input packets vs the rest.
Run: python3 test_drop_seconds.py"""

from drop_seconds import parse_logcat, per_step, split, step_seconds


def test_step_seconds_are_the_whole_seconds_inside_the_guarded_windows_of_ab_segments():
    # steps at 100 and 120, END 135, guard 4: ab_segments.step_window guards both ends -> [104, 116) and [124, 131)
    assert step_seconds([100.0, 120.0], 135.0, 4) == list(range(104, 116)) + list(range(124, 131))
    # a fractional start: [100.5 + 4, 110.2 - 4) holds whole seconds 105 only
    assert step_seconds([100.5], 110.2, 4) == [105]


def test_logcat_lines_become_per_second_counts_on_the_air_clock():
    lines = [
        "         1000.500 1 2 I wfb-ng  : PKT_LOST\t3",
        "         1001.200 1 2 I wfb-ng  : PKT_LOST\t1",
        "         1004.000 1 2 I PPXR_STATS: t=1 idrok=1.00 idrfail=0.50 idr=- kb=14",
        "         1006.000 1 2 I PPXR_STATS: t=2 idrok=0.00 idrfail=0.00 idr=2.50 kb=14",
    ]
    lost, events, idr_req, idr_frames = parse_logcat(lines, offset_s=0.5)
    assert lost == {1000: 4} and events == {1000: 2}, (lost, events)
    # a stats sample at air 1003.5 is a 2 s rate: 1.5 requests/s in air seconds 1001 and 1002
    assert idr_req == {1001: 1.5, 1002: 1.5, 1003: 0.0, 1004: 0.0}, idr_req
    # idr = IDR frames per second from the air; "-" (no sidecar data) counts as none
    assert idr_frames == {1001: 0.0, 1002: 0.0, 1003: 2.5, 1004: 2.5}, idr_frames


def test_split_gives_rates_per_class_of_second():
    r = split({10: 4, 11: 2, 12: 0}, [10, 11, 12, 13], {10})
    assert r["drop"] == (1, 4, 4.0) and r["clean"] == (3, 2, 2 / 3), r


def test_per_step_rates_use_each_steps_own_guarded_seconds():
    # steps at 100 and 120, END 135, guard 4: step 0 has seconds 104..115 (12), step 1 has 124..130 (7)
    counts = {104: 6, 115: 6, 118: 99, 127: 7}
    assert per_step(counts, [100.0, 120.0], 135.0, 4) == [1.0, 1.0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
