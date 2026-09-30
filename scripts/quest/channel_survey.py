"""The pre-flight channel survey's result from a capture: PPXR_SURVEY lines -> a per-channel table and a bar graph.

Usage: python3 channel_survey.py <detached capture> [--png out.png]

The app logs one PPXR_SURVEY line per event, as devourer chanmig JSONL (app/wfbngrtl8812/.../ChannelSurvey.h, run by
WfbngLink::run_survey when the survey_on_start pref is on; docs/xr/channel-survey-design.md):
  survey.start    plan, channels, rounds, dwell_ms, link
  survey.dwell    one per dwell: chan "5:<primary>/20", observe_ms, oth_air_us (other traffic), dvr_air_us (our own
                  link), nhm_busy (% of NHM samples above the lowest bucket), frames, rssi_max (raw), ...
  channel.ranking devourer RecommendEngine's scores, best first: c<i> = "<chan> q=<0|1> score= occ= rej="
  survey.result   recommended (0 = none qualified), link, dwells, outcome (completed / aborted /
                  retune_back_failed: no uplink, the link restarts), aborted
The score and the recommendation are computed on the Quest (one implementation); this script only reads and draws.
Bar = foreign airtime %, the share of the dwell other transmitters used (our own link is shown apart, not counted).
"""
import argparse
import json
import re

TAG = " PPXR_SURVEY: "
RSSI_DBM_OFFSET = 110          # devourer raw -> dBm (devourer src/LinkHealth.cpp:8)
BAR = 30                       # characters for 100 %
_RANK = re.compile(r"5:(\d+)/\d+ q=(\d) score=([\d.]+) occ=([\d.]+) rej=(\d+)")


def _chan(token):
    return int(token.split(":")[1].split("/")[0])


def parse(lines):
    """{"start", "dwells", "ranking", "result"} from the capture's PPXR_SURVEY lines (the last run wins)."""
    run = {"start": None, "dwells": [], "ranking": [], "result": None}
    for line in lines:
        i = line.find(TAG)
        if i < 0:
            continue
        try:
            ev = json.loads(line[i + len(TAG):])
        except ValueError:
            continue
        kind = ev.get("ev")
        if kind == "survey.start":
            run = {"start": ev, "dwells": [], "ranking": [], "result": None}
        elif kind == "survey.dwell":
            run["dwells"].append(ev)
        elif kind == "channel.ranking":
            run["ranking"] = [{"chan": int(m[1]), "qualified": m[2] == "1", "score": float(m[3]),
                               "occ": float(m[4]), "rej": int(m[5])}
                              for m in (_RANK.match(ev[f"c{k}"]) for k in range(int(ev.get("n", 0)))
                                        if f"c{k}" in ev) if m]
        elif kind == "survey.result":
            run["result"] = ev
    return run


def per_channel(dwells):
    """{primary: {dwells, foreign_pct, own_pct, nhm_busy, rssi_max_dbm, frames}}; percentages are means over dwells."""
    acc = {}
    for d in dwells:
        c = acc.setdefault(_chan(d["chan"]), {"dwells": 0, "foreign": [], "own": [], "nhm": [], "rssi": [], "frames": 0})
        obs_us = max(1, int(d.get("observe_ms") or 0) * 1000)
        c["dwells"] += 1
        c["foreign"].append(100.0 * int(d.get("oth_air_us") or 0) / obs_us)
        c["own"].append(100.0 * int(d.get("dvr_air_us") or 0) / obs_us)
        if d.get("nhm_busy") is not None:
            c["nhm"].append(float(d["nhm_busy"]))
        if int(d.get("frames") or 0) > 0:
            c["rssi"].append(int(d["rssi_max"]) - RSSI_DBM_OFFSET)
        c["frames"] += int(d.get("frames") or 0)
    mean = lambda v: sum(v) / len(v) if v else None
    return {ch: {"dwells": c["dwells"], "foreign_pct": mean(c["foreign"]), "own_pct": mean(c["own"]),
                 "nhm_busy": mean(c["nhm"]), "rssi_max_dbm": max(c["rssi"]) if c["rssi"] else None,
                 "frames": c["frames"]}
            for ch, c in sorted(acc.items())}


def chart(chans, run):
    """One text row per channel: a bar of foreign airtime, NHM busy, strongest foreign signal, the engine's score,
    and markers for the link channel and the recommendation."""
    link = (run.get("start") or {}).get("link") or (run.get("result") or {}).get("link")
    rec = (run.get("result") or {}).get("recommended")
    score = {r["chan"]: r for r in run.get("ranking") or []}
    rows = []
    for ch, c in chans.items():
        pct = c["foreign_pct"] or 0.0
        bar = "#" * int(round(pct / 100 * BAR))
        nhm = f"NHM {c['nhm_busy']:.0f}%" if c["nhm_busy"] is not None else "NHM -"
        rssi = f"{c['rssi_max_dbm']} dBm" if c["rssi_max_dbm"] is not None else "no frames"
        s = score.get(ch)
        verdict = (f"score {s['score']:.2f}" + ("" if s["qualified"] else " not qualified")) if s else "unscored"
        marks = (" (link, own video %.0f%%)" % (c["own_pct"] or 0) if ch == link else "") + \
                (" <- recommended" if ch == rec else "")
        rows.append(f"{ch:3d} |{bar:<{BAR}}| {pct:4.0f}%  {nhm:8s} {rssi:>10s}  {verdict}{marks}")
    return rows


def _png(chans, run, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rec = (run.get("result") or {}).get("recommended")
    xs = [str(c) for c in chans]
    ys = [c["foreign_pct"] or 0 for c in chans.values()]
    colors = ["tab:green" if int(x) == rec else "tab:blue" for x in xs]
    plt.figure(figsize=(8, 3.5))
    plt.bar(xs, ys, color=colors)
    plt.ylabel("foreign airtime %")
    plt.xlabel("channel (20 MHz)")
    plt.title("channel survey" + (f" - recommended {rec}" if rec else ""))
    plt.tight_layout()
    plt.savefig(path, dpi=120)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--png")
    a = ap.parse_args()
    with open(a.capture, encoding="utf-8", errors="replace") as fh:
        run = parse(fh)
    if not run["dwells"]:
        raise SystemExit("no PPXR_SURVEY dwell lines in the capture (was the survey_on_start pref on?)")
    chans = per_channel(run["dwells"])
    res = run["result"] or {}
    print(f"survey: {len(run['dwells'])} dwells, link {res.get('link')}, recommended {res.get('recommended') or 'none'}, "
          f"outcome {res.get('outcome', 'aborted' if res.get('aborted') else '?')}")
    print("bar = foreign airtime % (other transmitters; our own link shown apart)")
    for row in chart(chans, run):
        print(row)
    if a.png:
        _png(chans, run, a.png)
        print(f"png -> {a.png}")


if __name__ == "__main__":
    main()
