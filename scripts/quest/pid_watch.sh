#!/bin/bash
# Usage: pid_watch.sh <until PC epoch> [interval_s=60]
# Watches the XR app during a detached capture without streaming anything: one `pidof` over adb per interval. Prints
# "<PC epoch> pid=<pid>" per check and exits 0 at <until>. Exits 1 at once when the app is gone or its pid changed (a
# kill or a restart), with a GONE/CHANGED line, so a background run of this script wakes the caller the moment the
# capture stops being worth anything. ALLOW_RESTART=1 (a run that relaunches XR per step, e.g. pref_ab.sh): a new pid is
# only logged, and GONE needs two checks in a row, since a relaunch leaves ~1-2 s without the process.
# Written after 2026-09-30, when a low-memory kill at the end of a 46 min gate went unnoticed for 19 min and the next
# block captured nothing (docs/xr/link-envelope.md, rig slot 2026-09-30).
. "$(dirname "$0")/quest_env.sh" || exit 1
UNTIL=$1; STEP=${2:-60}
[ -n "$UNTIL" ] || { sed -n 2,9p "$0"; exit 2; }
PKG=com.openipc.pixelpilot.xr
FIRST=$(qadb shell pidof "$PKG" | tr -d '\r')
echo "$(date +%s) pid=${FIRST:-none} (start)"
[ -n "$FIRST" ] || { echo "$(date +%s) GONE at start"; exit 1; }
while [ "$(date +%s)" -lt "$UNTIL" ]; do
  LEFT=$(( UNTIL - $(date +%s) ))
  sleep $(( LEFT < STEP ? LEFT : STEP ))   # never past <until> (a 60 s interval once overshot a 5 s watch by 56 s)
  P=$(qadb shell pidof "$PKG" | tr -d '\r')
  echo "$(date +%s) pid=${P:-none}"
  if [ -z "$P" ]; then
    MISS=$(( ${MISS:-0} + 1 ))
    if [ "${ALLOW_RESTART:-0}" != 1 ] || [ "$MISS" -ge 2 ]; then echo "$(date +%s) GONE"; exit 1; fi
    continue
  fi
  MISS=0
  if [ "$P" != "$FIRST" ]; then
    [ "${ALLOW_RESTART:-0}" = 1 ] || { echo "$(date +%s) CHANGED $FIRST -> $P"; exit 1; }
    echo "$(date +%s) restarted $FIRST -> $P (allowed)"; FIRST=$P
  fi
done
echo "$(date +%s) until reached, app alive"
exit 0
