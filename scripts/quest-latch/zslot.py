"""One table per arm for a -Z x payload slot (stock / -Z x 2400 / 3900 on q7, openipc-40 lever_z.sh), from one
detached Quest capture, its Perfetto trace and the air's logs. It computes nothing itself; each number comes from the
script that owns it:

- lnk50 lnk95 tot50 tot95 post (PPXR_STATS 2 s medians / loss %): the openipc repo's slot/ab_fit.py, OLS per arm vs
  --ref with a linear drift (primary) and a quadratic drift (sensitivity); '*' marks an arm where the two differ by
  more than the larger of their SEs. Also the arm's own mean of the samples ab_fit used.
- last, last95, spread (frame complete, ms above the ref's drift line; first -> last packet): ab_segments.analyze.
- FEC-recovered frames: their share of all frames, their own capture -> last (mean / p95, ms above the same line), the
  share of them whose marker waited for the next frame's packets, and the held frames: zflush.rows (PPXR_RELEASE).
- FRAME_FLUSH fillers/s per arm (the air's wfbtx.log with -Z): zflush.air_per_step.

Usage:
  python3 zslot.py trace.pftrace steps.txt qtx_<label>.raw.txt --air-log ab_<label>.log --ref p2400 \\
      --quest-minus-air-s S [--guard-s 15] [--fps-min 0] [--wfbtx-log wfbtx.log --air-mono-minus-epoch-ms M]
      [--also trace_b.pftrace qtx_<label>_b.raw.txt --quest-minus-air-s Sa Sb]
--also adds a second (third ...) capture of the same run (the Quest caps one at 30 min): its PPXR_STATS go to ab_fit
with their own offset (ab_fit.read_quests), its packets join the first trace's into one frame stream (same Quest boot,
merge_traces), its PPXR_RELEASE lines join the flags.
steps.txt = the air step log (ab_segments.read_steps); --air-log = ab_run.sh's log (SET/S/END, ab_fit.read_air_log)
or its Quest-side stand-in (quest_airlog.py); S = Quest epoch minus air epoch, used for both (ab_segments'
--air-offset-s is the same number).
"""
import argparse
import importlib
import os
import statistics as st
import sys

import ab_segments
import zflush
from air_drops import parse_intervals

AB_FIT_DIR = "C:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/air-latency-30pct-2026-09-30/slot"
FIT_KEYS = ("lnk50", "lnk95", "tot50", "tot95", "post")


def load_ab_fit(path=None):
    """The openipc repo's ab_fit module (numpy), imported from its slot directory."""
    path = path or os.environ.get("AB_FIT_DIR", AB_FIT_DIR)
    if not os.path.isfile(os.path.join(path, "ab_fit.py")):
        raise SystemExit(f"ab_fit.py not found in {path} (--ab-fit-dir or AB_FIT_DIR)")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("ab_fit")


SAME_BOOT_NS = 1e9   # two traces of one Quest boot: REALTIME - trace clock agree to well within this


def merge_traces(loaded):
    """[(pkts, ready, realtime_minus_trace)] of several traces of one run (the Quest caps a capture at 30 min) -> one
    packet stream, so frames_from_packets groups and unwraps the RTP timestamps across the join. The traces must share
    the trace clock (one Quest boot); the first trace's REALTIME offset is used."""
    rt0 = loaded[0][2]
    for _, _, rt in loaded[1:]:
        if abs(rt - rt0) > SAME_BOOT_NS:
            raise SystemExit(f"traces from different Quest boots (REALTIME - trace differs by {(rt - rt0) / 1e9:.1f} s)")
    pkts = sorted(p for pk, _, _ in loaded for p in pk)
    ready = sorted(r for _, rd, _ in loaded for r in rd)
    return pkts, ready, rt0


def offsets(values, n):
    """--quest-minus-air-s: one value for every capture, or one per capture (as ab_fit's --quest)."""
    if len(values) == 1:
        return values * n
    if len(values) != n:
        raise SystemExit(f"--quest-minus-air-s: give 1 value or one per capture ({n}), got {len(values)}")
    return list(values)


def disagree(lin, quad):
    """(beta, se) of the linear and the quadratic fit: apart by more than the larger SE."""
    return abs(lin[0] - quad[0]) > max(lin[1], quad[1])


