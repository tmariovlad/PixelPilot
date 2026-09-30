#!/bin/bash
# Differential fuzz of wfb-ng's rx Aggregator: two rx.cpp variants (default stock 0da5279 vs the fork's drain 66d4bdb)
# fed the same random drop/reorder patterns by our Transmitter; compares the delivered payloads, count_p_lost and
# count_p_fec_recovered case by case (docs/xr/fec-block-probe.md §8). Run in WSL Ubuntu-22.04 (libsodium-dev,
# libpcap-dev) from the repo root:  bash app/wfbngrtl8812/src/main/cpp/tests/rxfuzz/run.sh [cases] [stock-rev] [drain-rev]
set -e
CASES=${1:-20000}
STOCK=${2:-0da5279}
DRAIN=${3:-66d4bdb}
HERE=$(cd "$(dirname "$0")" && pwd)
WFB=$HERE/../../wfb-ng
OUT=/tmp/rxfuzz-run
rm -rf "$OUT" && mkdir -p "$OUT/variants/stock/wfb-ng" "$OUT/variants/drain/wfb-ng"
git -C "$WFB" cat-file -e "$DRAIN^{commit}" 2>/dev/null || git -C "$WFB" fetch -q https://github.com/tmariovlad/wfb-ng.git pixelpilot-xr
git -C "$WFB" archive "$STOCK" src | tar -x -C "$OUT/variants/stock/wfb-ng"
git -C "$WFB" archive "$DRAIN" src | tar -x -C "$OUT/variants/drain/wfb-ng"
cmake -S "$HERE" -B "$OUT/build" -DCMAKE_BUILD_TYPE=Release -DVARIANTS="$OUT/variants" > "$OUT/cmake.log"
cmake --build "$OUT/build" -j8 > "$OUT/build.log"
"$OUT/build/rx_fuzz_stock" "$CASES" > "$OUT/stock.txt"
"$OUT/build/rx_fuzz_drain" "$CASES" > "$OUT/drain.txt"
echo "stock=$STOCK drain=$DRAIN cases=$CASES"
python3 "$HERE/rx_fuzz_compare.py" "$OUT/stock.txt" "$OUT/drain.txt"
