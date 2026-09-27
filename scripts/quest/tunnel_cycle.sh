#!/bin/bash
# Usage: tunnel_cycle.sh <cycles> [label]
# Stops and restarts the app's VPN tunnel by putting the headset to sleep and waking it (XR pauses -> unbind ->
# tunnel stopped; resume -> rebind -> tunnel started), with the app already running. Per cycle it reports:
#   asleep: tun0 present?, UDP port 8000 (0x1F40) still bound by the app's uid?
#   awake : tun0 present?, decoded fps
# and at the end the EBADF lines the app logged during the run. Output: out/tunnel_cycle_<label>.txt
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
N=${1:-2}; LABEL=${2:-run}; OUT="$QUEST_OUT/tunnel_cycle_$LABEL.txt"
P=$(qadb shell pidof "$PKG")
[ -n "$P" ] || { echo "app not running"; exit 1; }
UID_APP=$(qadb shell "stat -c %u /proc/$P" | tr -d '\r')
SINCE=$(qadb shell date +%s | tr -d '\r')
# the main buffer rotates within minutes (quality lines at 10 Hz): capture the service's own lines live
LOG="$QUEST_OUT/tunnel_cycle_$LABEL.logcat"
(timeout 900 "$ADB_SH" -s "$QUEST" logcat -v epoch WfbNgVpnService:V '*:S' > "$LOG" 2>&1 &)
udp8000() { qadb shell "cat /proc/net/udp /proc/net/udp6" | awk -v u="$UID_APP" '$8 == u && toupper($2) ~ /:1F40$/' | wc -l; }
udp8001() { qadb shell "cat /proc/net/udp /proc/net/udp6" | awk -v u="$UID_APP" '$8 == u && toupper($2) ~ /:1F41$/' | wc -l; }
# uplink alive = devourer injects frames (one "TX DESC" line per frame) during the 10 s after the call
txrate() { local t0; t0=$(qadb shell date +%s | tr -d '\r'); sleep 10
  qadb logcat -d -v epoch -s devourer:D | awk -v t="$t0" '$1+0 >= t' | grep -c "TX DESC" | awk '{printf "%.1f", $1/10}'; }
tun0() { qadb shell "grep -c tun0 /proc/net/dev" | tr -d '\r'; }
fps() { qadb logcat -d -t 300 --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE "VideoDecoder: FPS:[0-9.]+" | tail -1; }
{
  echo "# $LABEL $(date '+%F %T') pid $P uid $UID_APP cycles $N; before: udp8001_sockets=$(udp8001) uplink_tx_per_s=$(txrate)"
  for i in $(seq 1 "$N"); do
    qadb shell input keyevent KEYCODE_SLEEP
    sleep 12
    echo "cycle $i asleep: tun0=$(tun0) udp8000_sockets=$(udp8000) udp8001_sockets=$(udp8001)"
    qadb shell input keyevent KEYCODE_WAKEUP
    quest_prox_close
    for _ in $(seq 1 12); do sleep 5; F=$(fps); [ -n "$F" ] && [ "$(tun0)" = "1" ] && break; done
    sleep 6; F=$(fps)
    echo "cycle $i awake : tun0=$(tun0) udp8000_sockets=$(udp8000) udp8001_sockets=$(udp8001) uplink_tx_per_s=$(txrate) ${F:-no FPS line}"
  done
  P2=$(qadb shell pidof "$PKG")
  echo "pid after: ${P2:-none} (same process: $([ "$P" = "$P2" ] && echo yes || echo no))"
  sleep 2
  echo "EBADF lines since start: $(awk -v t="$SINCE" '$1+0 >= t' "$LOG" | grep -c EBADF)"
  echo "tunnel started / stopped lines: $(grep -c 'VPN tunnel started' "$LOG") / $(grep -c 'VPN tunnel stopped' "$LOG")"
  echo "late-stop warnings: $(grep -c 'still running after' "$LOG")"
} 2>&1 | tee "$OUT"
