"""Offline checks of quest_env.py (path conversions, env overrides, shell export). Run: python3 test_quest_env.py"""
import importlib
import os
import subprocess
import sys

import quest_env


def test_conversions():
    assert quest_env.posix(r"C:\Users\x\tool.exe") == "/c/Users/x/tool.exe"
    assert quest_env.posix("C:/a/b") == "/c/a/b"
    assert quest_env.posix("/mnt/c/a") == "/mnt/c/a"
    assert quest_env.mixed(r"C:\a\b") == "C:/a/b"
    real = os.name
    try:
        os.name = "nt"
        assert quest_env.native("/c/a/b.rtp") == "C:/a/b.rtp"
        assert quest_env.native(r"C:\a") == r"C:\a"
        os.name = "posix"
        assert quest_env.native(r"C:\a\b.rtp") == "/mnt/c/a/b.rtp"
        assert quest_env.native("/home/x") == "/home/x"
    finally:
        os.name = real


def test_overrides():
    keys = ("QUEST", "PC_IP", "WFB_CHANNEL")
    saved, before = {k: os.environ.get(k) for k in keys}, quest_env.QUEST
    os.environ.update(QUEST="10.0.0.5:5555", PC_IP="10.0.0.2", WFB_CHANNEL="149")
    try:
        m = importlib.reload(quest_env)
        assert (m.QUEST_HOST, m.PC_IP, m.WFB_CHANNEL) == ("10.0.0.5", "10.0.0.2", 149)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(quest_env)
    assert quest_env.QUEST == before


def test_stream_path_and_exports():
    assert quest_env.stream_path("h264_720.rtp") == os.path.join(quest_env.STREAMS_DIR, "h264_720.rtp")
    assert quest_env.stream_path(__file__) == __file__
    out = subprocess.run([sys.executable, quest_env.__file__, "--sh"], capture_output=True, text=True).stdout
    names = {line.split("=", 1)[0] for line in out.splitlines()}
    assert {"export ADB_SH", "export QUEST", "export QUEST_STREAMS", "export WLAN_IF"} <= names, names
    assert "export WLAN_IF='Wi-Fi 2'" in out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
