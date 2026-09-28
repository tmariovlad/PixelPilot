"""Offline checks of link_audit: trace-loss guard, same-window p_data, RTP loss runs, arrival gaps, logcat burst timing.
Run: python3 test_link_audit.py"""
import os
import tempfile

from link_audit import (arrival_gaps, loss_runs, p_data, parse_logcat, periodicity, run_summary, trace_loss,
                        uplink_coincidence)

S = 1e9


def test_trace_loss_flags_only_real_loss_stats():
    rows = [("ftrace_cpu_overrun_end", 0, 0), ("ftrace_cpu_overrun_end", 3, 12),
            ("ftrace_cpu_dropped_events_end", 1, 0), ("traced_buf_chunks_discarded", 0, 4),
            ("traced_buf_bytes_written", 0, 55_600_000), ("traced_buf_chunks_written", 0, 1698),
            ("traced_data_loss", None, 0)]
    bad = trace_loss(rows)
    assert ("ftrace_cpu_overrun_end", 3, 12) in bad
    assert ("traced_buf_chunks_discarded", 0, 4) in bad
    assert all(v != 0 for _, _, v in bad)
    assert not any(n in ("traced_buf_bytes_written", "traced_buf_chunks_written") for n, _, _ in bad)


def test_trace_loss_clean_trace_is_empty():
    assert trace_loss([("ftrace_cpu_overrun_end", 0, 0), ("traced_buf_bytes_written", 0, 10)]) == []


def test_p_data_same_window():
    # 950 RTP received + 50 lost = 1000 data expected; 30 repaired by FEC + 50 still lost -> 8 % pre-FEC
    assert abs(p_data(fec_rec=30, wfb_lost=50, rtp_received=950, rtp_lost=50) - 0.08) < 1e-12
    assert p_data(0, 0, 0, 0) is None


def test_loss_runs_across_wrap_and_reorder():
    # holes: 3 (1 pkt), 6-7 (2 pkts), 65535..0 wrap is continuous; 11 arrives late (reorder fills its own hole)
    seqs = [1, 2, 4, 5, 8, 9, 10, 12, 11, 13]
    assert sorted(loss_runs(seqs)) == [1, 2]
    wrap = [65533, 65534, 65535, 0, 2, 3]
    assert loss_runs(wrap) == [1]
    assert loss_runs([]) == []


def test_run_summary_shares():
    s = run_summary([1, 1, 2, 4, 6], seconds=2.0)
    assert s["runs"] == 5 and s["lost"] == 14
    assert s["runs_per_s"] == 2.5
    assert s["hist"] == {1: 2, 2: 1, 3: 0, 4: 1, "5+": 1}
    assert abs(s["share_lost_in_5plus"] - 6 / 14) < 1e-12


def test_arrival_gaps_max_and_p99():
    ts = [0, 1_000_000, 2_000_000, 19_000_000, 20_000_000]   # ns; one 17 ms gap
    g = arrival_gaps(ts)
    assert abs(g["max_ms"] - 17.0) < 1e-9
    assert g["n"] == 4


def write(text):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_parse_logcat_epoch_lines():
    path = write("     1790590000.100  1234  1300 I wfb-ng  : PKT_LOST\t3\n"
                 "     1790590000.102  1234  1301 D devourer: TX DESC len=120 rate=MCS1\n"
                 "garbage line\n"
                 "     1790590000.500  1234  1300 I wfb-ng  : PKT_LOST\t1\n"
                 "     1790590001.000  1234  1300 W wfb-ng  : block overrides 7\n")
    ev = parse_logcat(path)
    os.remove(path)
    assert ev["lost"] == [(1790590000.100, 3), (1790590000.500, 1)]
    assert ev["tx"] == [1790590000.102]
    assert ev["overrides"] == [1790590001.000]


def test_uplink_coincidence_counts_gaps_just_after_a_tx():
    tx = [10.000, 20.000, 30.000]
    gaps = [10.001, 20.0015, 25.0, 30.010]           # 2 within 2 ms after a TX, 2 not
    assert uplink_coincidence(gaps, tx, window_s=0.002) == 0.5
    assert uplink_coincidence([], tx, 0.002) is None


def test_periodicity_finds_a_locked_rate_and_not_a_random_one():
    beacon = [i / 9.765625 + 0.0003 * ((i * 7919) % 5) for i in range(200)]   # ~9.77 Hz with small jitter
    z = dict(periodicity(beacon, freqs=(4.0, 9.765625)))
    assert z[9.765625] > 50          # Rayleigh Z >> 3 means phase-locked to that rate
    assert z[4.0] < 10
    assert periodicity([1.0], freqs=(4.0,)) == [(4.0, 0.0)]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
