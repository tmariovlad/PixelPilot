#!/bin/bash
# Usage: pid_watch.sh <until PC epoch> [interval_s=60]
# Watches the XR app during a detached capture without streaming anything: one `pidof` over adb per interval. Prints
# "<PC epoch> pid=<pid>" per check and exits 0 at <until>. Exits 1 at once when the app is gone or its pid changed (a
# kill or a restart), with a GONE/CHANGED line, so a background run of this script wakes the caller the moment the
# capture stops being worth anything. Written after 2026-09-30, when a low-memory kill at the end of a 46 min gate went
# unnoticed for 19 min and the next block captured nothing (docs/xr/link-envelope.md, rig slot 2026-09-30).
. "$(dirname "$0")/quest_env.sh" || exit 1
UNTIL=$1; STEP=${2:-60}
[ -n "$UNTIL" ] || { sed -n 2,7p "$0"; exit 2; }
PKG=com.openipc.pixelpilot.xr
FIRST=$(qadb shell pidof "$PKG" | tr -d '\r')
echo "$(date +%s) pid=${FIRST:-none} (start)"
[ -n "$FIRST" ] || { echo "$(date +%s) GONE at start"; exit 1; }
while [ "$(date +%s)" -lt "$UNTIL" ]; do
  sleep "$STEP"
  P=$(qadb shell pidof "$PKG" | tr -d '\r')
  echo "$(date +%s) pid=${P:-none}"
  [ -n "$P" ] || { echo "$(date +%s) GONE"; exit 1; }
  [ "$P" = "$FIRST" ] || { echo "$(date +%s) CHANGED $FIRST -> $P"; exit 1; }
done
echo "$(date +%s) until reached, app alive"
exit 0
