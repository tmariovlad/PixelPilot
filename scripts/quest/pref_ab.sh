#!/bin/bash
# Usage: pref_ab.sh <label> <pref> <step_s> <step> <step> ...
#   step = [TAG:]value, e.g. true / false / OLD:true; TAG selects the debug APK in $APK_<TAG> (installed only when it
#   changes; the release app is never touched). Example:
#   APK_OLD=old.apk APK_NEW=new.apk pref_ab.sh alink adaptive_link_enabled 45 OLD:true NEW:true NEW:false OLD:true NEW:false NEW:true
# In-trace A/B of an app boolean pref read at start-up (optionally across app builds): one long lean trace
# (ab_long.sh) covers every step; each step installs its build if needed, writes the pref (quest_adb.set_prefs:
# keeps gs.key), force-stops and relaunches XR, and logs "<Quest epoch> <step>" to out/steps_<label>.txt. The air
# unit is untouched, so its RTP clock runs on and ab_segments.py can read the steps against one drift line
# (Quest clock: --air-offset-s 0; use --guard-s >= 10: after a restart the app needs a keyframe to show video).
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; PREF=$2; STEP=$3; shift 3
[ -n "$LABEL" ] && [ -n "$PREF" ] && [ "$#" -ge 2 ] || { echo "usage: pref_ab.sh <label> <pref> <step_s> <[TAG:]value> ..."; exit 1; }
STEPS="$QUEST_OUT/steps_$LABEL.txt"; mkdir -p "$QUEST_OUT"; : > "$STEPS"
TOTAL=$(( (STEP + 12) * $# + 20 ))   # + install/relaunch time per step
quest_prox_close
bash ab_long.sh "$LABEL" "$TOTAL" > "$QUEST_OUT/ab_$LABEL.capture.log" 2>&1 &
TRACE_PID=$!
sleep 8   # let the trace start before the first step
CUR=""
for SPEC in "$@"; do
  TAG=""; V=$SPEC
  case "$SPEC" in *:*) TAG=${SPEC%%:*}; V=${SPEC#*:} ;; esac
  qadb shell am force-stop "$PKG"
  if [ -n "$TAG" ] && [ "$TAG" != "$CUR" ]; then
    APK_VAR="APK_$TAG"; APK=${!APK_VAR}
    [ -f "$APK" ] || { echo "no APK for tag $TAG (set $APK_VAR)"; break; }
    qadb install -r "$(cygpath -w "$APK")" | tail -1; CUR=$TAG
  fi
  python3 -c "import quest_adb as q; q.set_prefs({'$PREF': '$V' == 'true'})"
  echo "$(qadb shell date +%s.%N | tr -d '\r') $SPEC" | tee -a "$STEPS"
  quest_prox_close
  quest_start_xr >/dev/null
  sleep "$STEP"
done
echo "$(qadb shell date +%s.%N | tr -d '\r') END" | tee -a "$STEPS"
wait "$TRACE_PID"
cat "$QUEST_OUT/ab_$LABEL.capture.log"
