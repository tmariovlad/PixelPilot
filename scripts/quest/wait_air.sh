#!/bin/bash
# Reconnect the PC's Wi-Fi ($WLAN_IF) to the air unit's AP ($AIR_SSID) and wait until $AIR_IP answers (max ~150 s).
# The Windows WLAN profile comes from openipc-wlan.xml (netsh wlan add profile filename=openipc-wlan.xml).
. "$(dirname "$0")/quest_env.sh" || exit 1
for i in $(seq 1 30); do
  netsh wlan show interfaces 2>&1 | grep -aq "SSID                   : $AIR_SSID" || netsh wlan connect name="$AIR_SSID" interface="$WLAN_IF" >/dev/null 2>&1
  ping -n 1 -w 1000 "$AIR_IP" | grep -q "TTL=" && { echo "air reachable after ~$((i*5))s"; exit 0; }
  sleep 4
done
echo "air NOT reachable"; exit 1
