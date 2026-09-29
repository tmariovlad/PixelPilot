#!/bin/bash
# Record one synthetic GDR (intra refresh) RTP stream + its "no-IDR" cut, for the decoder tests of OpenIPC O118 S0
# (T1 cold start without an IDR, T3 heal time with rtp_play.py DROP=, T4 slices, T5 rebuild/codec switch).
# Encoder: x264/x265 periodic intra refresh (one refresh pass per `keyint` frames, only the first frame is an IDR),
# no B-frames, SPS/PPS(/VPS) repeated, testsrc2 for 12 s, RTP payload <= 1400 B like the air (PT 96 / 97).
# Usage (in WSL, needs ffmpeg with libx264/libx265):
#   rtp_gen_gdr.sh <h264|h265> <WxH> <fps> <bitrate> <slices> <out.rtp> [keyint=30]
#   <out> = a path, or a file name that goes into streams/ (quest_env.py STREAMS_DIR).
#   Writes <out> (full stream, starts with one IDR) and <out minus .rtp>_noidr.rtp (starts at the first SPS that
#   precedes a non-IDR frame), and prints the NAL histogram of both (rtp_gdr.py; exit 1 if the cut has an IDR).
. "$(dirname "$0")/quest_env.sh" || exit 1
codec=$1; size=$2; fps=$3; br=$4; slices=$5; out=$6; keyint=${7:-30}
[ -n "$out" ] || { sed -n '2,11p' "$0"; exit 2; }
case "$out" in */*) ;; *) mkdir -p "$QUEST_STREAMS"; out="$QUEST_STREAMS/$out" ;; esac
cut="${out%.rtp}_noidr.rtp"
python3 "$QUEST_DIR/rtp_record.py" "$out" 5700 &
REC=$!; sleep 1
if [ "$codec" = h265 ]; then
  enc=(-c:v libx265 -preset ultrafast -tune zerolatency
       -x265-params "keyint=$keyint:bframes=0:intra-refresh=1:repeat-headers=1:slices=$slices:log-level=error"); pt=97
else
  enc=(-c:v libx264 -preset ultrafast -tune zerolatency -g "$keyint" -bf 0
       -x264-params "intra-refresh=1:keyint=$keyint:repeat-headers=1:slices=$slices:sliced-threads=0"); pt=96
fi
ffmpeg -hide_banner -loglevel error -re -f lavfi -i testsrc2=size=$size:rate=$fps -t 12 "${enc[@]}" \
  -b:v $br -maxrate $br -bufsize $br -pix_fmt yuv420p -payload_type $pt -f rtp "rtp://127.0.0.1:5700?pkt_size=1400"
wait $REC
python3 "$QUEST_DIR/rtp_gdr.py" "$out" "$codec" --cut "$cut"
