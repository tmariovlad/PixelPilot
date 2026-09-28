#!/bin/bash
# Usage: optical_step.sh backup <label> | step <label> <hz> [fov_deg] | restore <label>
# One step of the optical (ESP32/LDR on the lens) refresh bracket: the headset is not touched between steps, only
# the prefs change. "backup" saves the user's prefs file (out/opt_<label>.prefs-backup.xml); "step" writes
# xr_refresh_hz (+ xr_fov_deg, default 90 so the LED image is as large as possible), relaunches XR and logs the app's
# readback to out/opt_<label>.steps.txt; "restore" writes the backup back and relaunches XR.
# The 25-sample rig runs themselves go over serial (skill /g2g-latency; port auto-detected by find_rig_port.py, CP210x 10C4:EA60 — never COM5, which is the DPS-150 powering the air unit) between the steps.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
ACTION=$1; LABEL=$2
[ -n "$ACTION" ] && [ -n "$LABEL" ] || { echo "usage: optical_step.sh backup|step|restore <label> [hz] [fov_deg]"; exit 1; }
mkdir -p "$QUEST_OUT"
BACKUP="$QUEST_OUT/opt_$LABEL.prefs-backup.xml"
qadb shell am force-stop "$PKG"
case "$ACTION" in
  backup)
    python3 -c "import quest_adb as q, sys; q.backup_prefs(sys.argv[1])" "$(cygpath -m "$BACKUP")" && echo "saved $BACKUP"
    ;;
  step)
    HZ=$3; FOV=${4:-90}
    [ -f "$BACKUP" ] || { echo "run backup first"; exit 1; }
    python3 -c "import quest_adb as q; q.set_prefs({'xr_refresh_hz': int('$HZ'), 'xr_fov_deg': float('$FOV')})" || exit 1
    qadb logcat -c
    quest_prox_close
    quest_start_xr -W >/dev/null
    sleep 6
    APPLIED=$(qadb logcat -d | grep -oE "requested [0-9]+ Hz -> [0-9]+ Hz \(result -?[0-9]+\)" | tail -1)
    echo "$(qadb shell date +%s.%N | tr -d '\r') req=$HZ fov=$FOV app='$APPLIED'" | tee -a "$QUEST_OUT/opt_$LABEL.steps.txt"
    ;;
  restore)
    python3 -c "import quest_adb as q, sys; q.restore_prefs(sys.argv[1])" "$(cygpath -m "$BACKUP")" && echo "prefs restored"
    quest_start_xr >/dev/null
    ;;
  *) echo "unknown action $ACTION"; exit 1 ;;
esac
