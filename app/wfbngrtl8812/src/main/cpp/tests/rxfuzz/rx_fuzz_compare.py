"""Compare rx_fuzz outputs of two rx.cpp builds (stock, drain), case by case (tests/rxfuzz/run.sh)."""
import sys


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        head, deliv, tail = line.rstrip("\n").split("|")
        c = int(head.split()[1])
        pairs = [tuple(map(int, t.split("@"))) for t in deliv.split()]
        kv = dict(x.split("=") for x in tail.split())
        out[c] = (head.strip(), pairs, int(kv["lost"]), int(kv["rec"]))
    return out


s, d = load(sys.argv[1]), load(sys.argv[2])
same_ids = same_counters = earlier = later = cases_timing = tail_extra = 0
diffs = []
for c in sorted(s):
    hs, ps, ls, rs = s[c]
    hd, pd, ld, rd = d[c]
    ids_s, ids_d = [p for p, _ in ps], [p for p, _ in pd]
    ok_ids = ids_s == ids_d
    ok_cnt = (ls, rs) == (ld, rd)
    same_ids += ok_ids
    # stock a strict prefix of drain: stock holds the last in-order fragment of a finite stream (the bug)
    tail_extra += (not ok_ids) and len(ids_d) > len(ids_s) and ids_d[:len(ids_s)] == ids_s
    same_counters += ok_cnt
    if ok_ids:
        dt = [cd - cs for (_, cs), (_, cd) in zip(ps, pd)]
        earlier += sum(1 for x in dt if x < 0)
        later += sum(1 for x in dt if x > 0)
        cases_timing += any(x != 0 for x in dt)
    if not (ok_ids and ok_cnt) and len(diffs) < 5:
        diffs.append((c, hs, ids_s, ids_d, (ls, rs), (ld, rd)))
n = len(s)
print(f"cases {n}: delivered ids identical {same_ids}, lost/rec counters identical {same_counters}")
print(f"differing cases where drain only adds payloads at the stream end: {tail_extra} of {n - same_ids}")
print(f"payloads delivered earlier with the drain: {earlier}, later: {later}; cases with any timing change: {cases_timing}")
for c, h, a, b, cs, cd in diffs:
    print("DIFF", h, "\n  stock", a, cs, "\n  drain", b, cd)
