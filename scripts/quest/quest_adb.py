"""adb helpers for the Quest: run adb against the headset, rewrite the app's shared prefs, launch it."""
import re
import subprocess
import time

import quest_env as env

NL = "\n"
PREFS_HEADER = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>" + NL + "<map>" + NL
PREFS_FILE = "shared_prefs/general.xml"
PREFS_TMP = PREFS_FILE + ".tmp"
READBACK_TRIES = 3        # a read right after the write can still see the old file
READBACK_WAIT_S = 0.1
_sleep = time.sleep       # replaced by the offline test


def adb(*a, inp=None):
    """Run adb -s $QUEST <args>; returns stdout ("" on a 40 s timeout)."""
    try:
        r = subprocess.run([env.ADB, "-s", env.QUEST, *a], input=inp, capture_output=True, timeout=40)
    except subprocess.TimeoutExpired:
        print("  adb timeout:", " ".join(a[:4]), flush=True)
        return ""
    return r.stdout.decode("utf-8", "replace")


def pref_xml(k, v):
    if isinstance(v, str):
        return '    <string name="%s">%s</string>%s' % (k, v, NL)
    if isinstance(v, bool):
        return '    <boolean name="%s" value="%s" />%s' % (k, "true" if v else "false", NL)
    if isinstance(v, float):
        return '    <float name="%s" value="%r" />%s' % (k, v, NL)
    return '    <int name="%s" value="%d" />%s' % (k, v, NL)


def write_prefs(xml):
    """Replace the app's shared_prefs/general.xml (the app must be stopped), then read it back.

    Raises if the file on the headset differs: an A/B step must never run silently on the previous prefs. (On
    2026-09-27 a harness called set_link_prefs.py through subprocess "python3", which on Windows resolves to the
    Store alias and exits 9009, so a whole key test ran on unchanged prefs; see docs/xr/troubleshooting.md.)

    The write is atomic (a temp file, then mv), so neither the app nor the read-back ever sees a file truncated by
    "cat >", and the read-back is retried a few times before it raises: in the alink8 run on 2026-09-27 the guard
    failed a step whose value had landed, because the read came too early or caught the truncated file.

    The temp file and the rename are two adb calls. On the Quest, `adb exec-in run-as PKG sh -c "cat > tmp && mv
    tmp final"` runs only the first command inside run-as: the tmp file was written, the rename never happened, and
    general.xml stayed unchanged from 18:16 to 22:34 on 2026-09-27 (every read-back then failed; see
    docs/xr/troubleshooting.md)."""
    adb("exec-in", "run-as", env.PKG, "sh", "-c", "cat > " + PREFS_TMP, inp=xml.encode())
    adb("shell", "run-as", env.PKG, "mv", PREFS_TMP, PREFS_FILE)
    want = xml.replace(chr(13), "")   # adb may return CRLF
    for attempt in range(READBACK_TRIES):
        if adb("shell", "run-as", env.PKG, "cat", PREFS_FILE).replace(chr(13), "") == want:
            return
        if attempt + 1 < READBACK_TRIES:
            _sleep(READBACK_WAIT_S)
    raise RuntimeError("prefs write did not land on the headset (read-back differs after %d reads)" % READBACK_TRIES)


def set_prefs(flags):
    """Keep the stored gs.key, drop every other pref, set od_enabled=false plus `flags`."""
    xml = adb("shell", "run-as", env.PKG, "cat", PREFS_FILE)
    key = re.search(r'<string name="gs.key">.*?</string>', xml, re.S).group(0)
    body = "".join(pref_xml(k, v) for k, v in flags.items())
    write_prefs(PREFS_HEADER + "    " + key + NL
                + '    <boolean name="od_enabled" value="false" />' + NL + body + "</map>" + NL)


def step_prefs(pref, value, extra_json):
    """The prefs one pref_ab.sh step writes: EXTRA_PREFS (a JSON object, may be empty) plus `pref` = `value`, typed
    true/false -> boolean, digits -> int, else string. set_prefs drops every pref it is not given, so a setting that
    must hold for the whole A/B (e.g. rx-diag-ring-ms) goes in EXTRA_PREFS."""
    import json
    prefs = json.loads(extra_json) if extra_json.strip() else {}
    if value in ("true", "false"):
        typed = value == "true"
    elif value.isdigit():
        typed = int(value)
    else:
        typed = value
    prefs[pref] = typed
    return prefs


def backup_prefs(path):
    """Save the app's whole prefs file (the app must be stopped) before an A/B overwrites it with set_prefs.

    Raises, writing nothing, if the read has no gs.key: a failed run-as read must never become the "backup"."""
    xml = adb("shell", "run-as", env.PKG, "cat", PREFS_FILE).replace(chr(13), "")
    if '<string name="gs.key">' not in xml:
        raise RuntimeError("prefs backup read has no gs.key; nothing saved")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(xml)


def restore_prefs(path):
    """Write back a file saved by backup_prefs (checked by write_prefs' read-back)."""
    with open(path, encoding="utf-8", newline="") as f:
        write_prefs(f.read())


def prox_close():
    """Tell the power manager the headset is worn, so the XR session stays FOCUSED."""
    adb("shell", "am", "broadcast", "-a", "com.oculus.vrpowermanager.prox_close")


def start_xr(wait=True):
    adb("shell", "am", "start", *(["-W"] if wait else []), "-a", "android.intent.action.MAIN", "-c",
        env.XR_CATEGORY, "-n", f"{env.PKG}/{env.XR_ACTIVITY}")
