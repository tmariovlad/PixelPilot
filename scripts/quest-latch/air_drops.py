"""The air's wfb_tx injection drops, per log interval, and a circular-shift control for events joined to them.

The air's /tmp/wfbtx.log has one PKT line per interval (1 s): ts TAB PKT TAB
fec_timeouts:incoming:b_in:injected:b_inj:dropped:truncated (wfb-ng tx.cpp:729-730). The counters are per interval, so
a line covers (previous ts, ts]. `dropped` counts packets wfb_tx read but could not inject.

Clocks: a detached capture's logcat epoch (Quest wall) - quest_minus_pc_ms (ab_detached's meta) = PC wall;
+ air_minus_pc_ms = the air's get_time_ms, which is CLOCK_MONOTONIC (wfb-ng src/wifibroadcast.cpp:50-56), so
air_minus_pc_ms = (air uptime ms - air epoch ms, read together on the air) - (PC - air wall offset, ~+50..90 ms with
ntpd; slot_watch's AIR_CLOCK pc_minus_air_s). It is not the wall-clock offset alone.

shift_control(): the share of events that fall in drop intervals, against the same share with the drop series rotated
by every non-zero number of intervals (bounds kept, so coverage stays the same). An event type caused by the drops
beats the rotations; one unrelated to them sits at their mean. p_value = (1 + rotations with a share >= the real one) /
intervals. Used by fec_blocks.py and rtp_holes.py.
"""
from bisect import bisect_left

TAB = "\t"


def parse_intervals(lines, tag):
    """[(start_ms, end_ms, colon fields)] from the air's per-interval lines ts TAB <tag> TAB a:b:c..., in log order.
    The first line of a tag only opens the first interval."""
    out, prev = [], None
    for line in lines:
        f = line.rstrip("\r\n").split(TAB)
        if len(f) < 3 or f[1] != tag:
            continue
        ts = int(f[0])
        if prev is not None:
            out.append((prev, ts, f[2].split(":")))
        prev = ts
    return out


def parse_air_log(lines):
    """[(start_ms, end_ms, dropped)] from the air's wfb_tx PKT lines, in log order."""
    return [(s, e, int(c[5])) for s, e, c in parse_intervals(lines, "PKT") if len(c) >= 6]


def epoch_ms(line):
    """The logcat -v epoch time of a capture line in ms, or None."""
    head = line.split(None, 1)
    try:
        return float(head[0]) * 1000.0
    except (ValueError, IndexError):
        return None


def to_air_ms(wall_ms, quest_minus_pc_ms, air_minus_pc_ms):
    return wall_ms - quest_minus_pc_ms + air_minus_pc_ms


def _index(air_ms, intervals):
    i = bisect_left([end for _, end, _ in intervals], air_ms)
    if i < len(intervals) and intervals[i][0] < air_ms <= intervals[i][1]:
        return i
    return None


def mark(air_ms, intervals):
    """Y = the air dropped packets in the interval containing air_ms, N = it did not, ? = not covered."""
    i = _index(air_ms, intervals)
    if i is None:
        return "?"
    return "Y" if intervals[i][2] > 0 else "N"


def rotated(intervals, shift):
    """The same interval bounds with the dropped values moved by shift intervals (circularly)."""
    m = len(intervals)
    return [(s, e, intervals[(i + shift) % m][2]) for i, (s, e, _) in enumerate(intervals)]


def _share(idx, dropped):
    return sum(1 for i in idx if dropped[i] > 0) / len(idx)


def shift_control(air_times_ms, intervals):
    """The share of events in drop intervals vs every non-zero circular rotation of the drop series."""
    idx = [i for i in (_index(t, intervals) for t in air_times_ms) if i is not None]
    m = len(intervals)
    if not idx or m < 2:
        return {"covered": len(idx), "share": None, "shift_mean": None, "shift_p95": None, "shift_max": None,
                "p_value": None}
    dropped = [d for _, _, d in intervals]
    real = _share(idx, dropped)
    shifted = sorted(_share(idx, dropped[s:] + dropped[:s]) for s in range(1, m))
    return {
        "covered": len(idx),
        "share": real,
        "shift_mean": sum(shifted) / len(shifted),
        "shift_p95": shifted[min(len(shifted) - 1, int(0.95 * (len(shifted) - 1) + 0.5))],
        "shift_max": shifted[-1],
        "p_value": (1 + sum(1 for v in shifted if v >= real - 1e-12)) / m,
    }
