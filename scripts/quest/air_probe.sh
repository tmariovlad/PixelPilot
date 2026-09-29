#!/bin/sh
# Read-only probe of the air unit for slot_watch.py (fallback while air_health is not deployed). Fed to `ssh air sh -s --
# <prev_wfb_lines> <slow>` on stdin, so nothing is quoted through a shell chain. Prints key=value lines; an empty value
# means the source is missing. No waybeam `set`, no register access (the 0x550 value comes from bcn_off's own log line;
# openipc-…-40: air_health will be the one 0x550 sampler). <slow>=1 adds the radio / iw / config reads (every ~30 s).
PREV=${1:--1}; SLOW=${2:-1}
API=http://127.0.0.1/api/v1
echo "now=$(date +%s)"
echo "uptime=$(cut -d' ' -f1 /proc/uptime)"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
echo "temp=$(sed 's/[^0-9]//g' /sys/devices/virtual/mstar/msys/TEMP_R 2>/dev/null)"
echo "tx_packets=$(cat /sys/class/net/wlan0/statistics/tx_packets 2>/dev/null)"
# wfb_tx "<ts>\tPKT\t<fec_to>:<p_in>:<b_in>:<p_inj>:<b_inj>:<p_drop>:<p_trunc>" lines (wfb-ng tx.cpp:826) added since
# the previous poll, at most 50; PREV=-1 (first poll) or a shrunk file (rotation) counts nothing, only sets the mark.
N=$(wc -l < /tmp/wfbtx.log 2>/dev/null || echo 0)
echo "wfb_lines=$N"
if [ "$PREV" -ge 0 ] && [ "$N" -ge "$PREV" ]; then
  NEW=$((N - PREV)); [ "$NEW" -gt 50 ] && NEW=50
  if [ "$NEW" -gt 0 ]; then
    tail -n "$NEW" /tmp/wfbtx.log | awk -F'\t' '$2=="PKT"{split($3,a,":"); n++; d+=a[6]; i+=a[4]}
      END{printf "wfb_drop=%d\nwfb_inj=%d\nwfb_pkt_lines=%d\n", d, i, n}'
  else
    printf 'wfb_drop=0\nwfb_inj=0\nwfb_pkt_lines=0\n'
  fi
fi
echo "wb_verbose=$(tail -n 20 /tmp/waybeam.log 2>/dev/null | grep 'verbose.* fps .* kbps' | tail -n 1)"
echo "idr_stats=$(wget -qO- -T 2 $API/idr/stats 2>/dev/null | tr -d '\n')"
echo "bcn=$(tail -n 1 /tmp/linkmode-bcn.log 2>/dev/null)"
if [ "$SLOW" = 1 ]; then
  CFG=$(wget -qO- -T 2 $API/config.json 2>/dev/null)
  echo "cfg_bitrate=$(echo "$CFG" | grep -o '"bitrate": *[0-9]*' | head -n 1 | grep -o '[0-9]*$')"
  echo "cfg_fps=$(echo "$CFG" | grep -o '"fps": *[0-9]*' | head -n 1 | grep -o '[0-9]*$')"
  echo "radio=$(/opt/linkmode/wfb_tx_cmd 9000 get_radio 2>/dev/null | tr '\n' ' ')"
  echo "fec=$(/opt/linkmode/wfb_tx_cmd 9000 get_fec 2>/dev/null | tr '\n' ' ')"
  echo "iw=$(iw dev wlan0 info 2>/dev/null | tr '\n\t' '  ')"
fi
