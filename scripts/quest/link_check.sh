#!/bin/bash
# Usage: link_check.sh [wait_s=12]
# Launch the XR app on the Quest (RTL8812AU on USB-C, wfb-ng) and report what the link and decoder do:
# the PC's Wi-Fi state, wfb link-quality lines (-1024 = no wfb packets), decoder/decrypt log lines.
. "$(dirname "$0")/quest_env.sh" || exit 1
WAIT=${1:-12}
netsh wlan show interfaces 2>&1 | grep -aE " State|SSID " | tr -d '\r' | head -2
quest_guardian_pause 1
quest_prox_close
qadb shell am force-stop "$PKG"
qadb logcat -c
quest_start_xr | tail -1
sleep "$WAIT"
P=$(qadb shell pidof "$PKG"); echo "pid=$P"
L=$(qadb logcat -d --pid=$P)
echo "quality -1024 lines: $(echo "$L" | grep -c 'quality -1024')  other quality: $(echo "$L" | grep -E 'quality -?[0-9]+' | grep -vc 'quality -1024')"
echo "$L" | grep -E "quality -?[0-9]+" | grep -v "quality -1024" | tail -3 | cut -c1-160
echo "$L" | grep -iE "Decoded Frames|Decoding:|Configuring decoder|decrypt|session key|FATAL" | tail -8 | cut -c1-200
