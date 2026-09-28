"""One CSV row per refresh-bracket trace (scripts/quest/refresh_bracket.sh): panel rate actually run (vsync period),
decoded frame -> compositor latch wait, latch -> next vsync, frames never shown, buffer-queue depth.

Runs latch_analyze.py and ../quest/bq_stats.py on each trace and parses their text output (parse() is the tested
part: test_rb_summary.py).
Usage: python3 rb_summary.py out.csv <steps.txt> trace.pftrace ...   (steps.txt: the app's "requested X -> Y" line)
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUM = r"(-?[0-9.]+)"


def _stat(text, name):
    m = re.search(re.escape(name) + r"\s+n=\s*\d+\s+mean=\s*" + NUM + r"\s+p5=\s*" + NUM + r"\s+p50=\s*" + NUM
                  + r"\s+p95=\s*" + NUM, text)
    return tuple(float(g) for g in m.groups()) if m else (None, None, None, None)


def _one(pattern, text, cast=float):
    m = re.search(pattern, text)
    return tuple(cast(g) for g in m.groups()) if m else None


def parse(latch_out, bq_out):
    period = _one(r"vsync callbacks=\d+ period=" + NUM + " ms", latch_out)
    ready = _stat(latch_out, "frame ready (queueBuffer) -> latch")
    to_vsync = _stat(latch_out, "latch -> next vsync")
    tw_pass = _stat(latch_out, "TW pass interval")  # compositor cadence; present even without vsync callbacks
    counts = _one(r"decoded frames queued=(\d+) latched=(\d+) \(never shown=(-?\d+)\)", latch_out, int)
    rates = _one(r"= " + NUM + r"/s ; compositor latched \d+ = " + NUM + "/s", bq_out)
    depth = _one(r"queued-depth counter \([^)]*\): mean=" + NUM + " max=" + NUM, bq_out)
    return {
        "vsync_period_ms": period[0] if period else None,
        "panel_hz": 1000 / period[0] if period else None,
        "ready_to_latch_mean_ms": ready[0], "ready_to_latch_p50_ms": ready[2], "ready_to_latch_p95_ms": ready[3],
        "latch_to_vsync_mean_ms": to_vsync[0], "tw_pass_interval_p50_ms": tw_pass[2],
        "queued": counts[0] if counts else None, "latched": counts[1] if counts else None,
        "never_shown": counts[2] if counts else None,
        "decoder_fps": rates[0] if rates else None, "latch_fps": rates[1] if rates else None,
        "bq_depth_mean": depth[0] if depth else None, "bq_depth_max": int(depth[1]) if depth else None,
    }


def _run(script, trace):
    r = subprocess.run([sys.executable, str(script), str(trace)], capture_output=True, text=True)
    return r.stdout + r.stderr


def main(out_csv, steps_txt, traces):
    steps = {}
    for line in Path(steps_txt).read_text().splitlines():
        m = re.search(r"req=(\d+) app='([^']*)' trace=(\S+)", line)
        if m:
            steps[m.group(3)] = (int(m.group(1)), m.group(2))
    rows = []
    for t in traces:
        req, app = steps.get(Path(t).name, (None, ""))
        row = {"trace": Path(t).name, "requested_hz": req, "app_readback": app}
        row.update(parse(_run(HERE / "latch_analyze.py", t), _run(HERE.parent / "quest" / "bq_stats.py", t)))
        rows.append(row)
        print(row, flush=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
