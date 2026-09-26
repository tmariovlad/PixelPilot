"""Reproduce `wfb_keygen <password>` (wfb-ng src/keygen.c): Argon2i13 INTERACTIVE with the fixed salt,
then crypto_box_seed_keypair for drone (seed[0:32]) and gs (seed[32:64]). Writes drone.key and
checks the gs.key it derives against a given gs.key.
Usage: python3 pwkey.py <password> <salt as in keygen.c> <gs.key to match> <drone.key to write>
Needs: pip install pynacl"""
import sys
import nacl.bindings as b
from nacl import pwhash

password, salt, target = sys.argv[1].encode(), bytes(sys.argv[2], "latin1"), open(sys.argv[3], "rb").read()
seed = pwhash.argon2i.kdf(64, password, salt, opslimit=pwhash.argon2i.OPSLIMIT_INTERACTIVE,
                          memlimit=pwhash.argon2i.MEMLIMIT_INTERACTIVE)
d_pk, d_sk = b.crypto_box_seed_keypair(seed[:32])
g_pk, g_sk = b.crypto_box_seed_keypair(seed[32:])
gs = g_sk + d_pk
print(f"password {sys.argv[1]!r}: derived gs.key == target: {gs == target}")
if gs == target:
    open(sys.argv[4], "wb").write(d_sk + g_pk)
    print("wrote", sys.argv[4])
