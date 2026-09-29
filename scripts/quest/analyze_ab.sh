#!/bin/bash
# Usage: analyze_ab.sh <label> <date> <steps.txt> <pc_minus_air_s> <baseline> "<header>" [air-drop-seconds.txt]
# The standard analysis of one detached A/B capture (ab_detached.sh start/pull <label>) against an air step log:
# link_audit, frame_fate, loss_bursts, step_jitter, ab_segments (drift line on <baseline>), ab_link, big_frames,
# latency_bins (latency over time within each step), and,
# with an air-drop-seconds file, drop_seconds. Each output goes to docs/xr/data/<name>-<date>-<label>.txt with
# <header> and the exact command as its first two lines.
#   <pc_minus_air_s>: PC clock minus air clock (the coordinator's "air = PC - X"). The air offset passed to the analyzers is
#   Quest-PC (out/ab_<label>.meta) + this.
#   GUARD_S (env, default 5): seconds skipped at each step start (a wfb_tx restart gaps ~2 s).
. "$(dirname "$0")/quest_env.sh" || exit 1
LABEL=$1; DATE=$2; STEPS=$3; PC_AIR=$4; BASE=$5; HEADER=$6; ADS=$7
[ -n "$HEADER" ] || { sed -n 2,10p "$0"; exit 1; }
GUARD=${GUARD_S:-5}
REPO=$(cd "$QUEST_DIR/../.." && pwd)
cd "$REPO" || exit 1
TRACE=scripts/quest/out/ab_$LABEL.pftrace
RAW=scripts/quest/out/qtx_$LABEL.raw.txt
META=scripts/quest/out/ab_$LABEL.meta
for f in "$TRACE" "$RAW" "$META" "$STEPS"; do [ -f "$f" ] || { echo "missing: $f"; exit 1; }; done
Q_PC=$(awk '{print $2 / 1000}' "$META")
OFF=$(python3 -c "print(round($Q_PC + $PC_AIR, 4))")
D=docs/xr/data
H="# ab_$LABEL, steps $STEPS, --air-offset-s $OFF (Quest-PC $Q_PC + PC-air $PC_AIR), --guard-s $GUARD. $HEADER"
L=scripts/quest-latch
COMMON=(--air-offset-s "$OFF" --guard-s "$GUARD")
run() {
  local out=$D/$1-$DATE-$LABEL.txt; shift
  { echo "$H"; echo "# python3 $*"; timeout 900 python3 "$@" 2>&1; } > "$out"
  echo "== $out"; tail -n +3 "$out" | grep -v "Rayleigh Z"
}
run audit $L/link_audit.py "$TRACE" "$STEPS" "${COMMON[@]}" --logcat scripts/quest/out/logcat_$LABEL.txt
run frame-fate $L/frame_fate.py "$TRACE" "$STEPS" "${COMMON[@]}"
if [ -n "$ADS" ]; then
  run loss-bursts $L/loss_bursts.py "$TRACE" "$STEPS" "${COMMON[@]}" --air-drop-seconds "$ADS"
else
  run loss-bursts $L/loss_bursts.py "$TRACE" "$STEPS" "${COMMON[@]}"
fi
run step-jitter $L/step_jitter.py "$TRACE" "$STEPS" "${COMMON[@]}"
run latency $L/ab_segments.py "$TRACE" "$STEPS" "${COMMON[@]}" --baseline "$BASE"
run link $L/ab_link.py "$TRACE" "$STEPS" "${COMMON[@]}"
run big-frames $L/big_frames.py "$TRACE" "$STEPS" "${COMMON[@]}" --baseline "$BASE"
run latency-bins $L/latency_bins.py "$TRACE" "$STEPS" "${COMMON[@]}" --baseline "$BASE"
[ -n "$ADS" ] && run drop-seconds $L/drop_seconds.py "$RAW" "$STEPS" "$ADS" "${COMMON[@]}"
exit 0
