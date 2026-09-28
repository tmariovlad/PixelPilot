#!/bin/bash
# Usage: refresh_bracket.sh <label> <settle_s> <hz> <hz> ...     e.g. refresh_bracket.sh rb1 12 120 72 90 72 120 90
# Display refresh-rate bracket on the real link (air unit untouched: the app only sends a read-only vmode LIST at
# start). Per step: force-stop, write xr_refresh_hz (quest_adb.set_prefs keeps gs.key, other prefs -> defaults),
# relaunch XR, wait <settle_s> for a keyframe, capture a 9 s compositor trace (quest-latch/compositor.pbtx) and save
# it as out/rb_<label>_<n>_<hz>.pftrace. The trace's vsync period (latch_analyze.py) is the readback of the rate the
# panel actually ran at; the app's own readback is logged from logcat ("requested X Hz -> Y Hz").
# The user's prefs file is backed up first (out/rb_<label>.prefs-backup.xml) and written back at the end.
# Analyse afterwards: for f in out/rb_<label>_*.pftrace; do python3 ../quest-latch/latch_analyze.py $f; python3 bq_stats.py $f; done
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; SETTLE=$2; shift 2
[ -n "$LABEL" ] && [ -n "$SETTLE" ] && [ "$#" -ge 1 ] || { echo "usage: refresh_bracket.sh <label> <settle_s> <hz> ..."; exit 1; }
mkdir -p "$QUEST_OUT"
STEPS="$QUEST_OUT/rb_$LABEL.steps.txt"; : > "$STEPS"
BACKUP="$QUEST_OUT/rb_$LABEL.prefs-backup.xml"
qadb shell am force-stop "$PKG"
python3 -c "import quest_adb as q, sys; q.backup_prefs(sys.argv[1])" "$(cygpath -m "$BACKUP")" \
  || { echo "prefs backup failed; nothing changed"; exit 1; }
N=0
for HZ in "$@"; do
  N=$((N + 1))
  OUT="$QUEST_OUT/rb_${LABEL}_${N}_${HZ}.pftrace"
  qadb shell am force-stop "$PKG"
  python3 -c "import quest_adb as q; q.set_prefs({'xr_refresh_hz': int('$HZ')})" || exit 1
  qadb logcat -c
  quest_prox_close
  quest_start_xr -W >/dev/null
  sleep "$SETTLE"
  quest_prox_close
  qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/t.pftrace' < "$QUEST_LATCH/compositor.pbtx" 2>&1 | grep -iE "error|wrote" | tail -1
  qadb pull /data/misc/perfetto-traces/t.pftrace "$(cygpath -w "$OUT")" 2>&1 | tail -1
  APPLIED=$(qadb logcat -d | grep -oE "requested [0-9]+ Hz -> [0-9]+ Hz \(result -?[0-9]+\)" | tail -1)
  # system-side readback of the panel mode (format unverified on Horizon OS: kept raw for the analysis)
  qadb shell dumpsys display | grep -iE "refresh|fps|mode" > "$QUEST_OUT/rb_${LABEL}_${N}_${HZ}.display.txt"
  echo "$(qadb shell date +%s.%N | tr -d '\r') step=$N req=$HZ app='$APPLIED' trace=$(basename "$OUT")" | tee -a "$STEPS"
done
qadb shell am force-stop "$PKG"
python3 -c "import quest_adb as q, sys; q.restore_prefs(sys.argv[1])" "$(cygpath -m "$BACKUP")" \
  && echo "prefs restored from $BACKUP"
quest_start_xr >/dev/null
echo "done; steps in $STEPS"
