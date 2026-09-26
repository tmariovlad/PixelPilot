"""Re-check the key conclusions on a clean stream (h265_720, few losses): no keys / upstream LL /
operating rate only / LL + operating rate. N shuffled rounds.
Usage: python3 quest_recheck.py [rounds=3] [stream=h265_720.rtp] > out/quest_recheck_<stream>.log"""
import random
import statistics
import sys

import quest_lever_test as t

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
STREAM = sys.argv[2] if len(sys.argv) > 2 else "h265_720.rtp"
CONFIGS = [
    ("no keys", {"low_latency_decoder": False, "dec_operating_rate": False}),
    ("LL (upstream)", {"low_latency_decoder": True, "dec_operating_rate": False}),
    ("OR only (Quest default)", {"low_latency_decoder": False, "dec_operating_rate": True}),
    ("LL + OR", {"low_latency_decoder": True, "dec_operating_rate": True}),
]
res = {n: [] for n, _ in CONFIGS}
for r in range(ROUNDS):
    order = CONFIGS[:]
    random.shuffle(order)
    for name, flags in order:
        _, d, _, _ = t.run(name, flags, STREAM, loops=1)
        if d >= 0:
            res[name].append(d)
print("\n=== recheck on %s (N=%d) ===" % (STREAM, ROUNDS), flush=True)
for n, _ in CONFIGS:
    v = res[n]
    if v:
        print(f"{n:28s} mean={statistics.mean(v):5.2f} min={min(v):5.2f} max={max(v):5.2f}", flush=True)
