#!/bin/bash
# Usage: tunnel_probe.sh <label> [seconds=20] [ping]
# One observation window of the running app on the real link: decoded fps and link quality from the app's log,
# tun0 RX/TX packet deltas (RX = air -> Quest through the tunnel, TX = Quest -> air), and with "ping" a 10-packet
# ping to the air unit's tunnel end 10.5.0.10 at the start of the window. Output: out/tunnel_probe_<label>.txt
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1; SECS=${2:-20}; PING=$3
P=$(qadb shell pidof "$PKG")
[ -n "$P" ] || { echo "app not running"; exit 1; }
tun() { qadb shell "grep tun0 /proc/net/dev" | awk '{print $3, $11}'; }  # rx_packets tx_packets
{
  echo "# $LABEL $(date '+%F %T') pid $P window ${SECS}s"
  T0=$(qadb shell date +%s | tr -d '\r'); A=$(tun)
  if [ "$PING" = "ping" ]; then
    qadb shell "ping -c 10 -i 0.5 -W 1 10.5.0.10" 2>&1 | grep -E "packets transmitted|rtt|min/avg" | sed 's/^/  ping: /'
  fi
  sleep "$SECS"
  B=$(tun)
  L=$(qadb logcat -d -v epoch --pid="$P" | awk -v t="$T0" '$1+0 >= t')
  echo "  fps: $(echo "$L" | grep -oE 'VideoDecoder: FPS:[0-9.]+' | sed 's/.*://' | tr '\n' ' ')"
  echo "  quality mean: $(echo "$L" | grep -oE 'quality -?[0-9]+' | awk '{s+=$2; n++} END{if (n) printf "%.0f (n=%d)", s/n, n; else print "n/a"}')"
  echo "  tun0 rx/tx packets: ${A:-absent} -> ${B:-absent}" | awk '{print}'
  if [ -n "$A" ] && [ -n "$B" ]; then
    set -- $A $B
    echo "  tun0 delta: rx +$(( $3 - $1 )) tx +$(( $4 - $2 )) in ${SECS}s"
  fi
} 2>&1 | tee "$QUEST_OUT/tunnel_probe_$LABEL.txt"
