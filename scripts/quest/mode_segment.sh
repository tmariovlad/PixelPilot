#!/bin/bash
# Usage: mode_segment.sh <label>
# One segment of the W3 mode comparison (docs/xr/g2g-budget.md), run after the air unit switched to a mode:
# restart the XR app (a live resolution change once left the decoder holding frames; a fresh decoder avoids that),
# wait for decoded video, capture one 9 s compositor trace (compositor.pbtx: vsync, latch, decoder, the app's RTP
# marks) and analyse it with transport_analyze.py (frame spread on the radio, frame complete -> decoded, loss) and
# latch_analyze.py (decoded -> compositor latch). The absolute capture -> arrival is not comparable between modes
# (each waybeam start draws a new random RTP base), so only these per-mode segments are used.
# Name segments <mode>_<rep> (e.g. 2_a) so w3_budget.py can group them.
# Output: out/mode_<label>.{pftrace,txt}
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1
[ -n "$LABEL" ] || { echo "usage: mode_segment.sh <label>"; exit 1; }
TRACE="$QUEST_OUT/mode_$LABEL.pftrace"; OUT="$QUEST_OUT/mode_$LABEL.txt"
qadb shell am force-stop "$PKG"; sleep 1
quest_prox_close
quest_start_xr -W >/dev/null
for _ in $(seq 1 20); do
  sleep 2
  P=$(qadb shell pidof "$PKG")
  [ -n "$P" ] && qadb logcat -d -t 300 --pid="$P" 2>/dev/null | grep -q "VideoDecoder: FPS" && break
done
sleep 8   # let the decoder and the link settle after the first frames
qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/mode.pftrace' < "$QUEST_LATCH/compositor.pbtx" 2>&1 | grep -iE "error" | tail -2
qadb pull /data/misc/perfetto-traces/mode.pftrace "$(cygpath -w "$TRACE")" >/dev/null 2>&1
{
  echo "# $LABEL $(date '+%F %T') pid $(qadb shell pidof "$PKG")"
  qadb logcat -d -t 400 --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE "VideoDecoder: FPS:[0-9.]+|Decoding:[0-9.]+" | tail -4 | tr '\n' ' '; echo
  python3 "$QUEST_LATCH/transport_analyze.py" "$(cygpath -w "$TRACE")"
  python3 "$QUEST_LATCH/latch_analyze.py" "$(cygpath -w "$TRACE")" | grep -E "vsync callbacks|frame ready|missed a latch|queued="
} 2>&1 | tee "$OUT"
