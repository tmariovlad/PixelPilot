"""PPXR_RTPHOLE lines (one per hole in the RTP sequence the Quest's video aggregator delivered) -> where the missing
packets were lost: before FEC (never entered the air's wfb_tx) or after it (on the radio).

Usage: python3 rtp_holes.py <detached logcat> [--tsv holes.tsv]
           [--air-log wfbtx.log --quest-minus-pc-ms Q --air-minus-pc-ms A]

The app logs gap (missing RTP packets) and slots_lost (the wfb data slots wfb-ng skipped between the two packets
around the hole, its PKT_LOST; FEC-only padding slots are not counted) per hole (app/wfbngrtl8812/.../RtpHoleProbe.h;
docs/xr/fec-block-probe.md §6). Capture DETACHED (scripts/quest/ab_detached.sh includes the tag), never streamed.

Classes (the only place they are defined):
  pre_fec  slots_lost = 0: the neighbours sat in contiguous wfb slots, so the packets never entered wfb_tx (air input)
  post_fec slots_lost >= gap: lost on the radio after FEC (more slots than packets = lost padding slots)
  mixed    0 < slots_lost < gap: at least gap - slots_lost never entered wfb_tx
  unknown  session=1: a new wfb session restarted wfb-ng's slot counter between the two packets
Packets: pre-FEC = gap - min(slots_lost, gap) (a lower bound), post-FEC = min(slots_lost, gap) (an upper bound),
unknown = the gap of session holes.

Air join (--air-log ... as fec_blocks.py, air_drops.py): marks each hole by whether the air's wfb_tx dropped packets
at injection in the same 1 s interval, and per class gives that share against every circular rotation of the air's
drop series (the control): pre-FEC holes caused by air drops beat the rotations, post-FEC ones should not.
"""
import sys
from collections import Counter

from air_drops import epoch_ms, mark, parse_air_log, shift_control, to_air_ms
from stats_log import parse_kv

TAG = " PPXR_RTPHOLE: "
TAB = "\t"
CLASSES = ("pre_fec", "post_fec", "mixed", "unknown")
GAP_BINS = (1, 2, 3, 4)   # a gap above the last bin is counted as "5+"


def classify(gap, slots_lost, session):
    if session:
        return "unknown"
    if slots_lost == 0:
        return "pre_fec"
    return "post_fec" if slots_lost >= gap else "mixed"


def split(gap, slots_lost, session):
    """(pre-FEC packets, post-FEC packets) of one hole; (0, 0) when its place is unknown."""
    if session:
        return 0, 0
    post = min(slots_lost, gap)
    return gap - post, post


def parse(line):
    i = line.find(TAG)
    if i < 0:
        return None
    kv = parse_kv(line[i + len(TAG):])
    if "gap" not in kv or "slots_lost" not in kv:
        return None
    h: dict = {k: int(kv[k]) for k in ("t_mono_ms", "rtp_prev", "rtp_next", "gap", "slots_lost")}
    h["session"] = kv.get("session") == "1"
    h["suppressed"] = int(kv.get("suppressed") or 0)
    h["class"] = classify(h["gap"], h["slots_lost"], h["session"])
    h["wall_ms"] = epoch_ms(line)
    return h


def _holes(lines):
    return [h for h in (parse(line) for line in lines) if h]


def join_air(lines, air_lines, quest_minus_pc_ms, air_minus_pc_ms):
    """The holes, each with air_ms and air_drop = Y / N / ? (air_drops.mark)."""
    intervals = parse_air_log(air_lines)
    out = []
    for h in _holes(lines):
        h["air_ms"] = None if h["wall_ms"] is None else to_air_ms(h["wall_ms"], quest_minus_pc_ms, air_minus_pc_ms)
        h["air_drop"] = "?" if h["air_ms"] is None else mark(h["air_ms"], intervals)
        out.append(h)
    return out


COLUMNS = ["t_mono_ms", "rtp_prev", "rtp_next", "gap", "slots_lost", "session", "class"]


def to_tsv(lines, air=None):
    cols = COLUMNS + (["air_drop"] if air else [])
    out = [TAB.join(cols)]
    for h in (join_air(lines, *air) if air else _holes(lines)):
        out.append(TAB.join(str(int(h[c]) if isinstance(h[c], bool) else h[c]) for c in cols))
    return "\n".join(out) + "\n"


def _gap_bin(gap):
    return gap if gap <= GAP_BINS[-1] else f"{GAP_BINS[-1] + 1}+"


def summarize(lines, air=None):
    """air = (air log lines, quest_minus_pc_ms, air_minus_pc_ms) adds the per-class air-drop share and its control."""
    holes = join_air(lines, *air) if air else _holes(lines)
    pre = sum(split(h["gap"], h["slots_lost"], h["session"])[0] for h in holes)
    post = sum(split(h["gap"], h["slots_lost"], h["session"])[1] for h in holes)
    summary = {
        "holes": len(holes),
        "holes_by_class": dict(Counter(h["class"] for h in holes)),
        "missing": sum(h["gap"] for h in holes),
        "missing_pre_fec": pre,
        "missing_post_fec": post,
        "missing_unknown": sum(h["gap"] for h in holes if h["session"]),
        "pre_fec_share": pre / (pre + post) if pre + post else None,
        "gap_by_class": {c: dict(Counter(_gap_bin(h["gap"]) for h in holes if h["class"] == c))
                         for c in CLASSES if any(h["class"] == c for h in holes)},
        "suppressed": sum(h["suppressed"] for h in holes),
    }
    if air:
        intervals = parse_air_log(air[0])
        summary["air"] = {c: shift_control([h["air_ms"] for h in holes if h["class"] == c and h["air_ms"] is not None],
                                           intervals)
                          for c in CLASSES}
    return summary


def _take(args, flag):
    i = args.index(flag)
    value = args[i + 1]
    del args[i:i + 2]
    return value


def main():
    args = sys.argv[1:]
    tsv = _take(args, "--tsv") if "--tsv" in args else None
    air = None
    if "--air-log" in args:
        with open(_take(args, "--air-log"), encoding="utf-8", errors="replace") as fh:
            air_lines = fh.readlines()
        air = (air_lines, float(_take(args, "--quest-minus-pc-ms")), float(_take(args, "--air-minus-pc-ms")))
    lines = []
    for path in args:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines.extend(fh)
    if tsv:
        with open(tsv, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(to_tsv(lines, air))
        print(f"holes -> {tsv}")
    for k, v in summarize(lines, air).items():
        if k == "air":
            for c, ctl in v.items():
                print(f"air_drop_share[{c}]: {ctl}")
        else:
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
