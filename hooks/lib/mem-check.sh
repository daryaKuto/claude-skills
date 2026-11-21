#!/usr/bin/env bash
# One-line health check of this Mac's memory, swap, load and disk. Used by heavy-guard.py and mem-wait.sh.
# Prints "OK|WARN|CRITICAL free=<pct>% swap=<used>/<total>G load=<1min> cores=<n> disk=<free>G top=<name>:<GB>"; exit 0, 1 or 2.
# The limits come from limits.json, and free disk falling more than fall_critical_gb within fall_window_s is CRITICAL
# (a runaway writer can fill a disk in minutes). Samples live in $MEM_STATE_DIR/samples; the fall= field is added only when it triggers.
# Swap counts only together with low free memory (macOS shrinks swap slowly); load is printed, never a trigger.
set -u
here=$(cd "$(dirname "$0")" && pwd)
sd=${MEM_STATE_DIR:-$HOME/.claude/hooks/state/mem}
lim=$(python3 -c '
import json,sys
l=json.load(open(sys.argv[1]))
for k in ("disk_block_gb","disk_warn_gb","free_critical_pct","free_warn_pct","swap_critical_pct","swap_critical_free_below","swap_warn_pct","swap_warn_free_below","fall_critical_gb","fall_window_s"):
    print("L_%s=%d" % (k, int(l[k])))
' "${LIMITS_FILE:-$here/limits.json}" 2>/dev/null) || { echo "UNKNOWN limits.json unreadable"; exit 3; }
eval "$lim"
free=$(memory_pressure 2>/dev/null | awk -F': ' '/free percentage/ {gsub("%","",$2); print $2+0}')
# Unparsable memory_pressure is unknown, not critical: the gates fail open on UNKNOWN (exit 3).
[ -n "$free" ] || { echo "UNKNOWN memory_pressure output not parsable"; exit 3; }
read -r swap_used swap_total < <(sysctl -n vm.swapusage | awk '{gsub("M","",$3); gsub("M","",$6); print $6+0, $3+0}')
load=$(sysctl -n vm.loadavg | awk '{print $2+0}')
cores=$(sysctl -n hw.ncpu)
disk=$(df -g / | awk 'NR==2 {print $4+0}')
top=$(ps -axo rss=,comm= | awk '{n=$2; sub(".*/","",n); m[n]+=$1} END {for (k in m) printf "%.1f %s\n", m[k]/1048576, k}' | sort -rn | head -1 | awk '{print $2":"$1"G"}')
swap_pct=$(awk -v u="$swap_used" -v t="$swap_total" 'BEGIN {print (t > 0) ? int(100 * u / t) : 0}')
# Fall rate: oldest sample inside the window minus now. Samples older than the window plus 60 s are dropped.
now=$(date +%s); free_kb=$(df -k / | awk 'NR==2 {print $4+0}'); fall=0
mkdir -p "$sd" 2>/dev/null
if [ -f "$sd/samples" ]; then
  fall=$(awk -v now="$now" -v w="$L_fall_window_s" -v cur="$free_kb" '$1 >= now - w && !done {d = int(($2 - cur) / 1048576); done = 1} END {print d + 0}' "$sd/samples")
  awk -v now="$now" -v w="$L_fall_window_s" '$1 >= now - w - 60' "$sd/samples" > "$sd/samples.$$" 2>/dev/null && mv "$sd/samples.$$" "$sd/samples"
fi
echo "$now $free_kb" >> "$sd/samples" 2>/dev/null
status=OK; code=0; f=${free:-0}
if [ "$f" -lt "$L_free_warn_pct" ] || { [ "$swap_pct" -gt "$L_swap_warn_pct" ] && [ "$f" -lt "$L_swap_warn_free_below" ]; } || [ "$disk" -lt "$L_disk_warn_gb" ]; then status=WARN; code=1; fi
if [ "$f" -lt "$L_free_critical_pct" ] || { [ "$swap_pct" -gt "$L_swap_critical_pct" ] && [ "$f" -lt "$L_swap_critical_free_below" ]; } || [ "$disk" -lt "$L_disk_block_gb" ]; then status=CRITICAL; code=2; fi
fallnote=""
if [ "$fall" -gt "$L_fall_critical_gb" ]; then status=CRITICAL; code=2; fallnote=" fall=${fall}G/${L_fall_window_s}s"; fi
printf '%s free=%s%% swap=%.1f/%.1fG load=%s cores=%s disk=%sG top=%s%s\n' "$status" "${free:-?}" \
  "$(awk -v u="$swap_used" 'BEGIN {print u/1024}')" "$(awk -v t="$swap_total" 'BEGIN {print t/1024}')" "$load" "$cores" "$disk" "$top" "$fallnote"
exit $code
