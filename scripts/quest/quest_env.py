"""Single source of truth for the Quest 2 test rig: where adb is, which headset, which app, where
streams and outputs live. Every script in scripts/quest/ reads its configuration from here.

Override any machine-specific value with an environment variable:
    ADB           adb executable            (default: the Android SDK platform-tools adb.exe on PC-VLAD)
    QUEST         headset adb serial        (default 192.168.100.114:5555, Wi-Fi ADB)
    PC_IP         this PC on the home LAN   (default 192.168.100.213; phase reports come back here)
    WFB_CHANNEL   wfb-ng channel of the air unit (default 157)
    GS_KEY        gs.key for the real link  (default scripts/quest/keys/gs.key, gitignored)
    AIR_IP / AIR_SSID / WLAN_IF   the OpenIPC air unit's AP as seen from the PC's Wi-Fi adapter
    QUEST_STREAMS / QUEST_OUT     stream and output directories

Bash scripts source quest_env.sh, which runs `python3 quest_env.py --sh` and so reads the same values.
"""
import os
import re
import shlex
import sys


def _env(name, default):
    return os.environ.get(name) or default


def native(path):
    """A path usable by this interpreter: /c/x -> C:/x on Windows, C:\\x or C:/x -> /mnt/c/x on Linux/WSL."""
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])/(.*)$", path)
        return f"{m.group(1).upper()}:/{m.group(2)}" if m else path
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    return f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}" if m else path


def mixed(path):
    """C:/x style on Windows (works in Git Bash, in Windows programs and under MSYS_NO_PATHCONV=1)."""
    return path.replace("\\", "/")


def posix(path):
    """/c/x style for executing a Windows program from Git Bash (unchanged on Linux)."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    return f"/{m.group(1).lower()}/{m.group(2)}".replace("\\", "/") if m else path


# --- headset + app ---
ADB = native(_env("ADB", r"C:\Users\vlad_\AppData\Local\Android\Sdk\platform-tools\adb.exe"))
QUEST = _env("QUEST", "192.168.100.114:5555")
QUEST_HOST = QUEST.rsplit(":", 1)[0]
PC_IP = _env("PC_IP", "192.168.100.213")
PKG = "com.openipc.pixelpilot.xr"
XR_ACTIVITY = "com.openipc.pixelpilot.XrVideoActivity"
ACTIVITY_2D = "com.openipc.pixelpilot.VideoActivity"
XR_CATEGORY = "org.khronos.openxr.intent.category.IMMERSIVE_HMD"
VIDEO_PORT = 5600            # the app's RTP input
PHASE_REPORT_PORT = 5610     # PPXR1 compositor-phase reports -> PC (rtp_pace.py --report-port)

# --- real link (RTL8812AU on the Quest + OpenIPC air unit) ---
WFB_CHANNEL = int(_env("WFB_CHANNEL", "157"))
AIR_IP = _env("AIR_IP", "192.168.0.1")
AIR_SSID = _env("AIR_SSID", "OpenIPC")
WLAN_IF = _env("WLAN_IF", "Wi-Fi 2")

# --- directories ---
HERE = os.path.dirname(os.path.abspath(__file__))
STREAMS_DIR = native(_env("QUEST_STREAMS", os.path.join(HERE, "streams")))
OUT_DIR = native(_env("QUEST_OUT", os.path.join(HERE, "out")))
LATCH_DIR = os.path.normpath(os.path.join(HERE, "..", "quest-latch"))
GS_KEY = native(_env("GS_KEY", os.path.join(HERE, "keys", "gs.key")))


def stream_path(name):
    """A recorded stream: an existing path as given, otherwise a file name inside STREAMS_DIR."""
    p = native(name)
    return p if os.path.exists(p) else os.path.join(STREAMS_DIR, name)


def out_path(name):
    """A file inside OUT_DIR (created on demand)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    return os.path.join(OUT_DIR, name)


def shell_exports():
    """`export NAME=value` lines for quest_env.sh."""
    vals = {
        "ADB": mixed(ADB), "ADB_SH": posix(ADB), "QUEST": QUEST, "QUEST_HOST": QUEST_HOST, "PC_IP": PC_IP,
        "PKG": PKG, "XR_ACTIVITY": XR_ACTIVITY, "ACTIVITY_2D": ACTIVITY_2D, "XR_CATEGORY": XR_CATEGORY,
        "VIDEO_PORT": VIDEO_PORT, "PHASE_REPORT_PORT": PHASE_REPORT_PORT, "WFB_CHANNEL": WFB_CHANNEL,
        "AIR_IP": AIR_IP, "AIR_SSID": AIR_SSID, "WLAN_IF": WLAN_IF,
        "QUEST_DIR": mixed(HERE), "QUEST_STREAMS": mixed(STREAMS_DIR), "QUEST_OUT": mixed(OUT_DIR),
        "QUEST_LATCH": mixed(LATCH_DIR), "GS_KEY": mixed(GS_KEY),
    }
    return "".join(f"export {k}={shlex.quote(str(v))}\n" for k, v in vals.items())


if __name__ == "__main__":
    if sys.argv[1:] == ["--sh"]:
        sys.stdout.write(shell_exports())
    else:
        sys.stdout.write(shell_exports().replace("export ", ""))
