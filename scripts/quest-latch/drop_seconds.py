"""Does the loss follow the air's own input drops? Per air second of the guarded step windows, this splits the radio's
post-FEC loss (wfb-ng "PKT_LOST <n>", one line per unrecoverable block), the app's key-frame requests (PPXR_STATS
idrok + idrfail, a rate over the 2 s before each sample) and the IDR frames the air sent (PPXR_STATS idr) into the
seconds in which the air's wfb_tx dropped input packets (an --air-drop-seconds file, as for loss_bursts.py) and the rest.

Air input drops never enter FEC, so they show up as RTP holes (loss_bursts.py) but not as PKT_LOST. Equal PKT_LOST rates
in both classes mean the radio is the same in the drop seconds, and the extra holes there are the air's own drops.

Usage: python3 drop_seconds.py qtx_<label>.raw.txt steps.txt air-drop-seconds.txt --air-offset-s S [--guard-s 4]
"""
import argparse
import re

_KV = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?)")


def step_seconds(starts, end, guard_s):
    """Whole air seconds strictly inside each guarded step window [start + guard, next start or end)."""
    bounds = list(starts) + [end]
    return [s for lo, hi in zip(bounds, bounds[1:]) for s in range(int(lo + guard_s) + 1, int(hi))]


def parse_logcat(lines, offset_s):
    """Quest logcat lines (-v epoch) -> ({air s: PKT_LOST packets}, {air s: PKT_LOST events}, {air s: IDR requests},
    {air s: IDR frames}). A stats rate covers the 2 s before its sample and counts once in each of those seconds."""
    lost, events, idr_req, idr_frames = {}, {}, {}, {}
    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            t = float(parts[0]) - offset_s
        except ValueError:
            continue
        if "PKT_LOST" in line:
            s = int(t)
            lost[s] = lost.get(s, 0) + int(line.rstrip().split("\t")[-1])
            events[s] = events.get(s, 0) + 1
        elif "PPXR_STATS" in line:
            f = dict(_KV.findall(line))
            rate = float(f.get("idrok", 0)) + float(f.get("idrfail", 0))
            frames = float(f.get("idr", 0))
            for s in (int(t) - 2, int(t) - 1):
                idr_req[s] = idr_req.get(s, 0) + rate
                idr_frames[s] = idr_frames.get(s, 0) + frames
    return lost, events, idr_req, idr_frames


def split(counts, seconds, drop):
    """{second: count} over the given seconds -> {"drop"|"clean": (seconds, total, per second)}."""
    out = {}
    for name, keep in (("drop", lambda s: s in drop), ("clean", lambda s: s not in drop)):
        ss = [s for s in seconds if keep(s)]
        total = sum(counts.get(s, 0) for s in ss)
        out[name] = (len(ss), total, total / len(ss) if ss else 0.0)
    return out


def read_air_steps(path):
    """Air step log -> (step starts, END), both in air epoch seconds."""
    starts, end = [], None
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) < 2 or line.startswith("#") or "ERR" in p or p[1] == "PRE":
            continue
        if p[1] == "END":
            end = float(p[0])
        else:
            starts.append(float(p[0]))
    return sorted(starts), end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logcat")
    ap.add_argument("steps")
    ap.add_argument("air_drop_seconds")
    ap.add_argument("--air-offset-s", type=float, required=True)
    ap.add_argument("--guard-s", type=float, default=4.0)
    a = ap.parse_args()
    drop = {int(float(l.split()[0])) for l in open(a.air_drop_seconds) if l.strip() and not l.startswith("#")}
    starts, end = read_air_steps(a.steps)
    seconds = step_seconds(starts, end, a.guard_s)
    with open(a.logcat, encoding="utf-8", errors="ignore") as fh:
        lost, events, idr_req, idr_frames = parse_logcat(fh, a.air_offset_s)
    print(f"{'':7s}{'seconds':>8s}{'PKT_LOST':>10s}{'/s':>7s}{'events':>8s}{'/s':>7s}{'IDR req':>9s}{'/s':>7s}{'IDR fr':>8s}{'/s':>7s}")
    for name in ("drop", "clean"):
        n, l, lr = split(lost, seconds, drop)[name]
        _, e, er = split(events, seconds, drop)[name]
        _, r, rr = split(idr_req, seconds, drop)[name]
        _, fr, frr = split(idr_frames, seconds, drop)[name]
        print(f"{name:7s}{n:8d}{l:10d}{lr:7.2f}{e:8d}{er:7.2f}{r:9.1f}{rr:7.2f}{fr:8.1f}{frr:7.2f}")


if __name__ == "__main__":
    main()
