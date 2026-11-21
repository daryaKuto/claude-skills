#!/usr/bin/env python3
"""Rule: a guard check that protects a folder must also catch every PARENT of that folder, and a
whole-folder copy (rsync src/, cp src/., ditto, a glob, or a source named like the next folder down) into any parent
counts as a write to the guard.
Removing, moving, overwriting or pointing git at a parent (~, ~/Documents, a protected project's root) changes the guard
just as surely as touching it directly. A fix that narrows a check to "exactly this path" breaks that (it happened
twice: git --work-tree=~/.claude, and whole-folder copies into ~/). This file generates the rows from
the guard folders themselves, so a new narrowing fails here even when nobody thought to write a case for it.

For every guard folder (the hooks repo, a listed project's .claude/hooks) and every parent of it up to /, every
write shape below must be denied. A few ordinary commands next to them must stay allowed. Exit 0 only if all pass."""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.environ.get("TAMPER_HOOK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tamper-guard.py")
HOME = os.path.realpath(os.path.expanduser("~"))
PROJECT = os.path.realpath(tempfile.mkdtemp(prefix="tamper-anc-")) + "/proj"  # listed under protected_extra_dirs in a temp config
os.makedirs(PROJECT)
CFG = PROJECT + "/../config.json"
json.dump({"protected_extra_dirs": [PROJECT]}, open(CFG, "w"))
os.environ["CLAUDE_HOOKS_CONFIG"] = CFG
GUARDS = [os.path.join(HOME, ".claude", "hooks"), PROJECT + "/.claude/hooks"]
SHAPES = [  # {a} is the folder under test
    "rm -rf {a}", "mv {a} /tmp/moved", "rsync -a /tmp/evil/ {a}/", "cp -r /tmp/evil/. {a}/", "ditto /tmp/evil {a}",
    "git --work-tree={a} checkout x -- .", "git --work-tree {a} reset --hard", "git --git-dir=/tmp/e/.git --work-tree={a} clean -fdx",
    "GIT_WORK_TREE={a} git checkout x -- .", "env GIT_DIR=/tmp/e/.git GIT_WORK_TREE={a} git reset --hard",
    "export GIT_WORK_TREE={a}; git clean -fdx", "git -C / --work-tree={a_rel} checkout x -- .",
    "true && GIT_WORK_TREE={a} git checkout x -- .", "(GIT_WORK_TREE={a} git reset --hard)", "printf -v GIT_WORK_TREE {a}; git clean -fdx", "printf -v G''IT_WORK_TREE {a}; git clean -fdx",
    "export GIT_WORK\"_\"TREE={a}; git clean -fdx",
]
ALLOW = [("/tmp", "rm -rf /tmp/x"), ("/tmp", f"rsync -a /tmp/x/ {HOME}/notes/y/"), ("/tmp", "cp -r src/ /tmp/out/"),
         (GUARDS[1].rsplit("/.claude", 1)[0], "git checkout $BRANCH"), (GUARDS[1].rsplit("/.claude", 1)[0], "git rm src/a.ts"),
         ("/tmp", f"git --work-tree={GUARDS[1].rsplit('/.claude', 1)[0]} status")]


def ancestors(p):
    out = []
    while p not in ("/", ""):
        out.append(p)
        p = os.path.dirname(p)
    return out


def decide(cmd, cwd):
    p = subprocess.run([sys.executable, HOOK], capture_output=True, text=True, timeout=30,
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd}))
    if p.returncode:
        return f"ERROR rc={p.returncode}"
    return "deny" if '"deny"' in p.stdout else "allow"


fails = n = 0
for g in GUARDS:
    for a in ancestors(g):
        nxt = g[len(a) + 1:].split("/", 1)[0]  # the folder on the way down: a copy of a source with that name lands on it
        for s in SHAPES + [f"cp -r /tmp/evil/{nxt} {{a}}/", f"rsync -a /tmp/evil/{nxt} {{a}}/", f"cp -r /tmp/evil/* {{a}}/"]:
            n += 1
            cmd = s.format(a=a, a_rel=a.lstrip("/"))  # a_rel: relative to the -C / folder
            if decide(cmd, "/tmp") != "deny":
                fails += 1
                print(f"FAIL want deny: {cmd}")
for cwd, cmd in ALLOW:
    n += 1
    if decide(cmd, cwd) != "allow":
        fails += 1
        print(f"FAIL want allow: {cmd} (cwd {cwd})")
print(f"ancestors: {n} rows, {fails} failed")
sys.exit(1 if fails else 0)
