"""Decode time on the Quest per stream (codec x resolution) and decoder component, Quest defaults
(operating rate only). N shuffled rounds -> out/quest_codecs.csv + summary.
Usage: python3 quest_codec_matrix.py [rounds=3]   (needs streams/{h264,h265}_{540,720,1080}.rtp: gen_all.sh)"""
import csv
import random
import statistics
import sys

import quest_env as env
import quest_lever_test as t

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = env.out_path("quest_codecs.csv")
COMPONENTS = {"h265": ["", "c2.qti.hevc.decoder"], "h264": ["", "c2.qti.avc.decoder"]}
CONFIGS = []
for codec in ("h264", "h265"):
    for res in ("540", "720", "1080"):
        for comp in COMPONENTS[codec]:
            label = f"{codec} {res}p {comp or 'default'}"
            CONFIGS.append((label, f"{codec}_{res}.rtp", {"dec_component": comp} if comp else {}))

rows = []
for r in range(ROUNDS):
    order = CONFIGS[:]
    random.shuffle(order)
    for label, stream, flags in order:
        _, decode, frames, keys = t.run(label, flags, stream, loops=1)
        rows.append({"round": r, "config": label, "applied": keys, "decode_ms": round(decode, 3), "frames": frames})
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["round", "config", "applied", "decode_ms", "frames"])
            w.writeheader()
            w.writerows(rows)

print("\n=== summary (N=%d rounds, shuffled) ===" % ROUNDS, flush=True)
for label, _, _ in CONFIGS:
    v = [x["decode_ms"] for x in rows if x["config"] == label and x["decode_ms"] >= 0]
    fr = [x["frames"] for x in rows if x["config"] == label]
    ap = sorted({x["applied"] for x in rows if x["config"] == label})
    if v:
        print(f"{label:38s} mean={statistics.mean(v):6.2f} min={min(v):6.2f} max={max(v):6.2f} frames={fr} {ap}", flush=True)
    else:
        print(f"{label:38s} no decode data {ap}", flush=True)
