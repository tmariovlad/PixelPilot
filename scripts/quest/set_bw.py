"""Switch the app's wfb channel width (pref "bandwidth", 20 or 40; read by VideoActivity.getBandwidth and applied to the
link at XR onResume), and optionally the channel (pref "wifi-channel", VideoActivity.getChannel), then restart XR, which
restarts the link. Every other pref is kept. The first call saves the
original prefs to <backup>; "restore" writes that file back (e.g. a headset that never had the key goes back to the
default 20).

Usage: python3 set_bw.py 40 out/physical_o82b/prefs-before.xml [channel]
       python3 set_bw.py restore out/physical_o82b/prefs-before.xml
"""
import os
import re
import sys

import quest_adb as q
import quest_env as env

BW = re.compile(r'\s*<int name="bandwidth" value="\d+" />')
CH = re.compile(r'\s*<int name="wifi-channel" value="\d+" />')


def main():
    what, backup = sys.argv[1], sys.argv[2]
    if not q.force_stop():
        sys.exit("the app did not stop; not touching its prefs")
    if not os.path.exists(backup):
        q.backup_prefs(backup)
    if what == "restore":
        q.restore_prefs(backup)
    else:
        xml = q.adb("shell", "run-as", env.PKG, "cat", q.PREFS_FILE).replace(chr(13), "")
        xml = BW.sub("", xml).replace("</map>", q.pref_xml("bandwidth", int(what)) + "</map>", 1)
        if len(sys.argv) > 3:
            xml = CH.sub("", xml).replace("</map>", q.pref_xml("wifi-channel", int(sys.argv[3])) + "</map>", 1)
        q.write_prefs(xml)
    q.prox_close()
    q.start_xr()
    print("bandwidth", what, "channel", sys.argv[3] if len(sys.argv) > 3 else "unchanged", "written and read back; XR restarted")


if __name__ == "__main__":
    main()
