#!/usr/bin/env python3
"""Cases for write-guard.py: subagent Write/Edit on guard files is denied unless the orchestrator opened a window; the main
session and ordinary files are never touched. Exit 0 only if all pass."""
import json
import os
import subprocess
import sys
import tempfile
import time

HOOK = os.environ.get("WRITE_GUARD_HOOK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "write-guard.py")
H = os.path.expanduser("~")
tmp = os.path.realpath(tempfile.mkdtemp(prefix="write-guard-cases-"))
D = f"{tmp}/real/app"  # a project folder listed in config.json protected_extra_dirs; tmp/link is a symlink to tmp/real
LANES = f"{tmp}/lanes"  # lane_dirs
os.makedirs(D)
os.symlink(f"{tmp}/real", f"{tmp}/link")
cfg = f"{tmp}/config.json"
json.dump({"protected_extra_dirs": [D], "lane_dirs": [LANES]}, open(cfg, "w"))
win = os.path.join(tmp, "ALLOW_AGENTS_UNTIL")


def decide(path, agent=True, tool="Edit", extra_env=None, raw=None):
    payload = raw if raw is not None else json.dumps({"tool_name": tool, "tool_input": {"file_path": path}, **({"agent_id": "a1", "agent_type": "general-purpose"} if agent else {})})
    p = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, timeout=30,
                       env={**os.environ, "WRITE_GUARD_WINDOW": win, "CLAUDE_HOOKS_CONFIG": cfg, **(extra_env or {})})
    if p.returncode:
        return f"ERROR rc={p.returncode}"
    return "deny" if '"deny"' in p.stdout else "allow"


ROWS = [
    ("deny", f"{H}/.claude/hooks/policy-guard.py", True), ("deny", f"{H}/.claude/hooks/state/heavy-guard/NO_BACKGROUND_RULE", True),
    ("deny", f"{H}/.claude/hooks/state/write-guard/ALLOW_AGENTS_UNTIL", True), ("deny", f"{H}/.claude/settings.json", True),
    ("deny", f"{H}/.claude/settings.local.json", True), ("deny", f"{H}/.claude/CLAUDE.md", True),
    ("deny", f"{D}/.claude/hooks/project-guard.py", True), ("deny", f"{D}/.claude/settings.local.json", True),
    ("deny", f"{tmp}/link/app/.claude/hooks/project-guard.py", True),  # symlinked path
    ("deny", f"{H}/.claude/hooks/../hooks/kill-guard.py", True),
    ("deny", f"{H}/.claude/HOOKS/kill-guard.py", True), ("deny", f"{H}/.Claude/Settings.JSON", True), ("deny", f"{H}/.claude/claude.md", True),
    ("allow", f"{H}/.claude/hooks/policy-guard.py", False),  # main session
    ("allow", f"{D}/src/a.ts", True), ("allow", f"{D}/.claude/plans/x.md", True), ("allow", f"{D}/.claude/skills/x/SKILL.md", True),
    ("allow", f"{H}/.claude/skills/unslop/SKILL.md", True), ("allow", f"{H}/.claude/projects/p/memory/m.md", True),
    ("allow", f"{H}/plans/x/plan.md", True), ("allow", "/tmp/x.py", True),
    # other files that switch guards off (subagents denied; reads are not Write/Edit so never reach this guard)
    ("deny", f"{H}/.claude/guard-bin/pkill", True), ("deny", f"{H}/.claude/watchdog/disk-watchdog.sh", True), ("deny", f"{H}/.zshenv", True),
    ("deny", f"{H}/Library/LaunchAgents/com.example.disk-watchdog.plist", True), ("deny", f"{LANES}/wt-a/.claude/settings.json", True),
    ("deny", f"{LANES}/wt-b/.claude/settings.local.json", True), ("deny", f"{H}/.claude/GUARD-BIN/pkill", True),
    ("allow", f"{H}/.claude/guard-bin/pkill", False), ("allow", f"{H}/.zprofile", True), ("allow", f"{H}/Library/LaunchAgents/com.x.other.plist", True),
    ("allow", f"{LANES}/wt-a/src/a.ts", True), ("allow", f"{LANES}/wt-a/.claude/plans/x.md", True),
]
fails = 0
for want, path, agent in ROWS:
    for tool in ("Edit", "Write"):
        got = decide(path, agent, tool)
        if got != want:
            fails += 1
            print(f"FAIL want={want} got={got} agent={agent} {tool} {path}")
if decide(f"{H}/.claude/hooks/x.ipynb", raw=json.dumps({"tool_name": "NotebookEdit", "agent_id": "a", "tool_input": {"notebook_path": f"{H}/.claude/hooks/x.ipynb"}})) != "deny":
    fails += 1
    print("FAIL NotebookEdit on a hook must deny")
# the orchestrator's window lets subagents through until it expires
open(win, "w").write(str(time.time() + 600))
if decide(f"{H}/.claude/hooks/policy-guard.py") != "allow":
    fails += 1
    print("FAIL an open window must allow")
open(win, "w").write(str(time.time() - 1))
if decide(f"{H}/.claude/hooks/policy-guard.py") != "deny":
    fails += 1
    print("FAIL an expired window must deny")
open(win, "w").write("garbage")
if decide(f"{H}/.claude/hooks/policy-guard.py") != "deny":
    fails += 1
    print("FAIL an unreadable window must deny")
if decide("", raw='{"agent_id": "a", "tool_input": {"file_path": "/home/x/.claude/hooks/a.py"} BROKEN') != "deny":
    fails += 1
    print("FAIL a broken subagent payload naming a hook must deny")
if decide("", raw="not json") != "allow":
    fails += 1
    print("FAIL garbage with no protected path must not deny")
# a relative file_path resolves against the payload cwd; a `path` key is read too
for want, key, val, cwd in [("deny", "file_path", "policy-guard.py", f"{H}/.claude/hooks"), ("deny", "file_path", "hooks/policy-guard.py", f"{H}/.claude"),
                            ("deny", "file_path", "../.claude/settings.json", f"{H}/plans"), ("deny", "path", f"{H}/.claude/settings.json", "/tmp"),
                            ("deny", "path", "policy-guard.py", f"{H}/.claude/hooks"),
                            ("allow", "file_path", "x.md", f"{H}/plans"), ("allow", "file_path", "policy-guard.py", "/tmp"), ("allow", "path", "x.md", "/tmp")]:
    got = decide("", raw=json.dumps({"agent_id": "a", "cwd": cwd, "tool_input": {key: val}}))
    if got != want:
        fails += 1
        print(f"FAIL want={want} got={got} {key}={val} cwd={cwd}")
os.remove(win)
import shutil; shutil.rmtree(tmp, ignore_errors=True)
print(f"write-guard: {len(ROWS) * 2 + 14} rows, {fails} failed")
sys.exit(1 if fails else 0)
