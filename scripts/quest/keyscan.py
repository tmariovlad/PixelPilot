"""Search local folders for the gs.key that pairs with a given drone.key (64-byte *.key files whose
second half is the drone's public key).
Usage: python3 keyscan.py <drone.key as hex> [root ...]   (default roots: the PC-VLAD project folders below)
Needs: pip install cryptography"""
import os, sys
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
drone = bytes.fromhex(sys.argv[1])
pub = lambda sk: X25519PrivateKey.from_private_bytes(sk).public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
want_drone_pub = pub(drone[:32])
roots = sys.argv[2:] or ["C:/xampp/htdocs/openipc-low-latency-and-others-video", "C:/Users/vlad_/Downloads", "C:/Users/vlad_/Documents", "C:/xampp/htdocs/pixelpilot-xr"]
for root in roots:
    for dp, dns, fs in os.walk(root):
        dns[:] = [d for d in dns if d not in ("node_modules", ".git", "build", ".gradle")]
        for f in fs:
            if f.endswith(".key"):
                p = os.path.join(dp, f)
                try:
                    b = open(p, "rb").read()
                except OSError:
                    continue
                if len(b) == 64 and b[32:] == want_drone_pub:
                    print("MATCH gs.key:", p, "| pairs:", pub(b[:32]) == drone[32:])
print("scan done")
