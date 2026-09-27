#!/bin/bash
# Usage: quest_tx_log.sh [seconds=240] [out.txt=out/quest_tx.txt]
# Streams the Quest RTL's uplink injections during a trace: one line per injected frame (devourer "TX DESC" log line),
# written as its Quest epoch. Streaming, because a whole run (~50 lines/s plus PKT_LOST noise) can overflow the logcat
# buffer before a later dump. Per-step rate: ab_link.py --quest-tx out.txt. Same signal as tunnel_cycle.sh's txrate.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
SECS=${1:-240}; OUT=${2:-$QUEST_OUT/quest_tx.txt}
: > "$OUT"
timeout "$SECS" "$ADB_SH" -s "$QUEST" logcat -T 1 -v epoch -s devourer:D | grep --line-buffered "TX DESC" \
  | awk '{ print $1; fflush() }' >> "$OUT"
echo "wrote $OUT ($(wc -l < "$OUT") TX frames in ${SECS} s)"
