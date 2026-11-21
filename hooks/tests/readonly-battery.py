#!/usr/bin/env python3
"""Read-only battery: everyday read and dev commands must get NO decision from policy-guard.py
(no deny, no ask). Policy: reads and dev work never prompt or block.
Runs the real hook with HOME unchanged and writes nothing. One line per failure, then
"battery: N passed, M failed". Exit 1 on any failure. If a row fails, the policy has a gap:
fix the hook, never delete the row."""
import json
import os
import subprocess
import sys
import tempfile

# Scratch state dir: heavy-guard logs would-be denies there, never into your real decisions.jsonl.
STATE_DIR = tempfile.mkdtemp(prefix="battery-state-")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "policy-guard.py")
DASH = "/tmp/project"  # only a string: the hooks read the command text, not the folder
CWDS = [DASH, os.path.expanduser("~/worktrees/x"), "/tmp"]

# 20 commands run in every cwd (60 runs total counted as separate rows)
COMMANDS = [
    "git status", "git status --short", "git log --oneline -20", "git diff", "git diff --stat main",
    "git show HEAD --stat", "git branch --list", "git branch -a", "git fetch origin",
    "git worktree list", "git rev-parse --abbrev-ref HEAD", "git log --oneline origin/main..HEAD",
    "ls -la", "ls ~/.claude/hooks", "rg -n 'TODO' src | head -20", "grep -rn 'useQuery' src/features | head",
    "find src -name '*.tsx' -newer package.json", "cat package.json", "head -50 CLAUDE.md", "wc -l src/main.tsx",
    "jq '.scripts' package.json", "npm run lint", "npm test -- src/features/targets/ui.test.ts",
    "npx tsc --noEmit", "node scripts/check-env.mjs", "python3 scripts/report.py",
    "gh pr view 69", "gh pr list --state open", "gh pr checks 69",
    "docker ps", "docker ps -a --format '{{.ID}} {{.Names}}'", "docker logs mydb --tail 50",
    "psql -h localhost -p 5432 -U postgres -c 'select 1'",
    "psql postgresql://postgres@127.0.0.1:5432/postgres -c 'select count(*) from users'",
    "curl -s http://localhost:5173/", "curl -sI http://127.0.0.1:3000/health",
    "pwd", "which node", "node --version", "date -u",
    "git log -1 --format=%H", "git diff HEAD~1 --name-only", "git ls-files | wc -l",
    "git remote -v", "git config --get user.name",
    "sort -u list.txt | uniq -c | head", "tr a-z A-Z < README.md | head -3",
    "sed -n '171,215p' ~/.claude/skills/example-skill/SKILL.md",
    "cat ~/plans/notes.md | cut -c1-300",
    "ls ~/plans", "stat package.json", "diff package.json package-lock.json | head",
    "npm run build", "npm ls react", "git blame -L 1,20 src/main.tsx",
]


# Foreground pass (no run_in_background): these must stay allowed when run in the foreground.
FOREGROUND = [
    "npm run lint", "npm test -- src/features/targets/ui.test.ts", "npx tsc --noEmit",
    "git status", "git log --oneline -20", "git diff --stat main", "git show HEAD --stat", "git branch -a", "git blame -L 1,20 src/main.tsx",
    "gh pr view 69", "gh pr list --state open", "gh pr checks 69",
    "ls -la", "cat package.json", "rg -n 'TODO' src | head -20", "docker ps",
]
# Foreground long builds are refused with the run-in-background hint (heavy-guard rule e).
FG_DENY = ["npm run build", "npm ci"]
HINT = "run_in_background"


def run(cmd, cwd, background=True):
    # The background pass tests the permission policy; long commands in the foreground are refused on purpose
    # (heavy-guard rule e) and the foreground pass below pins exactly which ones.
    tool_input = {"command": cmd, **({"run_in_background": True} if background else {})}
    payload = {"tool_name": "Bash", "tool_input": tool_input, "cwd": cwd, "session_id": "battery"}
    p = subprocess.run(["python3", HOOK], input=json.dumps(payload), capture_output=True, text=True, timeout=30,
                       env={**os.environ, "HOOKS_STATE": STATE_DIR})
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def main():
    passed = failed = 0
    rows = [(c, CWDS[i % 3]) for i, c in enumerate(COMMANDS)]  # rotate cwds
    rows += [(c, w) for c in COMMANDS[:6] for w in CWDS if w != CWDS[COMMANDS.index(c) % 3]]  # git reads in all 3
    for cmd, cwd in rows:
        out, err, rc = run(cmd, cwd)
        if out or rc != 0:
            failed += 1
            print(f"FAIL [{cwd}] {cmd} -> rc={rc} out={out[:200]!r} err={err[:120]!r}")
        else:
            passed += 1
    print(f"battery (background): {passed} passed, {failed} failed")
    fg_passed = fg_failed = 0
    for cmd in FOREGROUND:
        out, err, rc = run(cmd, DASH, background=False)
        if out or rc != 0:
            fg_failed += 1
            print(f"FAIL foreground allow [{DASH}] {cmd} -> rc={rc} out={out[:200]!r}")
        else:
            fg_passed += 1
    for cmd in FG_DENY:
        out, err, rc = run(cmd, DASH, background=False)
        if rc == 0 and '"deny"' in out and HINT in out:
            fg_passed += 1
        else:
            fg_failed += 1
            print(f"FAIL foreground deny [{DASH}] {cmd} -> rc={rc} out={out[:200]!r}")
    print(f"battery (foreground): {fg_passed} passed, {fg_failed} failed")
    print(f"battery: {passed + fg_passed} passed, {failed + fg_failed} failed")
    sys.exit(1 if failed or fg_failed else 0)


if __name__ == "__main__":
    main()