def fits(rows, steps, ref, ab_fit=None):
    """{arm: {"lin": (b, se), "quad": (b, se) or absent, "disagree": bool}} for every arm but ref."""
    ab_fit = ab_fit or load_ab_fit()
    lin = ab_fit.fit(rows, steps, ref, False)["effects"]
    try:
        quad = ab_fit.fit(rows, steps, ref, True)["effects"]
    except (ValueError, ArithmeticError):
        quad = {}
    out = {}
    for arm, b in lin.items():
        out[arm] = {"lin": tuple(b)}
        if arm in quad:
            out[arm]["quad"] = tuple(quad[arm])
            out[arm]["disagree"] = disagree(out[arm]["lin"], out[arm]["quad"])
        else:
            out[arm]["disagree"] = False
    return out


def arm_means(rows, steps):
    """{arm: mean of the samples ab_fit used in that arm's blocks}."""
    by = {}
    for _, v, i in rows:
        by.setdefault(steps[i].label, []).append(v)
    return {arm: st.mean(v) for arm, v in by.items()}


def recovered(zrow):
    """The FEC-recovered frames of one zflush.rows state: share of all frames, their own wait, waited_next, held n."""
    cl = zrow["recovered"]["capture_last"]
    held = zrow["held"]["capture_last"]
    return {"share": (cl["n"] if cl else 0) / zrow["frames"],
            "wait_mean": cl["mean"] if cl else None, "wait_p95": cl["p95"] if cl else None,
            "waited_next": zrow["waited_next_of_recovered"], "held": held["n"] if held else 0}


def flush_rate(s):
    """FRAME_FLUSH fillers per second of air interval time, or None without any."""
    if not s or not s.get("ms"):
        return None
    return s["fillers"] / (s["ms"] / 1000.0)


def _f(x, fmt="{:+.3f}"):
    return "-" if x is None else fmt.format(x)


