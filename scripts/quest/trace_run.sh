#!/bin/bash
# Usage: trace_run.sh <stream> <out.pftrace> [prefs-python-dict]
# Launch the XR app with the given prefs, replay a stream over Wi-Fi, capture a 9 s Perfetto trace mid-stream.
#   <stream>  a file name in streams/ or a path;  <out.pftrace> a file name (-> out/) or a path.
#   prefs     e.g. "{'dec_picture_order': True}"  (quest_adb.set_prefs: keeps gs.key, drops other prefs)
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
STREAM=$1; OUT=$2; PREFS=${3:-"{}"}
case "$OUT" in */*|*\*) ;; *) mkdir -p "$QUEST_OUT"; OUT="$QUEST_OUT/$OUT" ;; esac
quest_prox_close
qadb shell am force-stop "$PKG"
python3 -c "import quest_lever_test as t; t.set_prefs($PREFS)"
qadb logcat -c
quest_start_xr -W >/dev/null
sleep 4
KEEPAWAKE=1 python3 rtp_play.py "$STREAM" "$VIDEO_PORT" 1 "$QUEST_HOST" >/dev/null 2>&1 &
sleep 2
qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/t.pftrace' < "$QUEST_LATCH/compositor.pbtx" 2>&1 | grep -iE "error|wrote" | tail -2
wait
qadb pull /data/misc/perfetto-traces/t.pftrace "$(cygpath -w "$OUT")" 2>&1 | tail -1
