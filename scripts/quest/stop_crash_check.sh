#!/bin/bash
# Usage: stop_crash_check.sh relaunch|sleepwake [N=2]
# Does the XR app survive repeated XR session stops? (AudioDecoder::stopAudio closed the same AAudio stream twice and
# aborted with SIGABRT on the second stop; fixed in c4ee807, see docs/xr/troubleshooting.md.)
#   relaunch  : `am start` XR mode over the running instance, N times
#   sleepwake : display sleep -> wake (+ prox_close), N times; the old build aborts on the SECOND sleep
# Per iteration: pid before/after, SIGABRT lines for the app in the crash buffer since the iteration began,
# and whether video was (re)attached to the compositor surface. Reads logcat with -t <time>; clears nothing.
. "$(dirname "$0")/quest_env.sh" || exit 1
MODE=$1; N=${2:-2}
case "$MODE" in relaunch|sleepwake) ;; *) echo "usage: $0 relaunch|sleepwake [N]" >&2; exit 2 ;; esac

now() { qadb shell "date +'%m-%d %H:%M:%S.000'" | tr -d '\r'; }  # quoted: adb shell re-splits on spaces
pid() { qadb shell pidof "$PKG" | tr -d '\r'; }

if [ -z "$(pid)" ]; then quest_prox_close; quest_start_xr >/dev/null; sleep 12; fi
echo "mode=$MODE N=$N start pid=$(pid)"
for i in $(seq 1 "$N"); do
  t=$(now); before=$(pid)
  if [ "$MODE" = relaunch ]; then
    quest_start_xr >/dev/null
    sleep 15
  else
    qadb shell input keyevent KEYCODE_SLEEP; sleep 6
    qadb shell input keyevent KEYCODE_WAKEUP; quest_prox_close; sleep 15
  fi
  after=$(pid)
  aborts=$(qadb logcat -d -b crash -t "$t" | grep -c "Fatal signal 6.*c.pixelpilot.xr")
  attached=$(qadb logcat -d -t "$t" | grep -c "video attached to the compositor surface")
  echo "iter $i: pid $before -> ${after:-none}  SIGABRT=$aborts  video_attached=$attached  since $t"
done
