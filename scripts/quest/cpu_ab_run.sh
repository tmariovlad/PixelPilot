#!/bin/bash
# Usage: cpu_ab_run.sh <apk> <label> [seconds=20]
# One state of an app-build A/B on the real link: install the given debug APK (the release app is never
# touched), start XR, let it settle 15 s, then over one window measure CPU per thread (cpu_threads.py),
# decoded fps + decode ms (VideoDecoder averages) and link quality / uplink loss. Output: out/cpu_<label>.txt
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
APK=$1; LABEL=$2; SECS=${3:-20}
[ -f "$APK" ] && [ -n "$LABEL" ] || { echo "usage: cpu_ab_run.sh <apk> <label> [seconds]"; exit 1; }
mkdir -p "$QUEST_OUT"; OUT="$QUEST_OUT/cpu_$LABEL.txt"
{
  echo "# $LABEL $(date '+%F %T') apk md5 $(md5sum "$APK" | cut -c1-12)"
  qadb install -r "$(cygpath -w "$APK")" | tail -1
  qadb shell am force-stop "$PKG"; sleep 1
  quest_prox_close
  quest_start_xr -W | grep -E "Status|Complete"
  sleep 15
  P=$(qadb shell pidof "$PKG")
  qadb logcat -c
  python3 cpu_threads.py "$SECS" 6
  L=$(qadb logcat -d --pid="$P")
  echo "$L" | grep -E "Decoding:" | tail -2 | sed -E 's/.*(Decoding:[0-9.]+).*/  \1 ms/'
  echo "$L" | grep -oE "FPS:[0-9.]+" | tail -3 | tr '\n' ' '; echo
  echo "$L" | grep -oE "quality -?[0-9]+" | awk '{s+=$2; n++} END{if(n) printf "  quality mean %.0f (n=%d)\n", s/n, n}'
  echo "$L" | grep -oE "message [0-9]+:[^ ]+" | awk -F: '{l+=$5; s+=$7; n++} END{if(n) printf "  uplink lost/s %.1f snr %.1f (n=%d)\n", l/n, s/n, n}'
} 2>&1 | tee "$OUT"
