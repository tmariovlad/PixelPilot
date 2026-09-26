#!/bin/bash
# Usage: pace_run.sh <tag> <latch_to_display_us> [rtp_pace.py options, e.g. --lock --target-us 1000]
# Phase-lock experiment: launch the XR app reporting its compositor phase to this PC ($PC_IP:$PHASE_REPORT_PORT),
# run ../quest-latch/rtp_pace.py for 40 s on streams/$PACE_STREAM (default h264_720.rtp), trace the last 9 s.
# Outputs: out/pace_<tag>.csv, out/pace_<tag>.log, out/pace_<tag>.pftrace
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
cd "$QUEST_DIR" || exit 1
mkdir -p "$QUEST_OUT"
TAG=$1; OFF=$2; shift 2
quest_guardian_pause 1
quest_prox_close
qadb shell am force-stop "$PKG"
python3 -c "import quest_lever_test as t; t.set_prefs({'xr_phase_report': '$PC_IP:$PHASE_REPORT_PORT', 'xr_latch_to_display_us': $OFF})"
qadb logcat -c
quest_start_xr -W >/dev/null
sleep 4
python3 -u "$QUEST_LATCH/rtp_pace.py" "$QUEST_STREAMS/${PACE_STREAM:-h264_720.rtp}" "$QUEST_HOST" \
  --port "$VIDEO_PORT" --report-port "$PHASE_REPORT_PORT" --seconds 40 --csv "$QUEST_OUT/pace_$TAG.csv" "$@" \
  > "$QUEST_OUT/pace_$TAG.log" 2>&1 &
sleep 29
qadb shell 'perfetto --txt -c - -o /data/misc/perfetto-traces/t.pftrace' < "$QUEST_LATCH/compositor.pbtx" 2>&1 | grep -iE "error" | tail -2
wait
qadb pull /data/misc/perfetto-traces/t.pftrace "$(cygpath -w "$QUEST_OUT/pace_$TAG.pftrace")" 2>&1 | grep -v pulled
qadb logcat -d | grep -iE "timespec|OpenXR ready|phase report" | head -5
