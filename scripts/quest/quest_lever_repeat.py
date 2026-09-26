"""N shuffled rounds of the decoder-key isolation matrix on the Quest.
Per config: mean/min/max steady-state decode time (queue -> output release). Raw rows -> CSV.
Usage: python3 quest_lever_repeat.py [rounds=3] [out.csv=out/quest_keys.csv]   (needs streams/h265_1slice.rtp)"""
import csv
import random
import statistics
import sys

import quest_env as env
import quest_lever_test as t

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = sys.argv[2] if len(sys.argv) > 2 else env.out_path("quest_keys.csv")
OFF = {"dec_operating_rate": False}
CONFIGS = [
    ("1 no keys", {"low_latency_decoder": False, **OFF}),
    ("2 LL all (upstream)", {**OFF}),
    ("3 LL minus priority", {**OFF, "dec_debug_key_mask": 0x1F}),
    ("4 priority only", {**OFF, "dec_debug_key_mask": 0x20}),
    ("5 low-latency (AOSP) only", {**OFF, "dec_debug_key_mask": 0x01}),
    ("6 qti low-latency only", {**OFF, "dec_debug_key_mask": 0x04}),
    ("7 vendor.low-latency only", {**OFF, "dec_debug_key_mask": 0x02}),
    ("8 operating rate only", {"low_latency_decoder": False, "dec_operating_rate": True}),
    ("9 LL-priority + OR (Quest default)", {"dec_operating_rate": True}),
]

rows = []
for r in range(ROUNDS):
    order = CONFIGS[:]
    random.shuffle(order)
    for name, flags in order:
        _, decode, frames, keys = t.run(name, flags, "h265_1slice.rtp")
        rows.append({"round": r, "config": name, "keys": keys, "decode_ms": round(decode, 3), "frames": frames})

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["round", "config", "keys", "decode_ms", "frames"])
    w.writeheader()
    w.writerows(rows)

print("\n=== summary (N=%d rounds, shuffled) ===" % ROUNDS, flush=True)
for name, _ in CONFIGS:
    v = [x["decode_ms"] for x in rows if x["config"] == name and x["decode_ms"] >= 0]
    keys = sorted({x["keys"] for x in rows if x["config"] == name})
    if v:
        print(f"{name:36s} decode_ms mean={statistics.mean(v):6.2f} min={min(v):6.2f} max={max(v):6.2f} keys={keys}",
              flush=True)
