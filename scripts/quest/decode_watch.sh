#!/bin/bash
# Usage: decode_watch.sh [seconds=30] [label]
# Watch the running app's decoder for N seconds: every 5 s averages line (VideoDecoder "Decoding Latency
# Averages": parse / wait-for-input-buffer / decode ms, decoded fps) plus any decoder (re)configuration.
# Use it around an air-unit restart with a new resolution: a decoder that is not rebuilt shows up as a
# decode time of tens of ms (it holds ~16 frames), a rebuilt one as ~1.5-2.5 ms.
. "$(dirname "$0")/quest_env.sh" || exit 1
SECS=${1:-30}; LABEL=${2:-watch}
P=$(qadb shell pidof "$PKG")
[ -n "$P" ] || { echo "$LABEL: app not running"; exit 1; }
qadb logcat -c
sleep "$SECS"
echo "# $LABEL ($SECS s, pid $P)"
qadb logcat -d -v epoch --pid="$P" \
  | grep -E "Parsing:|VideoDecoder: FPS|Configuring decoder (default|OMX|c2)|SPS changed" \
  | sed -E 's/(Configuring decoder [^:]*):.*(width: int32\([0-9]+\), height: int32\([0-9]+\)).*/\1: \2/'
