#!/bin/bash
# Usage: replug_check.sh prep <apk> <label> | check <label> | wake <label>
# On-device check of the "RTL plugged in with the display off" crash (docs/xr/troubleshooting.md). One run =
#   prep  : install the debug APK (release app untouched), start XR, put the headset to sleep (KEYCODE_SLEEP),
#           start a continuous logcat capture (events + main) and wait 90 s so the app's uid goes idle.
#   (user : unplug the RTL, wait 10 s, plug it back in, without waking the headset)
#   check : 30 s later, report crashes (am_crash / FATAL), process starts and the VPN tunnel lines since prep.
#   wake  : wake the headset (KEYCODE_WAKEUP + prox_close), then decoded fps and tun0 TX/RX over 10 s.
# Output: out/replug_<label>.{logcat,txt}
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
PHASE=$1
case "$PHASE" in
  prep)
    APK=$2; LABEL=$3
    [ -f "$APK" ] && [ -n "$LABEL" ] || { echo "usage: replug_check.sh prep <apk> <label>"; exit 1; }
    OUT="$QUEST_OUT/replug_$LABEL"
    qadb shell am force-stop "$PKG"
    qadb install -r "$(cygpath -w "$APK")" | tail -1
    quest_prox_close
    quest_start_xr -W | grep -E "Status|Complete"
    sleep 12
    qadb shell setprop debug.oculus.guardian_pause 0
    qadb shell am broadcast -a com.oculus.vrpowermanager.automation_disable >/dev/null
    qadb logcat -c
    (timeout 900 "$ADB_SH" -s "$QUEST" logcat -b events -b main -b crash -v epoch > "$OUT.logcat" 2>&1 &)
    qadb shell input keyevent KEYCODE_SLEEP
    echo "$(date '+%T') $LABEL: apk $(md5sum "$APK" | cut -c1-12) installed, XR started, headset asleep; waiting 90 s"
    sleep 90
    echo "$(date '+%T') $LABEL: READY -> user: unplug the RTL, wait 10 s, plug it back in (do not wake the headset)"
    ;;
  check)
    LABEL=$2; OUT="$QUEST_OUT/replug_$LABEL"
    {
      echo "# $LABEL check $(date '+%T')"
      grep -E "am_crash|FATAL EXCEPTION|BackgroundServiceStartNotAllowed" "$OUT.logcat" | grep -i pixelpilot | cut -c1-220
      echo "crashes: $(grep -c "am_crash.*pixelpilot.xr" "$OUT.logcat")"
      echo "process starts: $(grep -c "am_proc_start.*pixelpilot.xr" "$OUT.logcat")"
      grep -E "WfbNgVpnService: VPN tunnel (started|stopped)|USB_DEVICE_ATTACHED|Background start not allowed" "$OUT.logcat" | cut -c1-160 | tail -8
    } | tee "$OUT.txt"
    ;;
  wake)
    LABEL=$2; OUT="$QUEST_OUT/replug_$LABEL"
    qadb shell input keyevent KEYCODE_WAKEUP
    quest_prox_close
    sleep 20
    P=$(qadb shell pidof "$PKG")
    {
      echo "# $LABEL wake $(date '+%T') pid ${P:-none}"
      A=$(qadb shell "grep tun0 /proc/net/dev"); sleep 10; B=$(qadb shell "grep tun0 /proc/net/dev")
      echo "tun0 before: ${A:-absent}"; echo "tun0 after : ${B:-absent}"
      qadb logcat -d -t 400 --pid="$P" 2>/dev/null | grep -oE "FPS:[0-9.]+|Decoding:[0-9.]+" | tail -4 | tr '\n' ' '; echo
      echo "crashes since prep: $(grep -c "am_crash.*pixelpilot.xr" "$OUT.logcat")"
    } | tee -a "$OUT.txt"
    ;;
  *) echo "usage: replug_check.sh prep <apk> <label> | check <label> | wake <label>"; exit 1 ;;
esac
