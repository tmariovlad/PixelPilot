#!/bin/bash
# Record one synthetic RTP test stream: 60 fps, keyint 60, no B-frames, 1 slice (testsrc2, 12 s).
# Usage (in WSL, needs ffmpeg with libx264/libx265): rtp_gen_matrix.sh <h264|h265> <WxH> <bitrate> <out>
#   <out> = a path, or a file name that goes into streams/ (quest_env.py STREAMS_DIR).
. "$(dirname "$0")/quest_env.sh" || exit 1
codec=$1; size=$2; br=$3; out=$4
case "$out" in */*) ;; *) mkdir -p "$QUEST_STREAMS"; out="$QUEST_STREAMS/$out" ;; esac
python3 "$QUEST_DIR/rtp_record.py" "$out" 5700 &
REC=$!; sleep 1
if [ "$codec" = h265 ]; then
  enc=(-c:v libx265 -preset ultrafast -tune zerolatency -x265-params "keyint=60:bframes=0:repeat-headers=1:log-level=error") ; pt=97
else
  enc=(-c:v libx264 -preset ultrafast -tune zerolatency -g 60 -bf 0 -x264-params "repeat-headers=1:slices=1:sliced-threads=0") ; pt=96
fi
ffmpeg -hide_banner -loglevel error -re -f lavfi -i testsrc2=size=$size:rate=60 -t 12 "${enc[@]}" \
  -b:v $br -maxrate $br -bufsize $br -pix_fmt yuv420p -payload_type $pt -f rtp rtp://127.0.0.1:5700
wait $REC
