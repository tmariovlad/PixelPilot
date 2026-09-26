"""Write the .xr app's prefs for a real wfb link: gs.key (Base64, as GsKeyStore stores it) + channel.
Usage: python3 set_link_prefs.py <gs.key> <channel> [bool_lever=true ...]   e.g. dec_picture_order=true
(real_run.sh passes $GS_KEY and $WFB_CHANNEL from quest_env)"""
import base64
import sys

import quest_env as env
from quest_adb import NL, PREFS_HEADER, adb, write_prefs

key_file, channel = sys.argv[1], int(sys.argv[2])
extra = dict(a.split("=", 1) for a in sys.argv[3:])  # bool levers, e.g. dec_picture_order=true
b64 = base64.b64encode(open(env.native(key_file), "rb").read()).decode()
xml = (PREFS_HEADER
       + f'    <string name="gs.key">{b64}</string>' + NL
       + '    <boolean name="od_enabled" value="false" />' + NL
       + f'    <int name="wifi-channel" value="{channel}" />' + NL
       + "".join(f'    <boolean name="{k}" value="{v}" />' + NL for k, v in extra.items()) + "</map>" + NL)
adb("shell", "am", "force-stop", env.PKG)
write_prefs(xml)
print(adb("shell", "run-as", env.PKG, "cat", "shared_prefs/general.xml"))
