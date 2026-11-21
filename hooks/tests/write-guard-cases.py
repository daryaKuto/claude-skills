#!/usr/bin/env python3
"""Cases for write-guard.py: subagent Write/Edit on guard files is denied unless the orchestrator opened a window; the main
session and ordinary files are never touched by that rule. Lane docs and .bak copies outside a lane folder are denied for every
writer (main session too). Exit 0 only if all pass."""
import json
import os
import shutil
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
# The lane rule never checks the system temp folder (scratchpads), so its folders are built under home instead.
LD = os.path.realpath(tempfile.mkdtemp(prefix=".wg-cases-lane-", dir=H))
HP = f"{LD}/plans"  # a plans folder under home, written in config as "~/<name>/plans" (prefix match)
SN = f"{LD}/notes"  # lane_note_dirs: where a lane once wrote its doc
PR = f"{LD}/proj/docs/plans"  # matched by the "/docs/plans/" entry (substring match)
SP = f"{tmp}/scratchpad"  # a scratchpad in the system temp folder
json.dump({"protected_extra_dirs": [D], "lane_dirs": [LANES], "plans_dirs": ["/docs/plans/", "~/" + os.path.relpath(HP, H)],
           "lane_note_dirs": [SN]}, open(cfg, "w"))
empty_cfg = f"{tmp}/empty-config.json"  # no plans_dirs: the lane rule is off
json.dump({"protected_extra_dirs": [D]}, open(empty_cfg, "w"))
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
    # lane docs live under <plans>/<plan>/lanes/<lane>/ and .bak copies are banned under a plans folder; every writer
    ("deny", f"{PR}/p/lane-c.md", True), ("deny", f"{PR}/p/handoff-lane-c.md", True),
    ("deny", f"{PR}/p/handoff-lane-c.md", False), ("deny", f"{SN}/lane-p-x.md", True), ("deny", f"{SN}/Lane-P-X.MD", False),
    ("deny", f"{PR}/p/handoff.md.bak-A5", True), ("deny", f"{HP}/x/lanes.md.bakA1", True),
    ("deny", f"{HP}/x/lanes.md.bakA1", False), ("deny", f"{PR}/p/lanes/c/handoff.md.bak", False),
    ("allow", f"{PR}/p/lanes/c/handoff.md", True), ("allow", f"{PR}/p/lanes/c/handoff.md", False),
    ("allow", f"{PR}/p/lanes/c/scratch/brief-1.md", True), ("allow", f"{PR}/p/lanes/c/lane-c.md", True),
    ("allow", f"{PR}/p/handoff.md", True), ("allow", f"{PR}/p/lanes.md", True),
    ("allow", f"{PR}/p/progress.md", True), ("allow", f"{PR}/p/README.md", False),
    ("allow", f"{SN}/notes-1.md", True), ("allow", f"{LD}/src/lane-utils.ts", True), ("allow", f"{SP}/lane-c.md", True),
    ("allow", f"{SP}/lane-c.md", False), ("allow", f"{LD}/src/x.ts.bak-1", False),
    # globs only under a plans folder or a lane note folder, no .md needed; .bak is a name ending, not a substring
    ("allow", f"{LD}/docs/lane-utils.md", True), ("allow", f"{LD}/src/lanes/lane-a.ts", True), ("allow", f"{PR}/p/x.backup.md", True),
    ("deny", f"{PR}/p/lane-c.txt", True), ("deny", f"{PR}/p/notes.bak", True), ("deny", f"{PR}/p/old.bak/readme.md", True),
    # a tool or test named lane-* in a plans folder is code, not a lane doc
    ("allow", f"{PR}/p/tools/lane-check.sh", True), ("allow", f"{PR}/p/tools/lane_sync.py", True),
    ("deny", f"{PR}/p/tools/lane-notes", True),
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
                            ("allow", "file_path", "x.md", f"{H}/plans"), ("allow", "file_path", "policy-guard.py", "/tmp"), ("allow", "path", "x.md", "/tmp"),
                            ("deny", "file_path", "lane-c.md", f"{PR}/p"), ("allow", "file_path", "handoff.md", f"{PR}/p/lanes/c")]:
    got = decide("", raw=json.dumps({"agent_id": "a", "cwd": cwd, "tool_input": {key: val}}))
    if got != want:
        fails += 1
        print(f"FAIL want={want} got={got} {key}={val} cwd={cwd}")
# an empty plans_dirs turns the lane rule off
if decide(f"{PR}/p/lane-c.md", extra_env={"CLAUDE_HOOKS_CONFIG": empty_cfg}) != "allow":
    fails += 1
    print("FAIL an empty plans_dirs must turn the lane rule off")
# a symlinked plans folder is judged by its written path and its real path: right lane path allowed, .bak copy denied, both directions
os.makedirs(f"{LD}/real/docs/plans")
os.symlink(f"{LD}/real/docs/plans", f"{LD}/link1")  # real path is a plans folder, written path is not
os.makedirs(f"{LD}/other")
os.makedirs(f"{LD}/docs")
os.symlink(f"{LD}/other", f"{LD}/docs/plans")  # written path is a plans folder, real path is not
for want, path in [("allow", f"{LD}/link1/p/lanes/c/handoff.md"), ("deny", f"{LD}/link1/x.md.bak-1"),
                   ("allow", f"{LD}/docs/plans/p/lanes/c/handoff.md"), ("deny", f"{LD}/docs/plans/x.md.bak-1")]:
    got = decide(path)
    if got != want:
        fails += 1
        print(f"FAIL want={want} got={got} symlink {path}")
os.remove(win)
shutil.rmtree(LD, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
print(f"write-guard: {len(ROWS) * 2 + 21} rows, {fails} failed")
sys.exit(1 if fails else 0)
