#!/bin/sh
# mode_ab 2026-09-30: G2G <= 40 ms audit §5 (pixelpilot-xr docs/xr/research/2026-09-29-g2g-40ms-audit.md).
# Part A: video modes with everything else fixed (17 dBm, FEC 4/8, STBC/LDPC, 20 MHz, long GI, no -R, rmem untouched).
# Part C: race on ch157 vs ch165. RAM only: /tmp/waybeam.json + start.sh, wfb_tx_cmd set_radio, iw txpower, the L1 chan verb.
# STEPS = "air_epoch:label ..." (air clock). Labels:
#   race = 480p167 2M MCS2 | b2 = 720p120 2M MCS2 | h8 = 720p120 8M MCS7 | h12 = 720p120 12M MCS7 | hd = 1080p90 16M MCS7
#   c157 / c165 = race on that channel (the Quest follows by its own pref_ab schedule)
# END: race json, 2000 kbps, MCS2, 12 dBm, ch165 (the boot default). Log: /tmp/mode_ab.log.
STEPS=${STEPS:?"air_epoch:label ..."}
ENDAT=${ENDAT:?air epoch}
LOG=/tmp/mode_ab.log
LM=/opt/linkmode; TXCMD=$LM/wfb_tx_cmd; SETFEC=$LM/wfb_setfec; API=http://127.0.0.1/api/v1; TXLOG=/tmp/wfbtx.log
J1080=/etc/waybeam.json.bak-1080p90-20260927; JRACE=/etc/waybeam.default.json; J720=/tmp/waybeam.720p120.json
log() { echo "$*" >> $LOG; }
temp() { sed 's/[^0-9]//g' /sys/devices/virtual/mstar/msys/TEMP_R; }
set_pw() { T=$1; C=$(iw dev wlan0 info | awk '/txpower/{printf "%d",$2}')
  while [ "$C" != "$T" ]; do [ "$C" -lt "$T" ] && C=$((C+2)) || C=$T; [ "$C" -gt "$T" ] && C=$T
    iw dev wlan0 set txpower fixed "$((C*100))"; usleep 300000; done; }
vpid() { for p in $(pidof wfb_tx); do tr '\0' ' ' < /proc/$p/cmdline | grep -q -- '-p 0 ' && echo $p; done; }
chan() { iw dev wlan0 info | awk '/channel/{print $2}'; }
jget() { wget -qO- $API/config.json | tr -d ' \n' | grep -o "\"$1\":[^,}]*" | head -1 | cut -d: -f2 | tr -d '"'; }
rb() { echo "ch=$(chan) $($TXCMD 9000 get_radio | grep -o 'mcs_index=[0-9]*') $($TXCMD 9000 get_fec | tr '\n' ' ')mode=$(jget mode) size=$(jget size) fps=$(jget fps) br=$(jget bitrate) txp=$(iw dev wlan0 info | awk '/txpower/{print $2}') rmem=$(cat /proc/sys/net/core/rmem_default)/$(cat /proc/sys/net/core/rmem_max) vpid=$(vpid) wb=$(pidof waybeam) bcn=\"$(tail -1 /tmp/linkmode-bcn.log 2>/dev/null)\""; }
nl() { wc -l < $TXLOG 2>/dev/null || echo 0; }
drops() { tail -n +"$(($1 + 1))" $TXLOG 2>/dev/null | awk -F'\t' '$2=="PKT"{split($3,a,":"); d+=a[6]; i+=a[4]} $2=="TX_ANT"{split($4,b,":"); ad+=b[2]} END{printf "drop=%d inj=%d ant_drop=%d", d, i, ad}'; }
txdrop() { cat /sys/class/net/wlan0/statistics/tx_dropped; }
radio() { $TXCMD 9000 set_radio -B 20 -G long -S 1 -L 1 -N 1 -M "$1" >/dev/null 2>&1; }
# json + restart only when the file changes; bitrate always by API (RAM)
video() { J=$1; BR=$2
  if [ "$CURJ" != "$J" ]; then cp "$J" /tmp/waybeam.json && /opt/waybeam/start.sh >/tmp/mode_ab.start.log 2>&1; CURJ=$J; sleep 2; fi
  wget -qO- "$API/set?video0.bitrate=$BR" >/dev/null 2>&1; }
