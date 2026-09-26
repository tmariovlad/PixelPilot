#!/bin/bash
# NOTE: belongs to the OpenIPC low-latency project (air unit), not to PixelPilot XR. Kept here because it
# restored the air unit used for the first real-link test (2026-09-26). Run in WSL; paths are PC-VLAD's.
# Rebuild waybeam at f8742fe (HB-51 "last good", documented md5 13b85893) in a scratch copy.
set -e
REPO=/mnt/c/xampp/htdocs/openipc-low-latency-and-others-video/repos/openipc-extra/waybeam_venc
OUT=/tmp/wb-f8742fe
rm -rf "$OUT" && mkdir -p "$OUT"
git -C "$REPO" archive f8742fe | tar -x -C "$OUT"
mkdir -p "$OUT/toolchain" && ln -s "$REPO/toolchain/toolchain.sigmastar-infinity6e" "$OUT/toolchain/toolchain.sigmastar-infinity6e"
cd "$OUT" && make clean >/dev/null 2>&1 || true
make build SOC_BUILD=star6e > /tmp/wb-f8742fe.log 2>&1 || { tail -20 /tmp/wb-f8742fe.log; exit 1; }
ls -la out/star6e/waybeam && md5sum out/star6e/waybeam
