#!/bin/bash
# rtp_gen_matrix.sh's H.264 stream plus a green band at the top and a red band of the same height at the bottom
# (crop_check.py). x264 pads a 360/1080-row picture to 368/1088 by repeating the last rows, so a layer that draws
# the padding shows a red band 3x as thick as the green one; a layer that honours the crop shows both equal.
# Usage (WSL): rtp_gen_edges.sh <WxH> <bitrate> <out name in streams/> [band rows=4]
. "$(dirname "$0")/quest_env.sh" || exit 1
size=$1; br=$2; out="$QUEST_STREAMS/$3"; bh=${4:-4}   # band height in rows
python3 "$QUEST_DIR/rtp_record.py" "$out" 5700 &
REC=$!; sleep 1
ffmpeg -hide_banner -loglevel error -re -f lavfi -i testsrc2=size=$size:rate=60 -t 12 \
  -vf "drawbox=x=0:y=0:w=iw:h=$bh:color=lime:t=fill,drawbox=x=0:y=ih-$bh:w=iw:h=$bh:color=red:t=fill" \
  -c:v libx264 -preset ultrafast -tune zerolatency -g 60 -bf 0 -x264-params "repeat-headers=1:slices=1:sliced-threads=0" \
  -b:v $br -maxrate $br -bufsize $br -pix_fmt yuv420p -payload_type 96 -f rtp rtp://127.0.0.1:5700
wait $REC
