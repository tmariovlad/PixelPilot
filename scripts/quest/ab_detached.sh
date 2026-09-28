#!/bin/bash
# Usage: ab_detached.sh start <label> [seconds=420] | ab_detached.sh pull <label>
# Like ab_long.sh, but the capture survives adb dropping mid-run (e.g. the Quest changing Wi-Fi network, which moves
# adb-over-Wi-Fi): perfetto runs detached on the Quest (--background) and the uplink TX lines go to a logcat file on
# the Quest instead of a streaming adb logcat. "start" measures the Quest-minus-PC offset, starts both and returns;
# "pull" (after the run, adb back) fetches the trace and the TX log and writes out/qtx_<label>.txt in the
# quest_tx_log.sh format (one Quest epoch per injected frame), so ab_segments.py / ab_link.py read them unchanged.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
CMD=$1; LABEL=$2; SECS=${3:-420}
[ -n "$CMD" ] && [ -n "$LABEL" ] || { echo "usage: ab_detached.sh start|pull <label> [seconds]"; exit 1; }
mkdir -p "$QUEST_OUT"
DEV_TRACE=/data/misc/perfetto-traces/ab_$LABEL.pftrace
DEV_TX=/sdcard/ppxr_qtx_$LABEL.txt

case "$CMD" in
start)
  best=""
  for _ in 1 2 3 4 5; do
    a=$(date +%s.%N); q=$(qadb shell date +%s.%N | tr -d '\r'); b=$(date +%s.%N)
    best=$(python3 -c "a,q,b=$a,$q,$b; r=(b-a)*1e3; o=(q-(a+b)/2)*1e3; p='$best'.split()
print(f'{o:.1f} {r:.1f}' if not p or r<float(p[1]) else '$best')")
  done
  echo "quest_minus_pc_ms ${best% *} rtt_ms ${best#* }" | tee "$QUEST_OUT/ab_$LABEL.meta"
  quest_prox_close
  qadb shell "rm -f $DEV_TX"
  # logcat -T 1: only lines from now on; -v epoch: Quest epoch timestamps. Detached from the adb session.
  qadb shell "nohup logcat -T 1 -v epoch -s devourer:D -f $DEV_TX >/dev/null 2>&1 &"
  sed "s/^duration_ms: .*/duration_ms: $((SECS * 1000))/" "$QUEST_LATCH/transport_long.pbtx" \
    | qadb shell "perfetto --txt -c - -o $DEV_TRACE --background"
  echo "started: trace $DEV_TRACE for ${SECS}s, TX log $DEV_TX"
  ;;
pull)
  # No pkill on Horizon OS: find our logcat by its output file name.
  qadb shell 'for p in $(ps -A -o PID,ARGS | grep ppxr_qtx_ | grep -v grep | awk "{print \$1}"); do kill $p; done'
  qadb pull "$DEV_TRACE" "$(cygpath -w "$QUEST_OUT/ab_$LABEL.pftrace")" 2>&1 | tail -1
  qadb pull "$DEV_TX" "$(cygpath -w "$QUEST_OUT/qtx_$LABEL.raw.txt")" 2>&1 | tail -1
  # The same filter quest_tx_log.sh applies: one "TX DESC" line per injected frame -> its epoch.
  grep "TX DESC" "$QUEST_OUT/qtx_$LABEL.raw.txt" | awk '{print $1}' > "$QUEST_OUT/qtx_$LABEL.txt"
  echo "tx frames: $(wc -l < "$QUEST_OUT/qtx_$LABEL.txt")"
  ;;
*) echo "usage: ab_detached.sh start|pull <label> [seconds]"; exit 1 ;;
esac
