#!/bin/bash
# Usage: link_probe.sh <label> [seconds=20]
# One wfb link-health sample on the running XR app, for diagnosing a degraded link (e.g. before/after an RTL
# replug or a home-Wi-Fi change): keeps the display awake only for the sample (prox_close, then
# automation_disable), prints the Quest's own Wi-Fi association (SSID, frequency, RSSI) and runs link_measure.sh
# (decoded fps, link quality, recovered/lost per s, SNR). Appends one line to out/link_probe.log.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; SECS=${2:-20}
[ -n "$LABEL" ] || { echo "usage: link_probe.sh <label> [seconds]"; exit 1; }
mkdir -p "$QUEST_OUT"
quest_prox_close
sleep 4
WIFI=$(qadb shell 'dumpsys wifi | grep -m1 mWifiInfo' 2>/dev/null | grep -oE 'SSID: "[^"]+"|Frequency: [0-9]+MHz|RSSI: -?[0-9]+' | tr '\n' ' ')
M=$(bash link_measure.sh "$SECS" "$LABEL")
qadb shell am broadcast -a com.oculus.vrpowermanager.automation_disable >/dev/null
echo "$(date '+%F %T') | $M | wifi: $WIFI| pid $(qadb shell pidof "$PKG")" | tee -a "$QUEST_OUT/link_probe.log"
