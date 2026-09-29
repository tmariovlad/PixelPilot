"""Offline checks of tsv_steps: rows of a probe TSV (t_mono_ms first) counted per air step and per value of one column.
Run: python3 test_tsv_steps.py"""

from tsv_steps import count_per_step, mono_to_pc_offset_ms


def test_the_mono_to_pc_offset_comes_from_an_event_line_and_the_quest_minus_pc():
    line = "1790645842.885 1 2 I PPXR_EVENT: t_mono_ms=211186093 t_wall_ms=1790645842885 code=IDR level=INFO"
    # Quest wall 1790645842885 at mono 211186093; the Quest is 1500 ms ahead of the PC
    assert mono_to_pc_offset_ms([line], quest_minus_pc_ms=1500.0) == 1790645842885 - 211186093 - 1500.0


def test_rows_are_counted_per_step_inside_the_guarded_windows():
    # steps (PC s) at 100 and 160, END 220, guard 5: windows [105, 155) and [165, 215)
    rows = [{"t_mono_ms": "110000", "class": "pre_fec", "gap": "3"},    # 110 s -> step 0
            {"t_mono_ms": "120000", "class": "post_fec", "gap": "2"},   # step 0
            {"t_mono_ms": "157000", "class": "post_fec", "gap": "9"},   # guard between steps
            {"t_mono_ms": "200000", "class": "post_fec", "gap": "4"}]   # step 1
    out = count_per_step(rows, [(100.0, "a"), (160.0, "b")], 220.0, 5.0, offset_ms=0.0, column="class", weight="gap")
    assert out == [("a", 50.0, {"pre_fec": (1, 3), "post_fec": (1, 2)}), ("b", 50.0, {"post_fec": (1, 4)})], out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
