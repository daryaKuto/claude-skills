#!/usr/bin/env python3
"""PostToolUse hook (rule pyramid Task 8.4, fail: open): when memory is CRITICAL, tell the agent to shed its own load, and tell
the user once per CRITICAL episode. It never kills anything.
 - Agent: additionalContext, at most once per 5 minutes per session (state/shed-load/<session>.ts).
 - User: one macOS notification per episode. The episode marker state/shed-load/episode exists while memory stays CRITICAL and is
   removed on OK or WARN (UNKNOWN keeps it). The marker is made with O_EXCL, so two sessions cannot both notify.
 - PRESSURE_FAKE set (tests): no notification, but the marker is still made, so tests can count episodes.
Not critical costs one cached pressure read (lib/pressure.py caches 15 s), well under 0.3 s. Any failure prints nothing."""
import json
import os
import re
import subprocess
import sys
import time

STATE = os.path.join(os.environ.get("HOOKS_STATE") or os.path.expanduser("~/.claude/hooks/state"), "shed-load")
EVERY = 300
MSG = "memory is critical: stop your own heaviest job by the pid you recorded; start nothing heavy"


def main():
    d = json.load(sys.stdin)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    import pressure
    level = pressure.status()["level"]
    os.makedirs(STATE, exist_ok=True)
    episode = os.path.join(STATE, "episode")
    if level != "CRITICAL":
        if level in ("OK", "WARN") and os.path.exists(episode):
            os.remove(episode)
        return
    try:
        os.close(os.open(episode, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        # once per episode: drop per-session stamps older than a day, so the folder does not grow for ever
        for f in os.listdir(STATE):
            fp = os.path.join(STATE, f)
            if f.endswith(".ts") and time.time() - os.path.getmtime(fp) > 86400:
                os.remove(fp)
        if not os.environ.get("PRESSURE_FAKE"):
            subprocess.Popen(["osascript", "-e", 'display notification "Memory is critical. Agents were told to stop their heaviest job." with title "Claude hooks"'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except FileExistsError:
        pass
    ts = os.path.join(STATE, re.sub(r"\W", "_", str(d.get("session_id") or "none"))[:64] + ".ts")
    try:
        if time.time() - os.path.getmtime(ts) < EVERY:
            return
    except OSError:
        pass
    open(ts, "w").close()
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": MSG}}))


try:
    main()
except Exception:
    pass
