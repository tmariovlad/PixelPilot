#!/bin/bash
# Usage: ab_long.sh <label> [seconds=120]
# Capture side of an in-trace A/B (ab_segments.py): one long, lean Perfetto trace of the running XR app with only the
# app's own markers (ppxr_rtp_seq/ts, ppxr_frame_ready), plus the Quest-minus-PC REALTIME offset measured right before.
# The lever is switched meanwhile by a timed loop on the air unit that logs "<epoch> <label>" per step.
# Output: out/ab_<label>.pftrace and out/ab_<label>.meta (quest_minus_pc_ms). Then:
#   python3 ../quest-latch/ab_segments.py out/ab_<label>.pftrace steps.txt --air-offset-s <(quest-pc) - (air-pc)>
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; SECS=${2:-120}
[ -n "$LABEL" ] || { echo "usage: ab_long.sh <label> [seconds]"; exit 1; }
mkdir -p "$QUEST_OUT"
TRACE="$QUEST_OUT/ab_$LABEL.pftrace"; META="$QUEST_OUT/ab_$LABEL.meta"

# Quest REALTIME minus PC REALTIME, from the adb round trip with the smallest RTT out of 5.
best=""
for _ in 1 2 3 4 5; do
  a=$(date +%s.%N); q=$(qadb shell date +%s.%N | tr -d '\r'); b=$(date +%s.%N)
  best=$(python3 -c "a,q,b=$a,$q,$b; r=(b-a)*1e3; o=(q-(a+b)/2)*1e3; p='$best'.split()
print(f'{o:.1f} {r:.1f}' if not p or r<float(p[1]) else '$best')")
done
echo "quest_minus_pc_ms ${best% *} rtt_ms ${best#* }" | tee "$META"

quest_prox_close
sed "s/^duration_ms: .*/duration_ms: $((SECS * 1000))/" "$QUEST_LATCH/transport_long.pbtx" \
  | qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/ab_long.pftrace' 2>&1 | grep -iE "error|wrote" | tail -2
qadb pull /data/misc/perfetto-traces/ab_long.pftrace "$(cygpath -w "$TRACE")" 2>&1 | tail -1
