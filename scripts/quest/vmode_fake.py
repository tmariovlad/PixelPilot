"""A stand-in for the air unit's VMODE1 preset receiver (docs/xr/presets-design.md), to run the app's preset flow
without the air side: it answers list / apply / commit / save_default and sends the 1 Hz state beacon, with the
air's revert timer. It changes no video. To point the headset at it, set the app pref vmode_air to "<PC IP>:9998"
(quest_adb.set_prefs keeps only gs.key, so add it to the flags you pass).

Usage: python3 vmode_fake.py [--port 9998] [--switch-s 3] [--fail wide] [--busy] [--same-size]
  --switch-s S  seconds from apply to phase=pending (the new mode "running"); the real air needs ~10-14 s
  --fail MODE   applying MODE never reaches pending, so the revert timer fires
  --busy        answer every apply with state=busy
  --same-size   also list "race-b", a mode at Race's 640x480: the fake changes no video, so only a mode at the size
                that is already streaming can reach the app's commit (CommitGate) on a real link
"""
import argparse
import secrets
import socket
import threading
import time

# Fixture presets, the same numbers as the design's table (W3c); the real air unit owns its own list.
PRESETS = [
    ("race", "Race", "640x480@167", "33x44", "26.7-32.0"),
    ("balanced", "Balanced", "1280x720@119", "66x66", "33.0-38.3"),
    ("balanced-lite", "Balanced-lite", "1280x720@119>848x480", "66x66", "31.3-37.6"),
    ("wide", "Wide", "1920x1080@90>848x480", "99x98", "35.3-41.6"),
]
# As the air unit v1 lists them (c8): only what it can deliver at MCS2 FEC 4/8; 6000 waits for its own A/B.
QUALITIES = [(2000, "0"), (4000, "1.7")]
SAME_SIZE = ("race-b", "Race-B", "640x480@167", "33x44", "26.7-32.0")


class FakeAir:
    def __init__(self, port=9998, switch_s=3.0, fail=None, busy=False, host="0.0.0.0", same_size=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.port = self.sock.getsockname()[1]
        self.switch_s, self.fail, self.busy = switch_s, fail, busy
        self.presets = PRESETS + ([SAME_SIZE] if same_size else [])
        self.beacons = 0
        self.log = []               # (monotonic s, event) for a harness: requests received and phase changes
        self.active, self.default, self.kbps = "race", "race", 2000
        self.phase, self.pending, self.token, self.deadline, self.previous = "ok", "", "", 0.0, "race"
        self.replies = {}           # (addr, seq) -> reply, so a resent request is not applied twice
        self.peer = None
        self.lock = threading.Lock()
        self.running = True

    def fields(self, words):
        return dict(w.split("=", 1) for w in words if "=" in w)

    def handle(self, line, addr):
        words = line.split()
        if len(words) < 2 or words[0] != "VMODE1":
            return None
        verb, f = words[1], self.fields(words[2:])
        seq = f.get("seq", "-1")
        if (addr, seq) in self.replies:
            return self.replies[(addr, seq)]
        self.peer = addr
        self.log.append((time.monotonic(), line.strip()))
        if verb == "list":
            presets = ",".join("|".join(p) for p in self.presets)
            qualities = ",".join(f"{k}|{c}" for k, c in QUALITIES)
            r = (f"VMODE1 list seq={seq} active={self.active} default={self.default} kbps={self.kbps} "
                 f"presets={presets} qualities={qualities}")
        elif verb == "apply":
            r = self.apply(seq, f)
        elif verb == "commit":
            if self.phase == "pending" and f.get("token") == self.token:
                self.active, self.phase, self.pending = self.pending, "ok", ""
                r = f"VMODE1 ack seq={seq} state=committed"
            else:
                r = f"VMODE1 ack seq={seq} state=error reason=no_pending"
        elif verb == "save_default":
            self.default = self.active
            r = f"VMODE1 ack seq={seq} state=saved"
        else:
            r = f"VMODE1 ack seq={seq} state=error reason=bad_request"
        self.replies[(addr, seq)] = r
        return r

    def apply(self, seq, f):
        if self.busy or self.phase in ("applying", "pending"):
            return f"VMODE1 ack seq={seq} state=busy"
        mode, kbps = f.get("preset"), int(f.get("kbps", "0"))
        if mode is not None and mode not in [p[0] for p in self.presets]:
            return f"VMODE1 ack seq={seq} state=error reason=unknown_preset"
        if kbps:
            self.kbps = kbps
        if mode is None or mode == self.active:
            return f"VMODE1 ack seq={seq} state=committed"      # bitrate only: live, no commit
        self.previous, self.pending, self.token = self.active, mode, secrets.token_hex(3)
        self.phase = "applying"
        now = time.monotonic()
        self.pending_at = now + self.switch_s
        self.deadline = now + int(f.get("revert_s", "25"))
        return f"VMODE1 ack seq={seq} state=accepted token={self.token}"

    def step(self):
        """The air's clock: applying -> pending after switch_s (unless --fail), revert at the deadline."""
        now = time.monotonic()
        if self.phase == "applying" and now >= self.pending_at and self.pending != self.fail:
            self.phase = "pending"
        if self.phase in ("applying", "pending") and now >= self.deadline:
            self.active, self.phase, self.pending = self.previous, "reverted", ""

    def beacon(self):
        left = max(0, int(self.deadline - time.monotonic())) if self.phase in ("applying", "pending") else 0
        self.beacons += 1
        token = self.token if self.phase in ("applying", "pending") else ""
        return (f"VMODE1 state seq={self.beacons} preset={self.active} phase={self.phase} pending={self.pending} "
                f"token={token} left_s={left} kbps={self.kbps} req_kbps={self.kbps} mcs=2 fps=166")

    def serve(self):
        self.sock.settimeout(0.1)
        last_beacon = 0.0
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                with self.lock:
                    r = self.handle(data.decode("ascii", "replace"), addr)
                if r:
                    self.sock.sendto(r.encode(), addr)
            except socket.timeout:
                pass
            except OSError:
                return
            with self.lock:
                before = self.phase
                self.step()
                changed = self.phase != before
                if changed:
                    self.log.append((time.monotonic(), f"phase {before} -> {self.phase} (active {self.active})"))
                if self.peer and (changed or time.monotonic() - last_beacon >= 1.0):
                    self.sock.sendto(self.beacon().encode(), self.peer)
                    last_beacon = time.monotonic()
                if self.phase == "reverted" and not changed:
                    self.phase = "ok"                 # reported once (plus the next beacons), then back to ok

    def close(self):
        self.running = False
        self.sock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9998)
    ap.add_argument("--switch-s", type=float, default=3.0)
    ap.add_argument("--fail")
    ap.add_argument("--busy", action="store_true")
    ap.add_argument("--same-size", action="store_true")
    a = ap.parse_args()
    air = FakeAir(a.port, a.switch_s, a.fail, a.busy, same_size=a.same_size)
    print(f"fake air on UDP {air.port} (switch {a.switch_s} s, fail={a.fail}, busy={a.busy}); Ctrl+C to stop", flush=True)
    try:
        air.serve()
    except KeyboardInterrupt:
        air.close()


if __name__ == "__main__":
    main()
