#!/bin/bash
# Record a 1280x720@60 H.265 RTP test stream with N slices per frame (x265 default rate control, 12 s).
# Usage (in WSL, needs ffmpeg with libx265): rtp_gen_slices.sh <slices> <out>
#   <out> = a path, or a file name that goes into streams/.  quest_lever_repeat.py uses h265_1slice.rtp.
. "$(dirname "$0")/quest_env.sh" || exit 1
out=$2
case "$out" in */*) ;; *) mkdir -p "$QUEST_STREAMS"; out="$QUEST_STREAMS/$out" ;; esac
python3 "$QUEST_DIR/rtp_record.py" "$out" 5700 &
REC=$!; sleep 1
ffmpeg -hide_banner -loglevel error -re -f lavfi -i testsrc2=size=1280x720:rate=60 -t 12 \
  -c:v libx265 -preset ultrafast -tune zerolatency \
  -x265-params "keyint=60:bframes=0:slices=$1:repeat-headers=1:log-level=error" \
  -payload_type 97 -f rtp rtp://127.0.0.1:5700
wait $REC
