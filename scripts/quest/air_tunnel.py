"""Local TCP forward through the air unit's SSH (dropbear allows -L; it runs with -k, which only
disables remote forwards). Used to keep ADB to the Quest while the Quest is a client of the air
unit's APFPV AP: the air unit's AP holds max_num_sta=1, so the PC cannot join as a second client,
and the air unit has no iptables for NAT. The air unit reaches the Quest on wlan0 directly.

Usage: python3 air_tunnel.py [local_port=5595] [dest=192.168.0.10:5555]
       then: adb connect 127.0.0.1:5595
Needs: pip install paramiko. Credentials: the air unit's root/12345 (AIR_ETH_IP, QUEST_APFPV_IP from quest_env.py).
"""
import select
import socket
import sys
import threading

import paramiko

from quest_env import AIR_ETH_IP, QUEST_APFPV_IP

LOCAL_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5595
DEST_HOST, DEST_PORT = (sys.argv[2] if len(sys.argv) > 2 else f"{QUEST_APFPV_IP}:5555").split(":")


def pipe(chan, sock):
    try:
        while True:
            r, _, _ = select.select([chan, sock], [], [])
            if chan in r:
                d = chan.recv(65536)
                if not d:
                    break
                sock.sendall(d)
            if sock in r:
                d = sock.recv(65536)
                if not d:
                    break
                chan.sendall(d)
    finally:
        chan.close()
        sock.close()


def main():
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(AIR_ETH_IP, username="root", password="12345", look_for_keys=False, allow_agent=False)
    tr = cli.get_transport()
    assert tr is not None
    tr.set_keepalive(5)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", LOCAL_PORT))
    srv.listen(4)
    print(f"forwarding 127.0.0.1:{LOCAL_PORT} -> {DEST_HOST}:{DEST_PORT} via {AIR_ETH_IP}", flush=True)
    while True:
        sock, peer = srv.accept()
        try:
            chan = tr.open_channel("direct-tcpip", (DEST_HOST, int(DEST_PORT)), peer)
        except Exception as e:  # destination not reachable yet (Quest not on the AP)
            print(f"open failed: {e}", flush=True)
            sock.close()
            continue
        threading.Thread(target=pipe, args=(chan, sock), daemon=True).start()


if __name__ == "__main__":
    main()