# alink/vmoded start ~30 s after boot (linkmode); a late one overrides the radio (R25 try 1, 2026-09-30: MCS1 at 25 Mbit/s)
late_kill() { A=$(pidof alink_air vmoded); [ -n "$A" ] && { kill $A; log "KILLED late alink/vmoded pids=$A"; }; }
apply() { late_kill; case "$1" in
  race|c157|c165) video $JRACE 2000; radio 2;;
  b2)  video $J720 2000; radio 2;;
  h8)  video $J720 8000; radio 7;;
  h12) video $J720 12000; radio 7;;
  hd)  video $J1080 16000; radio 7;;
  *) log "ERR unknown label $1"; return 1;; esac
  case "$1" in c157) WANT=157;; *) WANT=165;; esac
  if [ "$(chan)" != "$WANT" ]; then T0=$(date +%s); V=$($LM/linkmode-air.sh chan "$WANT" 2>&1 | tail -1); log "CHAN -> $WANT took=$(( $(date +%s) - T0 ))s verdict=$V"; fi
  set_pw 17; }
revert() {
  [ -n "$REV" ] && return; REV=1
  [ "$(chan)" = 165 ] || $LM/linkmode-air.sh chan 165 >/dev/null 2>&1
  CURJ=""; video $JRACE 2000; radio 2; set_pw 12
  log "END epoch=$(date +%s) $(rb) json=$(md5sum /tmp/waybeam.json | cut -c1-8) tx_dropped=$(txdrop) temp=$(temp)"
}
trap 'log "ABORT_SIGNAL epoch=$(date +%s)"; revert; exit 1' INT TERM HUP
: > $LOG
# 720p120 = the 1080p90 json with sensor mode 6, 120 fps, 1280x720 (vmoded preset1 "balanced": mode=6 size=1280x720 fps=120)
sed -e 's/"mode": *2\([^0-9]\|$\)/"mode": 6\1/' -e 's/"fps": *90\([^0-9]\)/"fps": 120\1/' -e 's/"size": *"1920x1080"/"size": "1280x720"/' $J1080 > $J720
log "JSON 1080=$(md5sum $J1080 | cut -c1-8) race=$(md5sum $JRACE | cut -c1-8) 720=$(md5sum $J720 | cut -c1-8) diff=$(diff $J1080 $J720 | grep -c '^>')"
A=$(pidof alink_air vmoded); [ -n "$A" ] && { kill $A; sleep 1; log "stopped alink/vmoded pids=$A"; }
$SETFEC 4 8 9000 >/dev/null 2>&1
log "PRE epoch=$(date +%s) $(rb) fec=$($TXCMD 9000 get_fec | tr '\n' ' ') tx_dropped=$(txdrop) temp=$(temp)"
PE=""; PN=0
for S in $STEPS; do
  T=${S%%:*}; L=${S##*:}
  while [ "$(date +%s)" -lt "$T" ]; do usleep 200000; done
  [ -n "$PE" ] && log "STEP $PL epoch=$PE $(drops $PN) tx_dropped_d=$(( $(txdrop) - PD )) temp=$(temp) $(rb)"
  apply "$L"
  PE=$(date +%s); PN=$(nl); PD=$(txdrop); PL=$L; log "SET $L epoch=$PE $(rb)"
done
while [ "$(date +%s)" -lt "$ENDAT" ]; do usleep 200000; done
log "STEP $PL epoch=$PE $(drops $PN) tx_dropped_d=$(( $(txdrop) - PD )) temp=$(temp) $(rb)"
revert
