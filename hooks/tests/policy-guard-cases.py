#!/usr/bin/env python3
"""Cases for policy-guard.py, the dispatcher. Every row is a JSON payload piped to the hook; nothing is sent anywhere and
nothing is run. The dispatcher starts the four real detectors next to it (stash-secret, commit, tamper, heavy), which only
read the command text and run local git queries in throwaway folders. No mocks.

Row format: (name, command, want, text the reason must hold). want is "deny" or None (no decision). A command row runs
in the background (run_in_background true) unless it says foreground, so heavy-guard's long-command rule stays quiet.
Prints `all N rows passed`. Exit 0 only if every row passes."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HOOKS, "policy-guard.py")  # argv[1]: judge another copy of the hook
TMP = tempfile.mkdtemp(prefix="policy-cases-")
CFG = os.path.join(TMP, "config.json")
json.dump({"fork_branches": ["release/legacy"]}, open(CFG, "w"))
STATE = os.path.join(TMP, "state")
os.makedirs(STATE)
ENV = {**os.environ, "CLAUDE_HOOKS_CONFIG": CFG, "HOOKS_STATE": STATE, "PRESSURE_FAKE": "OK"}
ENV.pop("HEAVY_GUARD_CRASH", None)
ATTR = os.path.join(TMP, "attr.txt")
open(ATTR, "w").write("fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
HOME = os.path.expanduser("~")
fails = total = 0


def run(cmd, hook=HOOK, env=None, background=True, cwd="/tmp", raw=None):
    ti = {"command": cmd, **({"run_in_background": True} if background else {})}
    payload = raw if raw is not None else json.dumps({"tool_name": "Bash", "tool_input": ti, "cwd": cwd, "session_id": "cases"})
    t0 = time.time()
    p = subprocess.run([sys.executable, hook], input=payload, capture_output=True, text=True, timeout=30, env=env or ENV)
    if p.returncode:
        return f"EXIT {p.returncode}", time.time() - t0
    if not p.stdout.strip():
        return None, time.time() - t0
    o = json.loads(p.stdout)["hookSpecificOutput"]
    return (o["permissionDecision"], o["permissionDecisionReason"]), time.time() - t0


def row(name, cmd, want, text="", **kw):
    global fails, total
    total += 1
    got, took = run(cmd, **kw)
    if want is None:
        ok = got is None
    else:
        ok = isinstance(got, tuple) and got[0] == want and text in got[1]
    ok = ok and took < 4.5
    if not ok:
        fails += 1
        print(f"FAIL {name}: got {got!r} in {took:.1f}s, want {want!r} {text!r}")


# Secrets and the environment (stash-secret-guard.py). Its gate is empty: every command reaches it.
for c in ("cat ~/.npmrc", "cat ~/.pypirc", "cat ~/.config/gh/hosts.yml", "cat ~/.docker/config.json", "cat ~/.ssh/id_ed25519",
          "cat ~/.ssh/id_ecdsa", "cat ~/.aws/sso/cache/x.json", "cat .env", "printenv", "env"):
    row(f"secret read denied: {c}", c, "deny", "Secret guard")
row("harmless cat is no decision", "cat README.md", None)
row("env file names only through the helper", f"python3 {HOOKS}/lib/env-keys.py .env.example", None)

# git stash in every shape
for c in ("git stash", "git stash pop", "git -C /tmp/x stash", "env git stash", "git status && git stash", "bash -c 'git stash'"):
    row(f"stash denied: {c}", c, "deny")
row("a word near stash in a commit message is allowed", "git commit -m 'docs: explain why we never stash'", None)

# free-disk: the flag check lives in lib/free-disk.py, so text that only names the flag is never blocked
row("quoted --yes is left to the tool", f"python3 {HOOKS}/lib/free-disk.py \"--yes\"", None)
row("grep for free-disk.py --yes is allowed", "grep -rn \"free-disk.py --yes\" docs/", None)
row("a commit message naming free-disk.py --yes is allowed", "git commit -m 'docs: note free-disk.py --yes behaviour'", None)
row("free-disk dry run is allowed", f"python3 {HOOKS}/lib/free-disk.py", None)

# Attribution and forks (commit-guard.py)
row("attribution trailer in -m", 'git commit -m "feat: x" -m "Co-Authored-By: Claude <c@x>"', "deny", "Attribution guard")
row("attribution trailer in a -F file", f"git commit -F {ATTR}", "deny", "Attribution guard")
row("clean commit message is allowed", 'git commit -m "feat: add the thing"', None)
row("a configured fork branch cannot be merged", "git merge release/legacy", "deny", "Fork guard")
row("an ordinary branch merges", "git merge feature/x", None)
row("force-adding .claude is denied", "git add -f .claude/skills/x.md", "deny", "Local-material guard")
row("plain add of a source file is allowed", "git add src/a.ts", None)

# Guard files and switches (tamper-guard.py)
row("write a hook through a redirect", f"echo x > {HOME}/.claude/hooks/commit-guard.py", "deny", "Tamper guard")
row("write settings through a variable", "H=$HOME/.claude; echo x > $H/settings.json", "deny", "Tamper guard")
row("create a guard switch", "touch ~/.claude/hooks/state/heavy-guard/NO_BACKGROUND_RULE", "deny", "Tamper guard")
row("reading a hook is allowed", f"cat {HOME}/.claude/hooks/commit-guard.py", None)
row("running a hook test is allowed", "python3 ~/.claude/hooks/tests/kill-guard-cases.py", None)

# Heavy and long commands (heavy-guard.py, fail open)
crit = {**ENV, "PRESSURE_FAKE": "CRITICAL"}
row("heavy command under CRITICAL memory is denied", "npm ci", "deny", "memory is critical", env=crit)
row("light command under CRITICAL memory is allowed", "git status", None, env=crit)
row("heavy command with room is allowed", "npm ci", None)
row("long command in the foreground is denied", "sleep 60", "deny", "run_in_background", background=False)
row("long command in the background is allowed", "sleep 60", None)
row("short command in the foreground is allowed", "ls -la", None, background=False)

# The dispatcher itself
row("a command over 40 KB is denied", "echo " + "x" * 41000, "deny", "over 40 KB")
row("garbage stdin is no decision", "", None, raw="not json")
row("a non-string command is no decision", "", None, raw=json.dumps({"tool_input": {"command": 5}}))

# A closed detector that cannot run must deny a command it could refuse, and an open one must let commands through.
broken = os.path.join(TMP, "broken")
os.makedirs(broken)
shutil.copy(HOOK, os.path.join(broken, "policy-guard.py"))
for name in ("stash-secret-guard.py", "commit-guard.py", "tamper-guard.py", "heavy-guard.py"):
    open(os.path.join(broken, name), "w").write("import sys\nsys.exit(1)\n")  # a detector that crashes
bh = os.path.join(broken, "policy-guard.py")
row("closed detector crashed: stash command is denied", "git stash", "deny", "could not run", hook=bh)
row("closed detector crashed: secret read is denied", "cat .env", "deny", "could not run", hook=bh)
row("closed detector crashed: guard write is denied", "echo x > ~/.claude/settings.json", "deny", "could not run", hook=bh)
row("closed detector crashed: harmless command is allowed", "ls -la", None, hook=bh)
row("open detector crashed: heavy command is allowed", "npm ci", None, hook=bh)
shutil.rmtree(os.path.join(broken, "stash-secret-guard.py"), ignore_errors=True)
os.remove(os.path.join(broken, "stash-secret-guard.py"))  # a missing detector behaves like a crashed one
row("closed detector missing: stash command is denied", "git stash", "deny", "could not run", hook=bh)

shutil.rmtree(TMP, ignore_errors=True)
print(f"all {total} rows passed" if not fails else f"{fails} of {total} rows FAILED")
sys.exit(1 if fails else 0)
