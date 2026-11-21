#!/usr/bin/env bash
# Run every guard suite and print one line per suite; exit 1 if any failed. Takes a few minutes: run it in the background.
#   bash ~/.claude/hooks/tests/run-all.sh            # all suites
#   bash ~/.claude/hooks/tests/run-all.sh --quick    # skip the slow dispatcher suite
# Set CLAUDE_HOOKS_CONFIG to test a config.json other than the one next to the hooks.
# no-private-terms-cases.py is one of the suites: it greps this folder for words that belong to one project (see that file).
# The suite list is tests/SUITES. A listed file that is missing, or a suite file on disk that is not listed, is a FAIL,
# so a renamed or forgotten suite can never read as green.
set -u
here=$(cd "$(dirname "$0")" && pwd)
quick=0; [ "${1:-}" = "--quick" ] && quick=1
fail=0; ran=0
# Each suite runs in its own process group. After SUITE_TIMEOUT (600 s; macOS has no timeout(1)) the whole group is
# killed, so a child the suite left running (a sleep, a server) dies with it. A timeout is a FAIL.
run() {
  local name=$1; shift
  ran=$((ran+1))
  # The wrapper writes "timeout" or "signal N" into $mark; the suite's own exit code (142 included) is never read as a timeout.
  # stdin is /dev/null so a suite that reads stdin cannot swallow the rest of tests/SUITES.
  local mark; mark=$(mktemp)
  out=$(perl -e 'my ($t,$m)=(shift,shift); my $p=fork; die "fork" unless defined $p;
    if(!$p){ setpgrp(0,0); exec @ARGV or die "exec: $!" }
    sub note { open(my $f,">",$m); print $f $_[0]; close $f }
    $SIG{ALRM}=sub{ note("timeout"); kill("TERM",-$p); select(undef,undef,undef,1); kill("KILL",-$p); waitpid($p,0); exit 1 };
    alarm $t; waitpid($p,0); my $s=$?; alarm 0; kill("KILL",-$p); note("signal ".($s & 127)) if $s & 127; exit($s & 127 ? 128+($s & 127) : $s>>8)' "${SUITE_TIMEOUT:-600}" "$mark" "$@" 2>&1 </dev/null); rc=$?
  local note; note=$(cat "$mark"); rm -f "$mark"
  local last; last=$(printf '%s\n' "$out" | tail -1)
  if [ "$note" = timeout ]; then last="TIMEOUT after ${SUITE_TIMEOUT:-600}s"
  elif [ $rc -ne 0 ]; then last="$last (${note:-exit $rc})"; fi
  printf '%-34s %s  %s\n' "$name" "$([ $rc -eq 0 ] && echo PASS || echo FAIL)" "$last"
  [ $rc -eq 0 ] || fail=1
}
listed=" "
while IFS= read -r line; do
  case "$line" in
    "#"*|"") continue ;;
  esac
  listed="$listed$line "
  if [ ! -f "$here/$line" ]; then echo "FAIL: listed suite is missing: $line"; fail=1; continue; fi
  [ $quick -eq 1 ] && [ "$line" = "policy-guard-cases.py" ] && continue
  run "$line" python3 "$here/$line"
done < "$here/SUITES"
# A suite on disk that SUITES does not list would silently never run.
for f in "$here"/*-cases.py "$here"/readonly-battery.py "$here"/bypass-corpus.py; do
  [ -f "$f" ] || continue
  case "$listed" in *" $(basename "$f") "*) ;; *) echo "FAIL: suite not listed in tests/SUITES: $(basename "$f")"; fail=1 ;; esac
done
echo "ran $ran suites"
if [ "$ran" -eq 0 ]; then echo "FAIL: no suite ran"; fail=1; fi
exit $fail
