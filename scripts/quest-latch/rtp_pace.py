"""Stand-in for the air unit in the phase-lock experiment.

Sends a recorded RTP stream frame by frame (packets grouped by RTP timestamp) with an adjustable
frame period, and listens for the headset's compositor-phase reports (PPXR1, see
app/xr/.../PhaseReport.java). With --lock it runs a PI controller that changes ONLY the frame period
(what an air unit can do by nudging the sensor's VMAX), never jumps the phase, until the mean wait
between frame-ready and the compositor latch equals --target-us.

Recording format (rtp_record.py): repeated [float64 t_seconds][uint16 len][len bytes of RTP].

Usage: python3 rtp_pace.py stream.rtp <quest_ip> [--lock] [--seconds 40] [--target-us 1000] [--csv out.csv]
"""
import argparse
import csv
import socket
import struct
import threading
import time


def load_frames(path):
    """[(rtp_timestamp, [packet, ...]), ...] in file order."""
    frames, cur_ts, cur = [], None, []
    with open(path, "rb") as f:
        while True:
            h = f.read(10)
            if len(h) < 10:
                break
            _, n = struct.unpack("<dH", h)
            pkt = f.read(n)
            ts = struct.unpack(">I", pkt[4:8])[0]
            if cur and ts != cur_ts:
                frames.append((cur_ts, cur))
                cur = []
            cur_ts = ts
            cur.append(pkt)
    if cur:
        frames.append((cur_ts, cur))
    return frames


def wrap(x, period):
    """Map x into (-period/2, period/2]."""
    x = (x + period / 2) % period - period / 2
    return x if x != -period / 2 else period / 2


class PhaseLock:
    """PI on the phase error; output = frame-period correction in seconds."""

    def __init__(self, fps, kp=0.5, ki=0.05, max_ppm=5000):
        self.fps, self.kp, self.ki = fps, kp, ki
        self.umax = max_ppm * 1e-6 / fps
        self.integ = 0.0

    def update(self, err_s):
        # err_s > 0: frames wait too long -> arrive too early -> lengthen the period to drift later.
        self.integ += self.ki * err_s / self.fps
        self.integ = max(-self.umax, min(self.umax, self.integ))
        u = self.kp * err_s / self.fps + self.integ
        return max(-self.umax, min(self.umax, u))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stream")
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--report-port", type=int, default=5610)
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--fps", type=float, default=60)
    ap.add_argument("--lock", action="store_true")
    ap.add_argument("--target-us", type=float, default=1000)
    ap.add_argument("--csv", default="")
    a = ap.parse_args()

    frames = load_frames(a.stream)
    period0 = 1.0 / a.fps
    state = {"u": 0.0, "rows": []}
    lock = PhaseLock(a.fps) if a.lock else None
    stop = threading.Event()
    t0 = time.perf_counter()

    def reports():
        r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        r.bind(("0.0.0.0", a.report_port))
        r.settimeout(0.5)
        while not stop.is_set():
            try:
                line = r.recv(512).decode("ascii", "replace").strip()
            except socket.timeout:
                continue
            kv = dict(p.split("=", 1) for p in line.split()[1:] if "=" in p)
            if not line.startswith("PPXR1") or int(kv.get("frames", 0)) < 3:
                continue
            wait, conc, per = float(kv["wait_us"]), float(kv["conc"]), float(kv["period_us"])
            err = wrap(wait - a.target_us, per)
            if lock:
                state["u"] = lock.update(err * 1e-6)
            state["rows"].append((round(time.perf_counter() - t0, 3), wait, conc, round(err), round(state["u"] * 1e6, 2)))
            print(f"t={state['rows'][-1][0]:6.2f}s wait={wait/1000:5.2f}ms conc={conc:.2f} err={err/1000:+5.2f}ms "
                  f"dP={state['u']*1e6:+7.2f}us", flush=True)

    def filler():  # keeps the headset's Wi-Fi out of power save (see docs/xr-quest.md)
        f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        junk = bytes(1000)
        while not stop.is_set():
            f.sendto(junk, (a.host, 9))
            time.sleep(0.004)

    threading.Thread(target=reports, daemon=True).start()
    threading.Thread(target=filler, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t_next, i = time.perf_counter(), 0
    while time.perf_counter() - t0 < a.seconds:
        while time.perf_counter() < t_next:
            pass
        for pkt in frames[i % len(frames)][1]:
            s.sendto(pkt, (a.host, a.port))
        i += 1
        t_next += period0 + state["u"]
    stop.set()
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "wait_us", "conc", "err_us", "dperiod_us"])
            w.writerows(state["rows"])
    print("sent", i, "frames")


if __name__ == "__main__":
    main()
