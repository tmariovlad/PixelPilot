#!/bin/bash
# Generate the test streams into streams/ (run in WSL; needs ffmpeg with libx264 + libx265).
# Usage: gen_all.sh [h264] [h265] [slices]      (no argument = all three groups)
#   h264 / h265 : {codec}_540.rtp (4M), _720.rtp (8M), _1080.rtp (12M)   -> quest_codec_matrix.py, quest_recheck.py, pace_run.sh
#   slices      : h265_1slice.rtp, h265_4slice.rtp                       -> quest_lever_repeat.py
D="$(cd "$(dirname "$0")" && pwd)"
groups=("$@"); [ ${#groups[@]} -eq 0 ] && groups=(h264 h265 slices)
for g in "${groups[@]}"; do
  case "$g" in
    h264|h265)
      bash "$D/rtp_gen_matrix.sh" "$g" 960x540 4M "${g}_540.rtp"
      bash "$D/rtp_gen_matrix.sh" "$g" 1280x720 8M "${g}_720.rtp"
      bash "$D/rtp_gen_matrix.sh" "$g" 1920x1080 12M "${g}_1080.rtp" ;;
    slices)
      bash "$D/rtp_gen_slices.sh" 1 h265_1slice.rtp
      bash "$D/rtp_gen_slices.sh" 4 h265_4slice.rtp ;;
    *) echo "unknown group: $g (h264|h265|slices)" >&2; exit 2 ;;
  esac
done
