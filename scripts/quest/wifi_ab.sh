#!/bin/bash
# Usage: wifi_ab.sh check                  - harmless: does a setsid'd shell survive the adb session and run cmd wifi?
#        wifi_ab.sh start <label> [step_s=120] [pairs=2]
#        wifi_ab.sh pull <label>
# T2' of the link-25mbit audit: is the Quest's own Wi-Fi (associated to the home AP, waking on every 102.4 ms beacon)
# behind the beacon-locked loss floor? A/B/A/B: A = internal Wi-Fi on, B = off. adb runs over that same Wi-Fi, so the
# whole sequence runs ON THE QUEST from one setsid'd script (it survives adb dropping), writes its step epochs on the
# Quest clock, and re-enables Wi-Fi at the end; a second, independent watchdog re-enables it too. The capture is
# ab_detached.sh (perfetto --background + logcat to a file). After the run: adb reconnects over Wi-Fi, then "pull".
# If Wi-Fi does not come back, the user can turn it on in Quick Settings.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
CMD=$1; LABEL=$2; STEP=${3:-120}; PAIRS=${4:-2}
DEV_SCRIPT=/data/local/tmp/ppxr_wifi_ab.sh
DEV_STEPS=/sdcard/ppxr_steps_$LABEL.txt

case "$CMD" in
check)
  qadb shell "rm -f /sdcard/ppxr_wifi_check.txt; setsid sh -c 'sleep 20; { date +%s; cmd wifi status | head -1; } > /sdcard/ppxr_wifi_check.txt' </dev/null >/dev/null 2>&1 &"
  echo "launched; the adb shell has closed. Waiting 25 s ..."
  sleep 25
  qadb shell cat /sdcard/ppxr_wifi_check.txt || { echo "CHECK FAILED: the detached shell did not survive"; exit 1; }
  ;;
start)
  [ -n "$LABEL" ] || { echo "usage: wifi_ab.sh start <label> [step_s] [pairs]"; exit 1; }
  TOTAL=$(( STEP * 2 * PAIRS + 60 ))
  # The on-Quest sequence: A (on) STEP s, B (off) STEP s, PAIRS times, then Wi-Fi on and END.
  {
    echo 'F='"$DEV_STEPS"
    echo 'st() { echo "$(date +%s.%N) $1" >> $F; }'
    echo ': > $F'
    echo 'sleep 10'
    for _ in $(seq "$PAIRS"); do
      echo 'st wifi_on'
      echo "sleep $STEP"
      echo 'st wifi_off; cmd wifi set-wifi-enabled disabled'
      echo "sleep $STEP"
      echo 'cmd wifi set-wifi-enabled enabled'
    done
    echo 'st END'
  } > "$QUEST_OUT/ppxr_wifi_ab_$LABEL.sh"
  qadb push "$(cygpath -w "$QUEST_OUT/ppxr_wifi_ab_$LABEL.sh")" "$DEV_SCRIPT" | tail -1
  bash ab_detached.sh start "$LABEL" "$TOTAL" || exit 1
  # Watchdog first (independent of the sequence), then the sequence; both detached from this adb session.
  qadb shell "setsid sh -c 'sleep $(( TOTAL + 30 )); cmd wifi set-wifi-enabled enabled' </dev/null >/dev/null 2>&1 &"
  qadb shell "setsid sh $DEV_SCRIPT </dev/null >/dev/null 2>&1 &"
  echo "started at PC $(date +%s): ${PAIRS}x (on ${STEP}s, off ${STEP}s); adb drops in each off step."
  echo "Wi-Fi is back for good at ~PC $(( $(date +%s) + 10 + STEP * 2 * PAIRS )); watchdog at +$(( TOTAL + 30 )) s."
  ;;
pull)
  qadb pull "$DEV_STEPS" "$(cygpath -w "$QUEST_OUT/steps_$LABEL.txt")" | tail -1
  cat "$QUEST_OUT/steps_$LABEL.txt"
  bash ab_detached.sh pull "$LABEL"
  ;;
*) echo "usage: wifi_ab.sh check | start <label> [step_s] [pairs] | pull <label>"; exit 1 ;;
esac
