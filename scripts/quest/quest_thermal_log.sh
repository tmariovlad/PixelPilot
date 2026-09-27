#!/bin/bash
# Usage: quest_thermal_log.sh [seconds=240] [out.csv=out/thermal.csv] [period_s=5]
# Samples the Quest's thermal state and battery every period_s seconds while a trace runs (read-only, dumpsys):
# quest_epoch, thermal_status (0 = none … 4+ = severe/throttling), cpu_max_c, soc_c, batt_c, batt_level, charging.
# Join to an in-trace A/B by epoch (the Quest's REALTIME clock, same as ab_segments' steps after the air offset).
. "$(dirname "$0")/quest_env.sh" || exit 1
SECS=${1:-240}; OUT=${2:-$QUEST_OUT/thermal.csv}; PERIOD=${3:-5}
echo "quest_epoch,thermal_status,cpu_max_c,soc_c,batt_c,batt_level,charging" > "$OUT"
end=$(( $(date +%s) + SECS ))
while [ "$(date +%s)" -lt "$end" ]; do
  qadb shell "date +%s.%N; dumpsys thermalservice | sed -n '/^Thermal Status/p;/Cached temperatures/,/^[A-Z]/p'; dumpsys battery" \
    | tr -d '\r' | awk '
      NR == 1 { t = $1 }
      /^Thermal Status:/ { st = $3 }
      /mName=cpu-/ { v = $0; sub(/.*mValue=/, "", v); sub(/,.*/, "", v); if (v + 0 > cmax) cmax = v + 0 }
      /mName=soc-iio-usr/ { v = $0; sub(/.*mValue=/, "", v); sub(/,.*/, "", v); soc = v + 0 }
      /^  level:/ { lvl = $2 }
      /^  temperature:/ { bt = $2 / 10 }
      /^  AC powered: true|^  USB powered: true/ { chg = 1 }
      END { printf "%s,%s,%.1f,%.1f,%.1f,%s,%d\n", t, st, cmax, soc, bt, lvl, chg }' >> "$OUT"
  sleep "$PERIOD"
done
echo "wrote $OUT ($(($(wc -l < "$OUT") - 1)) samples)"
