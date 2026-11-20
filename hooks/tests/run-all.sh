#!/usr/bin/env bash
# Run every guard suite and print one line per suite; exit 1 if any failed. Takes a few minutes: run it in the background.
#   bash ~/.claude/hooks/tests/run-all.sh            # all suites
#   bash ~/.claude/hooks/tests/run-all.sh --quick    # skip the slow dispatcher suite
# Set CLAUDE_HOOKS_CONFIG to test a config.json other than the one next to the hooks.
# no-private-terms-cases.py is one of the suites: it greps this folder for words that belong to one project (see that file).
set -u
here=$(cd "$(dirname "$0")" && pwd)
quick=0; [ "${1:-}" = "--quick" ] && quick=1
fail=0
run() {
  local name=$1; shift
  out=$("$@" 2>&1); rc=$?
  printf '%-34s %s  %s\n' "$name" "$([ $rc -eq 0 ] && echo PASS || echo FAIL)" "$(printf '%s\n' "$out" | tail -1)"
  [ $rc -eq 0 ] || fail=1
}
for f in "$here"/*-cases.py "$here"/readonly-battery.py "$here"/bypass-corpus.py; do
  [ -f "$f" ] || continue
  [ $quick -eq 1 ] && [ "$(basename "$f")" = "policy-guard-cases.py" ] && continue
  run "$(basename "$f")" python3 "$f"
done
exit $fail
