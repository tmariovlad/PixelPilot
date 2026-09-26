#!/bin/bash
# Usage: ab_run.sh <label> [seconds=10]
# One transport A/B sample on the running XR app, the same way for every transport (wfb-ng via the RTL,
# APFPV via the Quest's internal Wi-Fi, APFPV via the RTL): link_measure.sh for N seconds (decoded fps;
# quality + uplink lost/s exist only on wfb-ng), then a 9 s Perfetto trace, analysed by transport_analyze.py
# (RTP sequence gaps = loss before the app, transport-delay excess = jitter) and gaps.py (burstiness).
# Transport-agnostic because the RTP counters come from VideoPlayer::onNewRTPData, after either transport.
# The app must already be running with the video up. Output: out/ab_<label>.{log,pftrace}.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; SECS=${2:-10}
[ -n "$LABEL" ] || { echo "usage: ab_run.sh <label> [seconds]"; exit 1; }
mkdir -p "$QUEST_OUT"
LOG="$QUEST_OUT/ab_$LABEL.log"; TRACE="$QUEST_OUT/ab_$LABEL.pftrace"
quest_prox_close
{
  echo "# $LABEL $(date '+%F %T')"
  bash link_measure.sh "$SECS" "$LABEL"
  qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/ab.pftrace' < "$QUEST_LATCH/compositor.pbtx" 2>&1 | grep -iE "error" | tail -2
  qadb pull /data/misc/perfetto-traces/ab.pftrace "$(cygpath -w "$TRACE")" 2>&1 | grep -iE "error" | tail -1
  python3 "$QUEST_LATCH/transport_analyze.py" "$(cygpath -w "$TRACE")"
  python3 gaps.py "$(cygpath -w "$TRACE")" | head -3
} 2>&1 | tee "$LOG"
