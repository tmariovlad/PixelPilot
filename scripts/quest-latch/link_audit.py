"""Link-loss audit for an in-trace A/B (T0 of the OpenIPC 25 Mbit/s audit, O117). Adds what ab_link.py / ab_segments.py
do not check, so every run validates itself:

1. Trace-loss guard: the trace's own 'stats' table. A non-zero ftrace overrun / dropped-event / discarded-chunk /
   data-loss stat means missing Perfetto events, which ab_segments and ab_link would count as packet loss.
2. p_data, the pre-FEC data loss measured on one device in one window:
       p_data = (fec_rec + wfb_lost) / (RTP received + RTP lost)
   ab_link's pre_fec_loss_pct divides the Quest rx rate in the guarded window by the air tx rate over the whole step,
   which can be off by up to ~2 points (audit H5 §2).
3. Burst shape per step: lengths of the RTP sequence holes (runs), runs/s, the share of lost packets in runs >= 5,
   and the largest / p99 packet inter-arrival gap. Short runs with small gaps = sub-ms loss clusters; long runs with
   long gaps = a stall (USB, CPU, GC) or an outage.
4. --logcat: timing of post-FEC losses from a logcat capture (T0 of the audit). Capture it DETACHED, on the Quest,
   and pull the file afterwards, as ab_detached.sh does:
       adb -s <quest> shell logcat -T 1 -v epoch -s wfb-ng:I devourer:D -f /sdcard/<file>    (then adb pull)
   Do NOT stream it live over adb-over-Wi-Fi: a streamed capture makes the Quest's internal Wi-Fi transmit after every
   uplink frame, which is itself a suspected cause of the loss it measures (pixelpilot-xr docs/xr/uplink-t4-analysis.md).
   Filter the pulled file for PKT_LOST / TX DESC / block overrides, or pass it whole. The analysis gives the fraction of loss events within --window-ms after a Quest uplink frame (TX DESC) against a shifted
   control, and the Rayleigh phase-locking Z of the loss times at candidate rates (1 Hz session key, 4 Hz uplink timer,
   9.77 Hz beacons, 72/90 Hz compositor/video). Z > ~13 (p < 1e-6) means the losses lock to that rate.

Usage: python3 link_audit.py trace.pftrace steps.txt --air-offset-s S [--guard-s 2]
       python3 link_audit.py --logcat pktlost.txt [--window-ms 2]
Background: OpenIPC repo repos/tasks/link-25mbit-audit-2026-09-28/00-INDEX-link-25mbit-audit.md.
"""
import argparse
import cmath
import math
import re
from bisect import bisect_right

from ab_segments import pct, step_window

# stats-table names that mean lost trace data; *_written and other accounting stats are not loss
LOSS_STAT = re.compile(r"^(ftrace_cpu_overrun|ftrace_cpu_dropped_events|traced_buf_.*(discarded|overwritten|"
                       r"patches_failed|abi_violations)|.*data_loss)")
CANDIDATE_HZ = (1.0, 4.0, 9.765625, 72.0, 90.0)


def trace_loss(rows):
    """rows [(name, idx, value)] from 'select name, idx, value from stats'. Returns the non-zero loss rows."""
    return [(n, i, v) for n, i, v in rows if v and LOSS_STAT.match(n)]


def p_data(fec_rec, wfb_lost, rtp_received, rtp_lost):
    """Pre-FEC data loss in one window on one device, or None without traffic."""
    expected = rtp_received + rtp_lost
    return (fec_rec + wfb_lost) / expected if expected else None


def unwrap(seqs):
    """16-bit RTP sequence numbers (arrival order) unwrapped the way rtp_seq.seq_loss does: each one against the
    previous with a signed step, so a late packet fills its own hole and a 65535 -> 0 wrap is continuous."""
    if not seqs:
        return []
    useq = [seqs[0]]
    for a, b in zip(seqs, seqs[1:]):
        useq.append(useq[-1] + ((b - a + 0x8000) & 0xFFFF) - 0x8000)
    return useq


