"""Which packets a replay leaves out: the DROP= spec of rtp_play.py, for deterministic-loss tests (e.g. how fast
intra refresh heals after a loss, OpenIPC O118 S0 T3).

  "k@period_s"  k consecutive packets starting at the first packet at or after each multiple of period_s (not at 0)
  "i1,i2,..."   these packet indices (0-based, in file order)
  ""            nothing
The same set applies to every loop of a replay.
"""

EPS = 1e-6   # s


def drops(spec, times):
    """spec as above; times = each packet's send time in s from the file start, in file order. Returns the indices."""
    spec = spec.strip()
    if not spec:
        return set()
    if "@" in spec:
        k_s, period_s = spec.split("@", 1)
        try:
            k, period = int(k_s), float(period_s)
        except ValueError:
            raise ValueError("DROP must be k@period_s or i1,i2,...: " + spec) from None
        if k < 1 or period <= 0:
            raise ValueError("DROP k@period_s needs k >= 1 and period_s > 0: " + spec)
        # Boundary m is m * period, not a running sum: adding 0.05 three times gives 0.15000000000000002, which would push
        # the run past the packet sent at 0.15 s. EPS absorbs the float error of the send times themselves.
        out, m, i = set(), 1, 0
        while i < len(times):
            if times[i] >= m * period - EPS:
                out.update(range(i, min(i + k, len(times))))
                m += 1
                i += k
            else:
                i += 1
        return out
    try:
        return {int(x) for x in spec.split(",")}
    except ValueError:
        raise ValueError("DROP must be k@period_s or i1,i2,...: " + spec) from None
