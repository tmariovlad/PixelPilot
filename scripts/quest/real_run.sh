#!/bin/bash
# Usage: real_run.sh <tag> [lever=true ...]
# Relaunch the XR app on the real link (gs.key = $GS_KEY, channel $WFB_CHANNEL) with bool levers, report
# the decoder keys actually applied, the last two decode times and the decoded-frame count.
. "$(dirname "$0")/quest_env.sh" || exit 1
cd "$QUEST_DIR" || exit 1
TAG=$1; shift
python3 set_link_prefs.py "$GS_KEY" "$WFB_CHANNEL" "$@" > /dev/null
quest_guardian_pause 1
quest_prox_close
qadb logcat -c
quest_start_xr >/dev/null
sleep 16
P=$(qadb shell pidof "$PKG")
L=$(qadb logcat -d --pid=$P)
KEYS=$(echo "$L" | grep -m1 -oE "Configuring decoder [^:]*:.*" | grep -oE "(low-latency|vendor\.qti-ext-dec-picture-order\.enable|operating-rate|priority)[^,]*" | tr '\n' ' ')
DEC=$(echo "$L" | grep -oE "\| Decoding:[0-9.]+" | tail -2 | tr '\n' ' ')
FR=$(echo "$L" | grep -oE "N Decoded Frames:[0-9]+" | tail -1)
echo "$TAG | keys: $KEYS | $DEC | $FR"