def loss_runs(seqs):
    """Lengths of the holes in 16-bit RTP sequence numbers (arrival order), after unwrap()."""
    if not seqs:
        return []
    got = sorted(set(unwrap(seqs)))
    return [b - a - 1 for a, b in zip(got, got[1:]) if b - a > 1]


def run_summary(runs, seconds):
    lost = sum(runs)
    hist = {1: 0, 2: 0, 3: 0, 4: 0, "5+": 0}
    for r in runs:
        hist[r if r < 5 else "5+"] += 1
    return {"runs": len(runs), "lost": lost, "runs_per_s": len(runs) / seconds if seconds else None, "hist": hist,
            "share_lost_in_5plus": sum(r for r in runs if r >= 5) / lost if lost else 0.0}


def arrival_gaps(ts_ns):
    d = [(b - a) / 1e6 for a, b in zip(ts_ns, ts_ns[1:])]
    return {"n": len(d), "max_ms": max(d) if d else None, "p99_ms": pct(d, .99) if d else None}


def parse_logcat(path):
    """'logcat -v epoch' lines -> {'lost': [(epoch, n)], 'tx': [epoch], 'overrides': [epoch]}."""
    ev = {"lost": [], "tx": [], "overrides": []}
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.split(None, 1)
        try:
            t = float(parts[0])
        except (ValueError, IndexError):
            continue
        m = re.search(r"PKT_LOST\s+(\d+)", line)
        if m:
            ev["lost"].append((t, int(m.group(1))))
        elif "TX DESC" in line:
            ev["tx"].append(t)
        elif "block overrides" in line:
            ev["overrides"].append(t)
    return ev


def uplink_coincidence(gap_times, tx_times, window_s):
    """Share of loss events with a Quest uplink frame in [t - window, t]; None without events. tx_times sorted."""
    if not gap_times:
        return None
    hit = 0
    for t in gap_times:
        j = bisect_right(tx_times, t)
        hit += j > 0 and t - tx_times[j - 1] <= window_s
    return hit / len(gap_times)


def periodicity(times, freqs=CANDIDATE_HZ):
    """[(f, Rayleigh Z = n * |mean(exp(2 pi i f t))|^2)]; Z ~ 1 for random times, ~n when locked to f."""
    n = len(times)
    if n < 2:
        return [(f, 0.0) for f in freqs]
    return [(f, n * abs(sum(cmath.exp(2j * math.pi * f * t) for t in times) / n) ** 2) for f in freqs]


def window_sum(samples, a, b):
    return sum(v for t, v in samples if a <= t < b)


def audit_steps(counters, pkts, steps, end, guard):
    """counters {name: [(ns, v)]} as from ab_link.load; pkts [(ns, seq)] sorted. Returns [(i, label, row)]."""
    rows = []
    for i, (_, lab) in enumerate(steps):
        a, b = step_window(i, steps, end, guard)
        mine = [p for p in pkts if a <= p[0] < b]
        seqs = [s for _, s in mine]
        runs = loss_runs(seqs)
        received, lost = len(set(unwrap(seqs))), sum(runs)   # unwrapped: a step can hold > 65536 packets
        fec = window_sum(counters.get("ppxr_wfb_fec_rec", []), a, b)
        wlost = window_sum(counters.get("ppxr_wfb_lost", []), a, b)
        r = run_summary(runs, (b - a) / 1e9)
        r.update(arrival_gaps([t for t, _ in mine]))
        r.update(received=received, rtp_lost=lost, fec_rec=fec, wfb_lost=wlost,
                 p_data=p_data(fec, wlost, received, lost),
                 post=lost / (received + lost) if received + lost else None)
        rows.append((i, lab, r))
    return rows


