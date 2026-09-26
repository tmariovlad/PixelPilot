# Source from bash (Git Bash or WSL):  . "$(dirname "$0")/quest_env.sh"
# Exports the rig configuration from quest_env.py (the single source of truth) and defines small
# adb helpers. Paths are exported C:/x-style on Windows, so they stay valid for Windows programs
# (python3, adb.exe) even with MSYS_NO_PATHCONV=1.
_qe_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if command -v cygpath >/dev/null 2>&1; then _qe_py=$(cygpath -m "$_qe_dir/quest_env.py"); else _qe_py="$_qe_dir/quest_env.py"; fi
_qe_out=$(python3 "$_qe_py" --sh) || { echo "quest_env.sh: python3 quest_env.py failed" >&2; return 1 2>/dev/null || exit 1; }
eval "$_qe_out"
unset _qe_dir _qe_py _qe_out

# adb against the headset:  qadb shell ...
qadb() { "$ADB_SH" -s "$QUEST" "$@"; }

# Launch the XR activity (extra args go to `am start`, e.g. -W).
quest_start_xr() {
  qadb shell am start "$@" -a android.intent.action.MAIN -c "$XR_CATEGORY" -n "$PKG/$XR_ACTIVITY"
}

# Session hygiene: keep the XR session FOCUSED with the headset off the face.
quest_prox_close() { qadb shell am broadcast -a com.oculus.vrpowermanager.prox_close >/dev/null; }
quest_guardian_pause() { qadb shell setprop debug.oculus.guardian_pause "${1:-1}"; }
quest_restore() {
  qadb shell setprop debug.oculus.guardian_pause 0
  qadb shell am broadcast -a com.oculus.vrpowermanager.automation_disable >/dev/null
}
