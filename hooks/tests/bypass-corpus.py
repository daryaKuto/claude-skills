#!/usr/bin/env python3
"""Feeds every row of bypass-corpus.json to policy-guard.py and kill-guard.py as a PreToolUse Bash payload. A row passes when
the decision is at least as strict as `must` (deny counts for ask); kill-guard exit 2 counts as deny. A missed row with a
"covered_by" field (a settings deny rule, not a hook) is reported as covered elsewhere, not as a miss.
Prints one line per miss, then "bypass: N passed, M missed, K covered elsewhere"; exit 1 on a miss."""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "policy-guard.py")
KILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kill-guard.py")
CWD = "/tmp"
RANK = {"deny": 2, "ask": 1}  # anything else (allow, none, crash) ranks 0
passed = missed = covered = 0
TMP = tempfile.mkdtemp(prefix="bypass-corpus-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)  # the temp folder goes away at exit, pass or fail
CFG = os.path.join(TMP, "config.json")  # the fork rows need fork_branches
json.dump({"fork_branches": ["release/legacy", "fork/tools"]}, open(CFG, "w"))
os.environ["CLAUDE_HOOKS_CONFIG"] = CFG
ATTR = os.path.join(TMP, "attr.txt")  # {ATTR} in a command: a real file holding an attribution trailer
open(ATTR, "w").write("fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
for row in json.load(open(os.path.join(HERE, "bypass-corpus.json"))):
    row["command"] = row["command"].replace("{ATTR}", ATTR)
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": CWD, "tool_input": {"command": row["command"]}})
    p = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, timeout=30, cwd=CWD)
    try:
        out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    except ValueError:
        out = {}
    got = out.get("permissionDecision") or "none"
    k = subprocess.run([sys.executable, KILL], input=payload, capture_output=True, text=True, timeout=30, cwd=CWD)
    if k.returncode == 2:
        got = "deny"
    if RANK.get(got, 0) >= RANK[row["must"]]:
        passed += 1
    elif row.get("covered_by"):
        covered += 1
        print(f"COVERED ({row['covered_by']}) cmd={row['command']!r}")
    else:
        missed += 1
        print(f"MISS must={row['must']} got={got} exit={p.returncode} cmd={row['command']!r} ({row['why']})")
print(f"bypass: {passed} passed, {missed} missed, {covered} covered elsewhere")
sys.exit(1 if missed else 0)
