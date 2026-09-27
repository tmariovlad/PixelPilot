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
    qadb shell date +%s | tr -d '' > "$OUT.since"   # events/crash buffers keep older lines: filter by this time
    (timeout 3600 "$ADB_SH" -s "$QUEST" logcat -b events -b main -b crash -v epoch > "$OUT.logcat" 2>&1 &)
    qadb shell input keyevent KEYCODE_SLEEP
    echo "$(date '+%T') $LABEL: apk $(md5sum "$APK" | cut -c1-12) installed, XR started, headset asleep; waiting 90 s"
    sleep 90
    echo "$(date '+%T') $LABEL: READY -> user: unplug the RTL, wait 10 s, plug it back in (do not wake the headset)"
    ;;
  check)
    LABEL=$2; OUT="$QUEST_OUT/replug_$LABEL"
    SINCE=$(cat "$OUT.since")
    # the live capture can miss lines (adb reconnects while asleep): take the device buffers too
    qadb logcat -d -b events -b main -b crash -v epoch > "$OUT.after" 2>/dev/null
    EV=$(cat "$OUT.logcat" "$OUT.after" | awk -v t="$SINCE" '$1+0 >= t' | sort -u)
    {
      echo "# $LABEL check $(date '+%T') (events since $SINCE)"
      echo "$EV" | grep -E "am_crash|wm_create_activity|am_proc_start|am_proc_died" | grep pixelpilot.xr | cut -c1-200
      echo "crashes: $(echo "$EV" | grep -c "am_crash.*pixelpilot.xr")"
      echo "USB attach -> activity: $(echo "$EV" | grep -c "wm_create_activity.*pixelpilot.xr.*USB_DEVICE_ATTACHED")"
      echo "$EV" | grep -E "WfbNgVpnService: VPN tunnel (started|stopped)" | cut -c1-120 | tail -4
    } | tee "$OUT.txt"
    ;;
  wake)
    LABEL=$2; OUT="$QUEST_OUT/replug_$LABEL"
    qadb shell input keyevent KEYCODE_WAKEUP
    quest_prox_close
    # Horizon takes a while to hand the display back to the XR activity: wait up to 60 s for decoded frames
    for _ in $(seq 1 12); do
      sleep 5
      P=$(qadb shell pidof "$PKG")
      [ -n "$P" ] && qadb logcat -d -t 200 --pid="$P" 2>/dev/null | grep -q "VideoDecoder: FPS" && break
    done
    P=$(qadb shell pidof "$PKG")
    {
      echo "# $LABEL wake $(date '+%T') pid ${P:-none}"
      A=$(qadb shell "grep tun0 /proc/net/dev"); sleep 10; B=$(qadb shell "grep tun0 /proc/net/dev")
      echo "tun0 before: ${A:-absent}"; echo "tun0 after : ${B:-absent}"
      qadb logcat -d -t 400 --pid="$P" 2>/dev/null | grep -oE "FPS:[0-9.]+|Decoding:[0-9.]+" | tail -4 | tr '\n' ' '; echo
      qadb logcat -d -b events -v epoch > "$OUT.after" 2>/dev/null
      echo "crashes since prep: $(cat "$OUT.logcat" "$OUT.after" | awk -v t="$(cat "$OUT.since")" '$1+0 >= t' | sort -u | grep -c "am_crash.*pixelpilot.xr")"
    } | tee -a "$OUT.txt"
    ;;
  *) echo "usage: replug_check.sh prep <apk> <label> | check <label> | wake <label>"; exit 1 ;;
esac
