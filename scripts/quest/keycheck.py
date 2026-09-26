"""Check that a drone.key and a gs.key form a wfb-ng pair (X25519: each file = own secret[32] + peer public[32]).
Usage: python3 keycheck.py <drone.key as hex> <gs.key file>     (hex e.g. from `xxd -p -c 64 /etc/drone.key` on the air unit)
Needs: pip install cryptography"""
import sys
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
drone = bytes.fromhex(sys.argv[1]); gs = open(sys.argv[2], "rb").read()
pub = lambda sk: X25519PrivateKey.from_private_bytes(sk).public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
print("gs.key len", len(gs))
print("drone pub (from drone.key secret) == gs.key[32:]:", pub(drone[:32]) == gs[32:64])
print("gs pub (from gs.key secret)       == drone.key[32:]:", pub(gs[:32]) == drone[32:64])
