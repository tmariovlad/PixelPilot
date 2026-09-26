#!/bin/bash
# Measure the running real link on the Quest for N seconds (default 10) without restarting the app:
# decoded fps, mean link quality, and the uplink line's lost/recovered packets per second + SNR.
# Usage: link_measure.sh [seconds] [label]
. "$(dirname "$0")/quest_env.sh" || exit 1
SECS=${1:-10}; LABEL=${2:-run}
P=$("$ADB" -s "$QUEST" shell pidof "$PKG")
[ -n "$P" ] || { echo "$LABEL: app not running"; exit 1; }
"$ADB" -s "$QUEST" logcat -c
sleep "$SECS"
L=$("$ADB" -s "$QUEST" logcat -d --pid="$P")
F=$(echo "$L" | grep -oE "N Decoded Frames:[0-9]+" | sed 's/.*://')
FPS=$(echo "$F" | awk 'NR==1{a=$1} {b=$1} END{if (NR>1) printf "%.0f", (b-a)/((NR-1)*5); else print "n/a"}')
Q=$(echo "$L" | grep -oE "quality -?[0-9]+" | awk '{s+=$2; n++} END{if(n) printf "%.0f", s/n; else print "n/a"}')
M=$(echo "$L" | grep -oE "message [0-9]+:[^ ]+" | awk -F: '{r+=$4; l+=$5; s+=$7; n++} END{if(n) printf "rec/s=%.0f lost/s=%.0f snr=%.1f", r/n, l/n, s/n; else print "no uplink lines"}')
echo "$LABEL | decoded_fps=$FPS | quality=$Q | $M"
