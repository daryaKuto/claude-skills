#!/usr/bin/env bash
# Wait until the memory check is no longer CRITICAL (exit 0 or 1; the gate denies only on CRITICAL), polling every 20 s, for at most 20 minutes. Prints one line and exits
# 0 (memory is not critical) or 1 (gave up). Run it in the background when a gate says "memory is critical", then retry once.
# MEM_CHECK, MEM_WAIT_POLL and MEM_WAIT_MAX are for tests.
set -u
chk=${MEM_CHECK:-$(cd "$(dirname "$0")" && pwd)/mem-check.sh}
poll=${MEM_WAIT_POLL:-20}; max=${MEM_WAIT_MAX:-1200}; start=$(date +%s)
while :; do
  line=$(bash "$chk" 2>&1); rc=$?
  [ "$rc" -ne 2 ] && { echo "memory is not critical after $(( $(date +%s) - start )) s: $line"; exit 0; }
  [ $(( $(date +%s) - start + poll )) -gt "$max" ] && { echo "gave up after $(( $(date +%s) - start )) s, still: $line"; exit 1; }
  sleep "$poll"
done
