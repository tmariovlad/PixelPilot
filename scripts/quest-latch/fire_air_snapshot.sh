#!/bin/sh
# Fire air_health.sh's on-demand snapshot on the air (openipc-40, air_health.sh >= 2ecd6be9): the label becomes the
# snapshot's trigger name. Called by first_light_follow.py --on-step "sh scripts/quest-latch/fire_air_snapshot.sh bad71"
# when the rig sees the HD +25 ms state. Key auth to root@.132; a hung air times out in 5 s (the follower adds 15 s).
LABEL=${1:-man}
AIR=${AIR:-root@192.168.100.132}
exec ssh -o BatchMode=yes -o ConnectTimeout=5 "$AIR" "echo $LABEL > /tmp/air_health.snap.now"
