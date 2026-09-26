"""One-off: turn the quest_recheck.py logs (out/quest_recheck_h264.log, out/quest_recheck_h265_1080.log)
into a measurements CSV.
Usage: python3 mkcsv.py [log_dir=out/] [csv_dir=out/]"""
import re, sys
import quest_env as env
S = sys.argv[1] if len(sys.argv) > 1 else env.OUT_DIR
R = sys.argv[2] if len(sys.argv) > 2 else env.OUT_DIR
rows = ["stream,config,keys,decode_ms,frames"]
for stream, log in [("h264_720", "quest_recheck_h264.log"), ("h265_1080", "quest_recheck_h265_1080.log")]:
    for line in open(f"{S}/{log}", encoding="utf-8"):
        m = re.match(r"(.+?)\s+comp=\S+\s+keys=(\S+)\s+frames=\s*(\d+)\s+decode_ms=\s*([0-9.]+)", line)
        if m:
            rows.append(f"{stream},{m.group(1).strip()},{m.group(2)},{m.group(4)},{m.group(3)}")
open(f"{R}/measurements-2026-09-26-quest2-lever-recheck.csv", "w", newline="\n").write("\n".join(rows) + "\n")
print(len(rows) - 1, "rows")
