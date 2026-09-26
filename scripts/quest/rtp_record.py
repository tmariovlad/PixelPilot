# Records UDP datagrams on 127.0.0.1:<port> as [f64 t][u16 len][bytes] until idle for 3 s.
# Usage: python3 rtp_record.py <out.rtp> <port>   (runs in WSL from the rtp_gen_*.sh scripts; no quest_env import)
import socket, struct, sys, time
out, port = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", port)); s.settimeout(3.0)
n = 0; t0 = None
with open(out, "wb") as f:
    while True:
        try: d = s.recv(65535)
        except socket.timeout:
            if n: break
            continue
        t = time.monotonic(); t0 = t0 or t
        f.write(struct.pack("<dH", t - t0, len(d)) + d); n += 1
print("recorded", n, "packets to", out)
