#!/usr/bin/env python3
"""Cases for shed-load.py (rule pyramid Task 8.4). The pressure level is given as input (PRESSURE_FAKE); state lives in a temp
HOOKS_STATE, so nothing under your home folder is touched and no notification is posted (PRESSURE_FAKE silences it)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shed-load.py")
fails = total = 0


def report(name, ok, got, want):
    global fails, total
    total += 1
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r}, want {want!r}")


def main():
    state = tempfile.mkdtemp(prefix="shed-")
    base = {**os.environ, "HOOKS_STATE": state}
    base.pop("PRESSURE_FAKE", None)

    def run(level, sid="s1", stdin=None):
        t = time.time()
        p = subprocess.run([sys.executable, HOOK], input=stdin if stdin is not None else json.dumps({"session_id": sid, "tool_name": "Bash"}),
                           capture_output=True, text=True, timeout=10, env={**base, "PRESSURE_FAKE": level})
        out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None
        return p.returncode, out, time.time() - t

    ep = f"{state}/shed-load/episode"
    rc, out, dt = run("OK")
    report("OK prints nothing, exit 0, under 0.3 s", rc == 0 and out is None and dt < 0.3, (rc, out, round(dt, 2)), "silent")
    rc, out, _ = run("CRITICAL")
    report("CRITICAL gives additionalContext", rc == 0 and out and out["hookEventName"] == "PostToolUse" and "memory is critical" in out["additionalContext"], out, "context")
    report("CRITICAL starts an episode", os.path.exists(ep), os.path.exists(ep), True)
    mt = os.path.getmtime(ep)
    rc, out, _ = run("CRITICAL")
    report("same session again within 5 minutes is silent", out is None, out, None)
    rc, out, _ = run("CRITICAL", sid="s2")
    report("another session still gets the message", out is not None, out, "context")
    report("one episode marker for both sessions", os.path.getmtime(ep) == mt, "same file", "same file")
    # age the session stamp past 5 minutes: it speaks again
    old = time.time() - 400
    os.utime(f"{state}/shed-load/s1.ts", (old, old))
    rc, out, _ = run("CRITICAL")
    report("after 5 minutes the same session hears it again", out is not None, out, "context")
    rc, out, _ = run("UNKNOWN")
    report("UNKNOWN is silent and keeps the episode", out is None and os.path.exists(ep), (out, os.path.exists(ep)), (None, True))
    run("WARN")
    report("WARN ends the episode", not os.path.exists(ep), os.path.exists(ep), False)
    stale, fresh = f"{state}/shed-load/stale.ts", f"{state}/shed-load/fresh.ts"
    open(stale, "w").close()
    open(fresh, "w").close()
    two_days = time.time() - 2 * 86400
    os.utime(stale, (two_days, two_days))
    run("CRITICAL", sid="s3")
    report("a new CRITICAL starts a new episode", os.path.exists(ep), os.path.exists(ep), True)
    report("new episode deletes .ts files older than a day, keeps fresh ones", not os.path.exists(stale) and os.path.exists(fresh),
           (os.path.exists(stale), os.path.exists(fresh)), (False, True))
    rc, out, _ = run("CRITICAL", stdin="not json")
    report("garbage stdin fails open", rc == 0 and out is None, (rc, out), (0, None))
    rc, out, _ = run("CRITICAL", stdin="{}")
    report("payload without session_id still works", rc == 0, rc, 0)
    shutil.rmtree(state, ignore_errors=True)
    print(f"{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


main()
