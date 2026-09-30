#!/bin/bash
# Usage: air_log_mirror.sh <out_dir> <end PC epoch> [air file ...]
# PC-side, in the background during every air slot: every MIRROR_INTERVAL_S (60) s it copies the air's /tmp logs into
# <out_dir>, until <end epoch>, so a hang or a power cycle cannot take them (2026-09-30: the L6 hang took
# /tmp/ab_l6.log and ab_hdp.log, docs/xr/link-envelope.md).
# Files: names under /tmp (globs expand on the air) or absolute paths; default: ab_*.log slot_chain*.log air_health.log
# waybeam-watchdog.log alink_air.log vmoded.log wfbtx*.log. One `scp -O` per round (key auth; -O = the legacy
# protocol, whose remote path goes through the air's shell, so globs and several paths work), with /etc/hostname as a
# reachability probe: a round where the probe does not arrive is UNREACHABLE; files that do not exist yet are not.
# Kept copies: an empty or missing file never replaces a good copy; a copy smaller than the kept one (the air rebooted
# and /tmp started over) moves the kept one to <name>.<epoch>.pre first. Nothing is ever overwritten by less.
# <out_dir>/mirror.log (and stdout): "<epoch> OK n=<files> updated=<files>", "<epoch> UNREACHABLE <k>", once per outage
# "<epoch> HANG? unreachable since <epoch>" when k reaches 3, "<epoch> BACK at <epoch> after <k> unreachable rounds",
# "<epoch> END". Polling goes on through an outage (planned reboots take 70-90 s, and the logs after the recovery
# matter). Exit 0 at <end epoch>, or 2 when the air was unreachable for >= 3 rounds in a row at some point.
# Env: AIR (root@192.168.100.132), SCP (scp), MIRROR_INTERVAL_S (60), MIRROR_ROUNDS (0 = until <end epoch>; N = stop
# after N rounds, e.g. 1 for a one-shot pull right after a slot).
OUT=$1; END=$2; shift 2 2>/dev/null
[ -n "$OUT" ] && [ -n "$END" ] || { sed -n 2,18p "$0"; exit 2; }
AIR=${AIR:-root@192.168.100.132}; SCP=${SCP:-scp}; STEP=${MIRROR_INTERVAL_S:-60}; ROUNDS=${MIRROR_ROUNDS:-0}
PROBE=/etc/hostname
HANG_ROUNDS=3
set -f   # the file list's globs expand on the air, never here
FILES=("$@")
[ ${#FILES[@]} -gt 0 ] || FILES=(ab_*.log slot_chain*.log air_health.log waybeam-watchdog.log alink_air.log vmoded.log wfbtx*.log)
SRC=$PROBE
for f in "${FILES[@]}"; do case $f in /*) SRC="$SRC $f" ;; *) SRC="$SRC /tmp/$f" ;; esac; done
mkdir -p "$OUT" || exit 2
log() { echo "$(date +%s) $*" | tee -a "$OUT/mirror.log"; }

size() { wc -c < "$1" | tr -d ' '; }

# Move one fetched file into $OUT unless it would replace a good copy with less.
keep() {
  local new=$1 name kept
  name=$(basename "$new"); kept="$OUT/$name"
  [ -s "$new" ] || return 1
  if [ -s "$kept" ]; then
    cmp -s "$new" "$kept" && return 1
    if [ "$(size "$new")" -lt "$(size "$kept")" ]; then
      local pre="$kept.$(date +%s).pre" i=1
      while [ -e "$pre" ]; do pre="$kept.$(date +%s).$i.pre"; i=$((i + 1)); done
      mv "$kept" "$pre"
    fi
  fi
  mv "$new" "$kept"
}

round() {
  local tmp n=0 up=0 f
  tmp=$(mktemp -d "$OUT/.round.XXXXXX") || return 1
  "$SCP" -O -q -o ConnectTimeout=5 -o BatchMode=yes "$AIR:$SRC" "$tmp/" 2>"$tmp/.err"
  if [ ! -s "$tmp/$(basename $PROBE)" ]; then
    rm -rf "$tmp"
    return 1
  fi
  rm -f "$tmp/$(basename $PROBE)" "$tmp/.err"
  set +f
  for f in "$tmp"/*; do
    [ -e "$f" ] || continue
    n=$((n + 1))
    keep "$f" && up=$((up + 1))
  done
  set -f
  rm -rf "$tmp"
  log "OK n=$n updated=$up"
}

DOWN=0; DOWN_SINCE=; HUNG=0; R=0
while :; do
  R=$((R + 1))
  if round; then
    [ "$DOWN" -gt 0 ] && log "BACK at $(date +%s) after $DOWN unreachable rounds (since $DOWN_SINCE)"
    DOWN=0
  else
    [ "$DOWN" -eq 0 ] && DOWN_SINCE=$(date +%s)
    DOWN=$((DOWN + 1))
    log "UNREACHABLE $DOWN"
    if [ "$DOWN" -eq "$HANG_ROUNDS" ]; then log "HANG? unreachable since $DOWN_SINCE"; HUNG=1; fi
  fi
  NOW=$(date +%s)
  [ "$NOW" -ge "$END" ] && break
  [ "$ROUNDS" -gt 0 ] && [ "$R" -ge "$ROUNDS" ] && break
  LEFT=$((END - NOW))
  sleep $(( LEFT < STEP ? LEFT : STEP ))
done
log "END"
exit $(( HUNG ? 2 : 0 ))
