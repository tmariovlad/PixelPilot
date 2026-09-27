#!/bin/bash
# Usage: pref_ab.sh <label> <pref> <step_s> <value> <value> ...   e.g. pref_ab.sh alink adaptive_link_enabled 45 true false true false true
# In-trace A/B of an app boolean pref that is read at start-up: one long lean trace (ab_long.sh) covers every step;
# each step writes the pref (quest_adb.set_prefs: keeps gs.key), force-stops and relaunches XR, and logs
# "<Quest epoch> <pref>=<value>" to out/steps_<label>.txt. The air unit is untouched, so its RTP clock runs on and
# ab_segments.py can read the steps against one drift line (Quest clock: --air-offset-s 0; use --guard-s >= 10,
# the app needs a few seconds and a keyframe to show video again after each restart).
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; PREF=$2; STEP=$3; shift 3
[ -n "$LABEL" ] && [ -n "$PREF" ] && [ "$#" -ge 2 ] || { echo "usage: pref_ab.sh <label> <pref> <step_s> <v1> <v2> ..."; exit 1; }
STEPS="$QUEST_OUT/steps_$LABEL.txt"; mkdir -p "$QUEST_OUT"; : > "$STEPS"
TOTAL=$(( STEP * $# + 20 ))
quest_prox_close
bash ab_long.sh "$LABEL" "$TOTAL" > "$QUEST_OUT/ab_$LABEL.capture.log" 2>&1 &
TRACE_PID=$!
sleep 8   # let the trace start before the first step
for V in "$@"; do
  qadb shell am force-stop "$PKG"
  python3 -c "import quest_adb as q; q.set_prefs({'$PREF': '$V' == 'true'})"
  echo "$(qadb shell date +%s.%N | tr -d '\r') $PREF=$V" | tee -a "$STEPS"
  quest_prox_close
  quest_start_xr >/dev/null
  sleep "$STEP"
done
echo "$(qadb shell date +%s.%N | tr -d '\r') END" | tee -a "$STEPS"
wait "$TRACE_PID"
cat "$QUEST_OUT/ab_$LABEL.capture.log"