def render_fits(fits_by_key, arms, ref):
    """One line per key: per arm the linear effect ± se, then the quadratic, '*' where they disagree."""
    lines = [f"{'vs ' + ref:8s}" + "".join(f"{arm:>34s}" for arm in arms if arm != ref),
             f"{'':8s}" + "".join(f"{'linear':>17s}{'quadratic':>17s}" for arm in arms if arm != ref)]
    for key, per_arm in fits_by_key.items():
        cells = []
        for arm in arms:
            if arm == ref:
                continue
            e = per_arm.get(arm)
            if e is None:
                cells.append(f"{'-':>17s}{'-':>17s}")
                continue
            lin = f"{e['lin'][0]:+.3f}±{e['lin'][1]:.3f}"
            quad = f"{e['quad'][0]:+.3f}±{e['quad'][1]:.3f}" if "quad" in e else "-"
            cells.append(f"{lin:>17s}{quad + ('*' if e['disagree'] else ' '):>17s}")
        lines.append(f"{key:8s}" + "".join(cells))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("steps")
    ap.add_argument("capture")
    ap.add_argument("--air-log", required=True, help="ab_run.sh log (SET/S/END) or quest_airlog.py's stand-in")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--quest-minus-air-s", type=float, nargs="+", required=True,
                    help="Quest epoch - air epoch: one value, or one per capture (the first, then each --also)")
    ap.add_argument("--also", nargs=2, action="append", default=[], metavar=("TRACE", "CAPTURE"),
                    help="another capture of the same run (trace + detached logcat)")
    ap.add_argument("--guard-s", type=float, default=15.0)
    ap.add_argument("--end-guard-s", type=float, default=2.0, help="ab_fit's end guard")
    ap.add_argument("--fps-min", type=float, default=0.0, help="ab_fit voids a block with an S sample below this")
    ap.add_argument("--wfbtx-log", help="the air's /tmp/wfbtx.log (FRAME_FLUSH, -Z)")
    ap.add_argument("--air-mono-minus-epoch-ms", type=float)
    ap.add_argument("--ab-fit-dir")
    a = ap.parse_args()
    ab_fit = load_ab_fit(a.ab_fit_dir)
    guard = a.guard_s * 1e9
    traces = [a.trace] + [t for t, _ in a.also]
    captures = [a.capture] + [c for _, c in a.also]
    offs = offsets(a.quest_minus_air_s, len(captures))

    # ab_fit on PPXR_STATS
    blocks = ab_fit.read_air_log(a.air_log, a.fps_min)
    fit_by_key, means_by_key = {}, {}
    for key in FIT_KEYS:
        rows = ab_fit.assign(ab_fit.read_quests(captures, key, offs, ap), blocks, a.guard_s, a.end_guard_s)
        fit_by_key[key] = fits(rows, blocks, a.ref, ab_fit)
        means_by_key[key] = arm_means(rows, blocks)
    arms = list(dict.fromkeys(b.label for b in blocks))

    # the trace: frames, one drift line (the ref's), ab_segments per state and zflush per state
    pkts, ready, rt = merge_traces([ab_segments.load_trace(t) for t in traces])
    frames, _ = ab_segments.frames_from_packets(pkts, ready)
    steps, end = ab_segments.read_steps(a.steps, offs[0], rt)
    end = min(pkts[-1][0], end) if end else pkts[-1][0]
    _, per_state, _ = ab_segments.analyze(frames, steps, end, guard, a.ref, pkts)
    seg = dict(per_state)
    slope, icpt = ab_segments.baseline_line(frames, steps, end, guard, a.ref)
    lines = []
    for c in captures:
        with open(c, encoding="utf-8", errors="replace") as fh:
            lines += fh.readlines()
    flags = zflush.frame_flags(lines)
    zrows = zflush.rows(frames, flags, steps, end, guard, lambda t: slope * t + icpt)
    flush = {}
    if a.wfbtx_log:
        if a.air_mono_minus_epoch_ms is None:
            raise SystemExit("--wfbtx-log needs --air-mono-minus-epoch-ms (air uptime ms - air epoch ms)")
        with open(a.wfbtx_log, encoding="utf-8", errors="replace") as fh:
            iv = parse_intervals(fh, "FRAME_FLUSH")
        to_trace = lambda air_ms: ((air_ms - a.air_mono_minus_epoch_ms) / 1000 + offs[0]) * 1e9 - rt
        flush = zflush.air_per_step(iv, to_trace, steps, end, guard)

    print(f"# zslot: {' + '.join(traces)} | captures {' + '.join(captures)} | steps {a.steps} | air log {a.air_log} | "
          f"ref {a.ref} | Quest-air {' / '.join(f'{o:+.4f}' for o in offs)} s | guard {a.guard_s:g} s | fps-min {a.fps_min:g}"
          f"{' | wfbtx ' + a.wfbtx_log if a.wfbtx_log else ' | no wfbtx log: FRAME_FLUSH not read'}")
    print(f"ab_fit: {len(blocks)} blocks, {sum(b.void for b in blocks)} void")
    print("\nper arm, own values (PPXR_STATS mean of the used 2 s samples; frame times ms above the ref's drift line)")
    hdr = (f"{'arm':8s}{'lnk50':>7s}{'lnk95':>7s}{'tot50':>7s}{'tot95':>7s}{'post%':>7s} |{'last':>7s}{'last95':>7s}"
           f"{'spread':>7s} |{'rec%':>6s}{'recW':>7s}{'recW95':>7s}{'wNext':>6s}{'held':>6s} |{'fill/s':>8s}")
    print(hdr)
    for arm in arms:
        s = seg.get(arm)
        r = recovered(zrows[arm]) if arm in zrows else None
        m = lambda k: means_by_key[k].get(arm)
        print(f"{arm:8s}" + "".join(_f(m(k), "{:7.2f}") for k in FIT_KEYS[:4]) + _f(m("post"), "{:7.3f}")
              + " |" + (f"{s['last_ms']:7.2f}{s['last_p95_ms']:7.2f}{s['spread_ms']:7.2f}" if s else f"{'-':>21s}")
              + " |" + (f"{100 * r['share']:6.1f}" + _f(r["wait_mean"], "{:7.2f}") + _f(r["wait_p95"], "{:7.2f}")
                        + _f(r["waited_next"], "{:6.3f}") + f"{r['held']:6d}" if r else f"{'-':>32s}")
              + " |" + _f(flush_rate(flush.get(arm)), "{:8.1f}"))
    print(f"\nab_fit effects vs {a.ref} (OLS; '*' = linear and quadratic differ by more than the larger SE)")
    print(render_fits(fit_by_key, arms, a.ref))
    ref = seg.get(a.ref)
    if ref:
        print(f"\nframe complete vs {a.ref} (ab_segments): "
              + "  ".join(f"{arm} Δlast {seg[arm]['last_ms'] - ref['last_ms']:+.2f} Δlast95 "
                          f"{seg[arm]['last_p95_ms'] - ref['last_p95_ms']:+.2f}" for arm in arms
                          if arm != a.ref and arm in seg))


if __name__ == "__main__":
    main()
