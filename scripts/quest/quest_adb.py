"""adb helpers for the Quest: run adb against the headset, rewrite the app's shared prefs, launch it."""
import re
import subprocess

import quest_env as env

NL = "\n"
PREFS_HEADER = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>" + NL + "<map>" + NL


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
    return '    <int name="%s" value="%d" />%s' % (k, v, NL)


def write_prefs(xml):
    """Replace the app's shared_prefs/general.xml (the app must be stopped)."""
    adb("exec-in", "run-as", env.PKG, "sh", "-c", "cat > shared_prefs/general.xml", inp=xml.encode())


def set_prefs(flags):
    """Keep the stored gs.key, drop every other pref, set od_enabled=false plus `flags`."""
    xml = adb("shell", "run-as", env.PKG, "cat", "shared_prefs/general.xml")
    key = re.search(r'<string name="gs.key">.*?</string>', xml, re.S).group(0)
    body = "".join(pref_xml(k, v) for k, v in flags.items())
    write_prefs(PREFS_HEADER + "    " + key + NL
                + '    <boolean name="od_enabled" value="false" />' + NL + body + "</map>" + NL)


def prox_close():
    """Tell the power manager the headset is worn, so the XR session stays FOCUSED."""
    adb("shell", "am", "broadcast", "-a", "com.oculus.vrpowermanager.prox_close")


def start_xr(wait=True):
    adb("shell", "am", "start", *(["-W"] if wait else []), "-a", "android.intent.action.MAIN", "-c",
        env.XR_CATEGORY, "-n", f"{env.PKG}/{env.XR_ACTIVITY}")
