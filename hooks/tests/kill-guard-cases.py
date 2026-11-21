#!/usr/bin/env python3
"""Cases for kill-guard.py. Feeds the real hook a PreToolUse payload; exit 2 = deny. Exit 0 only if all pass."""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kill-guard.py")

DENY = [
    "pkill node", "pkill -f 'sleep 60$' -P 1", "killall node",
    "kill -1 -1", "kill -9 -1", "kill 0",
    "kill -- -0", "kill -TERM -- -0", "kill -9 -- -1",
    "kill -s TERM 0", "kill -s KILL -1", "kill -n 9 -1", "kill -s TERM -- -0",
    "sleep 1; kill -9 -1",
    # F6: quoted, wrapped, shell-built and obfuscated forms
    "kill '-1'", 'kill "0"', "bash -c 'kill -9 -1'", 'sh -c "kill 0"', "zsh -lc 'echo hi; kill -- -1'",
    "kill $(echo 0)", "kill `echo 0`", 'kill -- "$G"', "kill ${G}", "kill -TERM -- -$G",
    "p\\kill node", '"pkill" node', "pk''ill node", "/usr/bin/pkill node", "ki''llall node",
    "k''ill -9 -1", "bash -c \"bash -c 'kill 0'\"",
    # xargs kill, and pkill after wrappers or a subshell
    "pgrep -f vite | xargs kill", "pgrep -f vite | xargs -r kill", "pgrep node | xargs kill -9", "pgrep node | xargs -I{} kill {}",
    "sudo -u x pkill node", "xargs pkill", "(pkill node)", "echo hi && pkill node", "eval 'pkill node'", "find . -exec pkill {} \\;",
    # security review: pkill after shell keywords and launchers (any segment not starting with a text-only command counts)
    "if true; then pkill node; fi", "timeout 5 pkill node", "watch pkill node", "while true; do pkill node; done", "caffeinate pkill node",
    # re-review: unbalanced quotes, substitutions, pipes into a shell, xargs sh -c, padded pids, eval
    "echo it's; killall node", "cat <<EOF\nit's\nEOF\npkill node", "echo \"unbalanced; pkill node", "echo \"$(pkill node)\"",
    "echo `pkill node`", "git commit -m \"$(pkill -f node)\"", "cat < <(pkill node)", "cat x |& pkill node", "git status;; pkill node",
    "echo pkill node | sh", "pgrep node | xargs -I{} sh -c \"kill {}\"", "pgrep -f node | parallel kill",
    "kill -9 \" -1\"", "kill -KILL \" 0\"", "kill -9 -- \" -1\"", "kill -TERM 00", "eval \"kill 0\"", "eval \"kill -9 -1\"",
    "pkill${IFS}node", "pkill>/dev/null node", "{pkill,node}", "pkill,node",
    # git, gh and rg options that run a command are not text
    "git rebase -x 'pkill node' HEAD~1", "git bisect run pkill node", "rg --pre pkill x", "gh alias set --shell k 'pkill node'",
    "man -P pkill ls", "less +'!pkill node' f", "git -c alias.k='!pkill node' k", "git config alias.k '!pkill node'",
    "rg -z pkill x", "gh alias set k 'pkill node'", "git grep -Opkill x", "GIT_EXTERNAL_DIFF=pkill git diff", "git grep --open='pkill node;:' x",
    "git diff --ext=pkill", "git log -c x --format=pkill",
    # round 4: broad kill inside quotes or other languages
    "trap 'kill -1' EXIT", "perl -e 'kill 9, -1'", "ruby -e 'Process.kill(9,-1)'", "ruby -e 'Process.kill(9, 0)'",
    "python3 -c \"import subprocess;subprocess.run(['kill','-1'])\"", "python3 -c 'import os; os.kill(0, 9)'",
    "ssh localhost 'kill -1'", "watch 'kill -1'", "sh <<< 'kill -1'", "ssh h 'kill -9 -- -1'",
    "x" * 250_000 + " kill",  # over the size cap: put it in a script file
    "x" * 250_000 + " k''ill",  # split forms still count as the word
    "x" * 250_000 + " pkill node", "x" * 250_000 + " killall node",
    # loop 3, B: Node's process.kill takes the pid first, and the dot used to hide the word from the raw scan
    "node -e 'process.kill(-1, 9)'", "node -e \"process.kill(0, 'SIGKILL')\"", "node -e 'process.kill(0)'",
    "node -e \"process.kill('-1', 9)\"", "node -e \"process.kill(Number('0'), 9)\"; echo \"process.kill(' 0', 9)\"",  # the RULES regex needs a bare number; the raw scan reads quoted ones
]
ALLOW_RAW = [
    "python3 -c 'import os; os.kill(1234, 0)'", "ruby -e 'Process.kill(9, 1234)'", "ssh localhost 'kill -1 12345'",
    "trap 'kill 12345' EXIT", "python3 -c \"import subprocess;subprocess.run(['kill','-TERM','12345'])\"",
    "x" * 250_000,
    "x" * 250_000 + " skills", "x" * 250_000 + " skill",  # loop 3, C: the size refusal is for the word kill, not skill/skills
    "node -e 'process.kill(1234, 0)'", "node -e 'process.kill(1234, \"SIGTERM\")'", "npx kill-port 3000",  # loop 3, B
]
NO_DECISION = [None, ["kill", "-1"], 5]
ALLOW = [
    'echo "kill 0"',  # raw-text guard: the trailing quote hides the 0, same as before
    "kill 12345", "kill -TERM 12345", "kill -TERM -- -12345", "kill -1 12345",
    "kill -s TERM 12345", "kill -n 9 12345", "kill -0 12345", "pgrep node",
    "kill '12345'", "bash -c 'kill 12345'", "bash -c 'kill -TERM -- -12345'", "kill -1 12345; echo done",
    "bash -c 'echo hello'",
    # words that only mention pkill/killall
    "grep -n pkill notes.txt", "git commit -m 'docs: explain pkill block'", "echo pkill", "man killall",
    "pgrep -f vite | xargs echo", "kill 12345 | cat",
    "git show HEAD:kill-guard.py | grep pkill", "grep -rn killall docs/ | head -5",
    # re-review: file and branch names that contain the word are not commands
    "git checkout -b fix/pkill-guard", "git add hooks/pkill-notes.md", "mv notes.md pkill-notes.md", "find . -name '*pkill*'",
    "sed -n '/pkill/p' notes.md", "python3 tests/pkill-cases.py", "git commit --no-verify -m 'docs: pkill rule'",
    "git log --max-count=5 --grep pkill",
    "git commit --message='docs: pkill is blocked'", "git log --oneline --grep pkill", "git grep -n pkill -- '*.md'",
]

bad = 0
for cmd, want in [(c, 2) for c in DENY] + [(c, 0) for c in ALLOW]:
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": cmd}}),
                       capture_output=True, text=True, timeout=30)
    ok = p.returncode == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), "deny " if want == 2 else "allow", cmd, "" if ok else f"(exit {p.returncode})")
for cmd in ALLOW_RAW + NO_DECISION:
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": cmd}}),
                       capture_output=True, text=True, timeout=30)
    ok = p.returncode == 0 and "Traceback" not in p.stderr
    bad += not ok
    print(("PASS" if ok else "FAIL"), "allow", repr(cmd)[:60], "" if ok else f"(exit {p.returncode})")
print(f"{len(DENY) + len(ALLOW) + len(ALLOW_RAW) + len(NO_DECISION) - bad} passed, {bad} failed")
sys.exit(1 if bad else 0)
