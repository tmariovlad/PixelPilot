"""Offline check of vmode_fake.FakeAir (the VMODE1 stand-in) over localhost UDP. Run: python3 test_vmode_fake.py"""
import socket
import threading
import time

from vmode_fake import FakeAir


def start(**kw):
    air = FakeAir(port=0, host="127.0.0.1", **kw)
    threading.Thread(target=air.serve, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    return air, s


def ask(s, air, line):
    """Sends a request, returns its reply (beacons in between are skipped)."""
    s.sendto(line.encode(), ("127.0.0.1", air.port))
    while True:
        r = s.recv(2048).decode()
        if not r.startswith("VMODE1 state"):
            return r


def wait_beacon(s, phase, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        r = s.recv(2048).decode()
        if r.startswith("VMODE1 state") and f"phase={phase}" in r:
            return r
    raise AssertionError("no beacon with phase=" + phase)


def test_list_carries_presets_and_qualities():
    air, s = start()
    r = ask(s, air, "VMODE1 list seq=1")
    assert "active=race" in r and "wide|Wide|1920x1080@90>848x480|99x98|35.3-41.6" in r and "4000|1.7" in r, r
    air.close()


def test_switch_then_commit():
    air, s = start(switch_s=0.2)
    r = ask(s, air, "VMODE1 apply seq=2 preset=wide revert_s=5")
    assert "state=accepted" in r, r
    token = r.split("token=")[1]
    b = wait_beacon(s, "pending")
    assert f"token={token}" in b and " seq=" in b, b
    assert "state=committed" in ask(s, air, f"VMODE1 commit seq=3 token={token}")
    assert "active=wide" in ask(s, air, "VMODE1 list seq=4")
    air.close()


def test_no_commit_reverts():
    air, s = start(switch_s=0.1)
    ask(s, air, "VMODE1 apply seq=2 preset=wide revert_s=1")
    r = wait_beacon(s, "reverted")
    assert "preset=race" in r, r
    air.close()


def test_a_failing_mode_never_gets_pending_and_reverts():
    air, s = start(switch_s=0.1, fail="wide")
    ask(s, air, "VMODE1 apply seq=2 preset=wide revert_s=1")
    r = wait_beacon(s, "reverted")
    assert "preset=race" in r, r
    air.close()


def test_busy_during_a_switch_and_resend_is_not_applied_twice():
    air, s = start(switch_s=5)
    first = ask(s, air, "VMODE1 apply seq=2 preset=wide revert_s=9")
    assert ask(s, air, "VMODE1 apply seq=2 preset=wide revert_s=9") == first      # same seq: same reply
    assert "state=busy" in ask(s, air, "VMODE1 apply seq=3 preset=balanced revert_s=9")
    air.close()


def test_same_size_mode_is_listed_only_on_request():
    air, s = start()
    assert "race-b" not in ask(s, air, "VMODE1 list seq=1")
    air.close()
    air, s = start(same_size=True)
    assert "race-b|Race-B|640x480@167" in ask(s, air, "VMODE1 list seq=1")
    air.close()


def test_bitrate_only_is_committed_at_once():
    air, s = start()
    assert "state=committed" in ask(s, air, "VMODE1 apply seq=2 kbps=4000 revert_s=25")
    assert "kbps=4000" in ask(s, air, "VMODE1 list seq=3")
    air.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
