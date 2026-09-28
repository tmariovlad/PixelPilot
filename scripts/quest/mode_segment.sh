#!/bin/bash
# Usage: mode_segment.sh <label>
# One segment of the W3 mode comparison (docs/xr/g2g-budget.md), run after the air unit switched to a mode:
# restart the XR app (a live resolution change once left the decoder holding frames; a fresh decoder avoids that),
# wait for decoded video, capture one 9 s compositor trace (compositor.pbtx: vsync, latch, decoder, the app's RTP
# marks) and analyse it with transport_analyze.py (frame spread on the radio, frame complete -> decoded, loss) and
# latch_analyze.py (decoded -> compositor latch). The absolute capture -> arrival is not comparable between modes
# (each waybeam start draws a new random RTP base), so only these per-mode segments are used.
# Name segments <mode>_<rep> (e.g. 2_a) so w3_budget.py can group them.
# NO_RESTART=1 keeps the running app (and its decoder): for a lever the app follows live, e.g. the H.264 <-> H.265
# switch (CodecSwitch.h), so the segment measures the decoder the pilot actually gets after a live switch.
# Output: out/mode_<label>.{pftrace,txt}
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
LABEL=$1
[ -n "$LABEL" ] || { echo "usage: mode_segment.sh <label>"; exit 1; }
TRACE="$QUEST_OUT/mode_$LABEL.pftrace"; OUT="$QUEST_OUT/mode_$LABEL.txt"
quest_prox_close
if [ "${NO_RESTART:-0}" != 1 ]; then
  qadb shell am force-stop "$PKG"; sleep 1
  quest_prox_close
  quest_start_xr -W >/dev/null
fi
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
  # Prefs and decoder keys actually in effect (a launch once came up without its prefs; picture-order alone is
  # worth ~95 ms of decode on this stream, docs/xr/real-link.md)
  echo "prefs: $(qadb shell run-as "$PKG" cat shared_prefs/general.xml | grep -v gs.key | grep -oE 'name="[^"]+"( value="[^"]+")?' | tr '\n' ' ')"
  # the last configure: with NO_RESTART a live codec switch rebuilds the decoder in the same process
  echo "decoder: $(qadb logcat -d --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE 'Configuring decoder [^:]*:.*' | tail -1 | grep -oE '(width|height|low-latency|vendor\.qti-ext-dec-picture-order\.enable|operating-rate)[^,]*' | tr '\n' ' ')"
  qadb logcat -d -t 400 --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE "VideoDecoder: FPS:[0-9.]+|Decoding:[0-9.]+" | tail -4 | tr '\n' ' '; echo
  # live H.264 <-> H.265 switches this process followed (VideoDecoder::interpretNALU)
  qadb logcat -d --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE "codec changed to H\.26[45]" | sed 's/^/live switch: /' | tail -3
  # the SPS the decoder was configured with (builds >= e889479) and whether it rules out frame reordering
  SPS=$(qadb logcat -d --pid="$(qadb shell pidof "$PKG")" 2>/dev/null | grep -oE "csd-0 [0-9a-f]+" | tail -1)
  [ -n "$SPS" ] && echo "sps: $SPS" && echo "$SPS" | python3 sps_vui.py - | sed 's/^/sps: /'
  python3 "$QUEST_LATCH/transport_analyze.py" "$(cygpath -w "$TRACE")"
  python3 "$QUEST_LATCH/latch_analyze.py" "$(cygpath -w "$TRACE")" | grep -E "vsync callbacks|frame ready|missed a latch|queued="
} 2>&1 | tee "$OUT"
