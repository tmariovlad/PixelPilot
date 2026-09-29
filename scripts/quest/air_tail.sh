#!/bin/sh
# Read-only poll of the air for slot_watch.py when air_health.sh runs (openipc-…-40, 00-DESIGN-air-health.md): the
# air's clock, then the last lines of the ring (.1 first, so the output stays chronological across a rotation). The
# watcher keeps only the lines it has not seen. Fed to `ssh air sh -s -- <slow> <lines>` on stdin. air_health samples
# everything else; the only extra read is waybeam's configured bitrate/fps (a read-only GET air_health leaves out),
# every ~30 s. No waybeam `set`, no register access.
SLOW=${1:-0}; N=${2:-15}
echo "now=$(date +%s)"
echo "uptime=$(cut -d' ' -f1 /proc/uptime)"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
if [ "$SLOW" = 1 ]; then
  CFG=$(wget -qO- -T 2 http://127.0.0.1/api/v1/config.json 2>/dev/null)
  echo "cfg_bitrate=$(echo "$CFG" | grep -o '"bitrate": *[0-9]*' | head -n 1 | grep -o '[0-9]*$')"
  echo "cfg_fps=$(echo "$CFG" | grep -o '"fps": *[0-9]*' | head -n 1 | grep -o '[0-9]*$')"
fi
tail -n "$N" /tmp/air_health.log.1 2>/dev/null
tail -n "$N" /tmp/air_health.log 2>/dev/null
