# Replays a recording to <host>:<port> (default 127.0.0.1) with the original pacing; loops N times.
# Usage: python3 rtp_play.py <stream.rtp | name in streams/> <port> [loops=1] [host=127.0.0.1]
# KEEPAWAKE=1 also sends ~250 junk pkt/s to the host's discard port so the Quest's Wi-Fi stays out of power save.
import socket, struct, sys, time
import quest_env
path, port, loops = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1
host = sys.argv[4] if len(sys.argv) > 4 else "127.0.0.1"
pkts = []
with open(quest_env.stream_path(path), "rb") as f:
    while True:
        h = f.read(10)
        if len(h) < 10: break
        t, n = struct.unpack("<dH", h); pkts.append((t, f.read(n)))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dur = pkts[-1][0] + 1 / 60
import threading, os
keepawake = os.environ.get("KEEPAWAKE") == "1"
stop = threading.Event()
def filler():
    f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); junk = bytes(1000)
    while not stop.is_set():
        f.sendto(junk, (host, 9)); time.sleep(0.004)   # ~250 pkt/s to the discard port
if keepawake: threading.Thread(target=filler, daemon=True).start()
for i in range(loops):
    start = time.perf_counter()
    for t, d in pkts:
        while time.perf_counter() - start < t: pass
        s.sendto(d, (host, port))
stop.set()
print("sent", len(pkts) * loops, "packets", "(keep-awake)" if keepawake else "")