def print_steps(rows, bad):
    print("TRACE LOSS: " + ("none (stats table clean)" if not bad else
                            "PRESENT -> missing events count as packet loss, results unreliable: " + str(bad)))
    hdr = (f"{'':15s}{'rx':>7s}{'lost':>6s}{'fec':>6s}{'wlost':>6s}{'p_data%':>8s}{'post%':>7s}{'runs/s':>7s}"
           f"{'r1':>5s}{'r2':>5s}{'r3':>5s}{'r4':>5s}{'r5+':>5s}{'5+sh%':>6s}{'gapmax':>7s}{'gap99':>6s}")
    print(hdr)
    f = lambda v, w, d=1: f"{'-':>{w}}" if v is None else f"{v:{w}.{d}f}"
    for i, lab, r in rows:
        h = r["hist"]
        print(f"{i:2d} {lab:12s}{r['received']:7d}{r['rtp_lost']:6d}{r['fec_rec']:6.0f}{r['wfb_lost']:6.0f}"
              f"{f(None if r['p_data'] is None else 100 * r['p_data'], 8, 2)}"
              f"{f(None if r['post'] is None else 100 * r['post'], 7, 2)}{f(r['runs_per_s'], 7)}"
              + "".join(f"{h[k]:5d}" for k in (1, 2, 3, 4, "5+"))
              + f"{100 * r['share_lost_in_5plus']:6.1f}{f(r['max_ms'], 7)}{f(r['p99_ms'], 6)}")


def print_logcat(ev, window_ms):
    lost_t = [t for t, _ in ev["lost"]]
    sizes = [n for _, n in ev["lost"]]
    print(f"PKT_LOST events {len(sizes)}, packets {sum(sizes)}; TX DESC {len(ev['tx'])}; "
          f"block overrides {len(ev['overrides'])}" + ("  <- outage / ring override" if ev["overrides"] else ""))
    if sizes:
        print("post-FEC gap sizes: " + ", ".join(f"{k}:{sizes.count(k)}" for k in sorted(set(sizes))[:12]))
    w = window_ms / 1e3
    hit = uplink_coincidence(lost_t, ev["tx"], w)
    ctl = uplink_coincidence(lost_t, sorted(t + 0.050 for t in ev["tx"]), w)   # same TX pattern shifted by 50 ms
    if hit is not None:
        print(f"loss within {window_ms:g} ms after a Quest TX: {100 * hit:.1f} % (control, TX shifted 50 ms: "
              f"{100 * ctl:.1f} %)")
    for f_hz, z in periodicity(lost_t):
        print(f"Rayleigh Z @ {f_hz:8.3f} Hz = {z:8.1f}" + ("  <- locked" if z > 13.8 else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace", nargs="?")
    ap.add_argument("steps", nargs="?")
    ap.add_argument("--air-offset-s", type=float)
    ap.add_argument("--guard-s", type=float, default=2.0)
    ap.add_argument("--logcat", help="file from the T0 logcat capture (PKT_LOST / TX DESC / block overrides)")
    ap.add_argument("--window-ms", type=float, default=2.0)
    a = ap.parse_args()
    if a.logcat:
        print_logcat(parse_logcat(a.logcat), a.window_ms)
        if not a.trace:
            return
    if not (a.trace and a.steps and a.air_offset_s is not None):
        ap.error("trace, steps and --air-offset-s are needed for the per-step audit")
    from ab_link import load
    from perfetto.trace_processor import TraceProcessor
    counters, _thermal, _fields, steps, end = load(a.trace, a.air_offset_s, a.steps, None)
    tp = TraceProcessor(trace=a.trace)
    bad = trace_loss([(r.name, r.idx, r.value) for r in tp.query("select name, idx, value from stats")])
    pkts = [(r.ts, int(r.value)) for r in tp.query(
        "select c.ts, c.value from counter c join counter_track t on c.track_id=t.id "
        "where t.name='ppxr_rtp_seq' order by c.ts")]
    print_steps(audit_steps(counters, pkts, steps, end, a.guard_s * 1e9), bad)


if __name__ == "__main__":
    main()
