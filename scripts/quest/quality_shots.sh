#!/bin/bash
# Usage: quality_shots.sh <state> [n=3] [interval_s=2] [outdir=../../docs/xr/img]
# Picture-quality stills of the XR app without wearing the headset: adb screencap of the compositor output (both eyes,
# 3664x1920), cropped to the left eye's video layer plus the stats overlay under it (link loss/FEC, fps, Mbit/s), so
# every still shows whether artifacts come from the encoder or from lost packets. Saves
# quality-<YYYY-MM-DD>-<state>-<i>.jpg and prints "<Quest epoch> <file>" per shot, to match stills with air-side frames.
# The crop box fits the default layer layout (flat, 90 deg FOV); check one full frame first if the layout changed.
. "$(dirname "$0")/quest_env.sh" || exit 1
export MSYS_NO_PATHCONV=1
STATE=$1; N=${2:-3}; GAP=${3:-2}; OUTDIR=${4:-$(dirname "$0")/../../docs/xr/img}
[ -n "$STATE" ] || { echo "usage: quality_shots.sh <state> [n] [interval_s] [outdir]"; exit 1; }
mkdir -p "$OUTDIR" "$QUEST_OUT"
TMP="$QUEST_OUT/quality_shot_tmp"   # C:/ path: Windows python cannot open an MSYS /tmp path
for i in $(seq 1 "$N"); do
  t=$(qadb shell date +%s.%N | tr -d '\r')
  "$ADB_SH" -s "$QUEST" exec-out screencap -p > "$TMP.png"
  OUT="$OUTDIR/quality-$(date +%F)-$STATE-$i.jpg"
  python3 - "$TMP.png" "$(cygpath -m "$OUT" 2>/dev/null || echo "$OUT")" <<'EOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
box = (int(w * 0.063), int(h * 0.20), int(w * 0.405), int(h * 0.81))  # left eye: video layer + stats overlay
im.crop(box).save(sys.argv[2], "JPEG", quality=88)
EOF
  echo "$t $OUT"
  [ "$i" -lt "$N" ] && sleep "$GAP"
done
rm -f "$TMP.png"
