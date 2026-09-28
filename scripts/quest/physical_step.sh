#!/bin/bash
# Usage: physical_step.sh start <label>   | physical_step.sh <step-name>   | physical_step.sh stop
# Monitor for hands-on checks with the user (controller buttons, preset menu, RTL unplug/replug): "start" pauses the
# Guardian, keeps the display awake and starts a background logcat of the app's tags plus the system's activity and
# USB events into out/physical_<label>/logcat.txt. Each step call takes a screenshot and prints the log lines since the
# previous step. "stop" ends the logcat and restores the Guardian.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
STATE="$QUEST_OUT/physical_current"
case "$1" in
  start)
    DIR="$QUEST_OUT/physical_$2"; mkdir -p "$DIR"; echo "$DIR" > "$STATE"; echo 0 > "$DIR/.lines"
    quest_guardian_pause 1; quest_prox_close
    qadb logcat -c
    # app tags + activity switches (X15: XR -> 2D) + USB attach/detach
    nohup "$ADB" -s "$QUEST" logcat -v time pixelpilot:V pixelpilot-xr:V pixelpilot-xr-input:V \
      ActivityTaskManager:I UsbHostManager:V UsbDeviceManager:V '*:S' > "$DIR/logcat.txt" 2>&1 &
    echo $! > "$DIR/.pid"
    echo "monitoring into $DIR (pid $(cat "$DIR/.pid"))"
    ;;
  stop)
    DIR=$(cat "$STATE"); kill "$(cat "$DIR/.pid")" 2>/dev/null
    quest_restore; rm -f "$STATE"; echo "stopped; guardian restored; log $DIR/logcat.txt"
    ;;
  *)
    DIR=$(cat "$STATE" 2>/dev/null) || { echo "run: physical_step.sh start <label>"; exit 1; }
    quest_prox_close
    N=$(printf "%02d" $(( $(ls "$DIR"/*.png 2>/dev/null | wc -l) + 1 )))
    qadb exec-out screencap -p > "$DIR/$N-$1.png"
    FROM=$(cat "$DIR/.lines"); TO=$(wc -l < "$DIR/logcat.txt"); echo "$TO" > "$DIR/.lines"
    echo "== step $N $1 ($(date +%T)), screenshot $DIR/$N-$1.png, top: $(qadb shell dumpsys activity activities | grep -m1 topResumedActivity | grep -o '[a-zA-Z.]*/[a-zA-Z.]*')"
    sed -n "$((FROM + 1)),${TO}p" "$DIR/logcat.txt" | grep -vE "FPS:|Decoding:|quality|WfbNGStats|Mavlink recv timeout| message [0-9]+:|tunnel window" | tail -25
    ;;
esac
