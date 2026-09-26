#!/bin/bash
# Usage: hygiene.sh pause | restore
#   pause   : Guardian paused + proximity forced "worn", so the XR session stays FOCUSED on a desk
#   restore : Guardian back on + proximity sensor back to normal (run after testing)
. "$(dirname "$0")/quest_env.sh" || exit 1
case "$1" in
  pause)   quest_guardian_pause 1; quest_prox_close; echo "guardian paused, prox_close sent" ;;
  restore) quest_restore; echo "guardian restored, automation_disable sent" ;;
  *) echo "usage: $0 pause|restore" >&2; exit 2 ;;
esac
