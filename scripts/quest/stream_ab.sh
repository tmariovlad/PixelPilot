#!/bin/bash
# Usage: stream_ab.sh <label> <step_s> <stream|quiet> ...   e.g. stream_ab.sh u1 120 stream quiet quiet stream stream quiet quiet stream
# U1 of docs/xr/uplink-t4-analysis.md: does a STREAMING adb logcat (quest_tx_log.sh, over adb-over-Wi-Fi) cost video
# packets? The app is never relaunched. One detached capture (ab_detached.sh) covers every step; in a "stream" step
# quest_tx_log.sh streams for the whole step, in a "quiet" step nothing talks over adb. Steps are logged on the Quest
# clock from the PC clock + the offset ab_detached.sh measured (no adb call at a step boundary). The trace is pulled
# at the end. Analysis (Quest clock): ab_link.py / link_audit.py with --air-offset-s 0 and the steps file.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; STEP=$2; shift 2
[ -n "$LABEL" ] && [ -n "$STEP" ] && [ "$#" -ge 2 ] || { echo "usage: stream_ab.sh <label> <step_s> <stream|quiet> ..."; exit 1; }
TOTAL=$(( STEP * $# + 30 ))
bash ab_detached.sh start "$LABEL" "$TOTAL" || exit 1
T0=$(date +%s)
OFF_MS=$(awk '{print $2}' "$QUEST_OUT/ab_$LABEL.meta")
qepoch() { python3 -c "import time; print(f'{time.time() + $OFF_MS / 1000:.3f}')"; }
STEPS="$QUEST_OUT/steps_$LABEL.txt"; : > "$STEPS"
sleep 10   # let the trace start before the first step
i=0
for S in "$@"; do
  i=$((i + 1))
  case "$S" in stream|quiet) ;; *) echo "step must be stream or quiet: $S"; exit 1 ;; esac
  echo "$(qepoch) $S" | tee -a "$STEPS"
  if [ "$S" = stream ]; then
    bash quest_tx_log.sh "$STEP" "$QUEST_OUT/qtx_${LABEL}_stream$i.txt" > /dev/null 2>&1 &
  fi
  sleep "$STEP"
  wait   # the streaming logger ends with its step
done
echo "$(qepoch) END" | tee -a "$STEPS"
sleep $(( T0 + TOTAL + 5 - $(date +%s) > 0 ? T0 + TOTAL + 5 - $(date +%s) : 0 ))
bash ab_detached.sh pull "$LABEL"
