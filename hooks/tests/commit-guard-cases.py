#!/usr/bin/env python3
"""Cases for commit-guard.py. Real temp git repos give the current-branch checks. Run: python3 commit-guard-cases.py"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.environ.get("HOOK") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "commit-guard.py")
tmp = tempfile.mkdtemp(prefix="commit-guard-")
json.dump({"fork_branches": ["release/legacy", "fork/tools"]}, open(os.path.join(tmp, "config.json"), "w"))
os.environ["CLAUDE_HOOKS_CONFIG"] = os.path.join(tmp, "config.json")  # the hook reads its fork list from here
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(d, *a):
    subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, env=ENV)


def repo(name, on):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    git(d, "init", "-q", "-b", "main")
    git(d, "commit", "-q", "--allow-empty", "-m", "init")
    for b in ("release/legacy", "fork/tools", "feature/x"):
        git(d, "branch", b)
    git(d, "checkout", "-q", on)
    return d


MAIN, DEMO, SKILLS, FX = repo("m", "main"), repo("d", "release/legacy"), repo("s", "fork/tools"), repo("x", "feature/x")
open(os.path.join(tmp, "attr.txt"), "w").write("fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
open(os.path.join(tmp, "clean.txt"), "w").write("fix: claude settings path\n")
open(os.path.join(tmp, "gen.md"), "w").write("body\n\nGenerated with [Claude Code](https://claude.com)\n")

open(os.path.join(tmp, "empty.txt"), "w").write("")
os.mkfifo(os.path.join(tmp, "fifo.txt"))
for _d in (".claude", "specs/001", "src"):
    os.makedirs(os.path.join(MAIN, _d), exist_ok=True)

HEREDOC = """git commit -m "$(cat <<'EOF'
fix: thing

Co-Authored-By: Claude Opus <noreply@anthropic.com>
EOF
)\""""
HEREDOC_OK = """git commit -m "$(cat <<'EOF'
fix: claude settings path
EOF
)\""""

# (expect deny?, cwd, command)
CASES = [
    # forks: merge
    (1, MAIN, "git merge release/legacy"),
    (1, MAIN, "git merge --no-ff release/legacy"),
    (1, MAIN, "git merge --squash release/legacy"),
    (1, MAIN, "git merge fork/tools"),
    (1, MAIN, "git merge origin/release/legacy"),
    (1, MAIN, "git merge refs/heads/fork/tools"),
    (1, MAIN, "git merge -m 'x' --no-ff origin/fork/tools"),
    (1, FX, "git merge release/legacy"),
    (1, SKILLS, "git merge release/legacy"),
    (1, DEMO, "git merge fork/tools"),
    (1, "/", f"git -C {MAIN} merge release/legacy"),
    (1, MAIN, "git -c merge.ff=false merge fork/tools"),
    (1, MAIN, "cd " + MAIN + " && git merge release/legacy"),
    (1, MAIN, "bash -c 'git merge release/legacy'"),
    (1, MAIN, "git merge release/legacy~2"),
    # forks: pull, rebase, cherry-pick
    (1, MAIN, "git pull origin release/legacy"),
    (1, MAIN, "git pull --no-rebase origin fork/tools"),
    (1, MAIN, "git rebase release/legacy"),
    (1, MAIN, "git rebase --onto fork/tools main"),
    (1, MAIN, "git cherry-pick release/legacy"),
    (1, MAIN, "git cherry-pick main..release/legacy"),
    (1, MAIN, "git cherry-pick origin/fork/tools~3..origin/fork/tools"),
    # forks: gh
    (1, MAIN, "gh pr create --head release/legacy --base main"),
    (1, MAIN, "gh pr create --head=fork/tools --base=main --title x"),
    (1, MAIN, "gh pr create -H release/legacy -B main"),
    (1, MAIN, "gh pr create --head release/legacy"),
    (1, DEMO, "gh pr create --base main"),
    (1, MAIN, "gh pr merge release/legacy --squash"),
    # forks allowed
    (0, DEMO, "git merge main"),
    (0, DEMO, "git merge origin/main"),
    (0, DEMO, "git merge release/legacy"),
    (0, SKILLS, "git merge fork/tools"),
    (0, DEMO, "git pull origin release/legacy"),
    (0, DEMO, "git rebase main"),
    (0, MAIN, "git merge main"),
    (0, FX, "git merge main"),
    (0, MAIN, "git merge feature/x"),
    (0, MAIN, "git merge --no-ff feature/x -m 'merge release/legacy notes'"),
    (0, MAIN, "git rebase main release/legacy"),
    (0, MAIN, "git cherry-pick abc123"),
    (0, MAIN, "git log release/legacy"),
    (0, MAIN, "git diff main..release/legacy"),
    (0, MAIN, "git checkout release/legacy"),
    (0, MAIN, "git push origin release/legacy"),
    (0, MAIN, "gh pr create --head feature/x --base main"),
    (0, MAIN, "gh pr create --head release/legacy --base plan/x"),
    (0, FX, "gh pr create --base main"),
    (0, MAIN, "gh pr list --head release/legacy"),
    # attribution: git commit
    (1, MAIN, 'git commit -m "feat: x" -m "Co-Authored-By: Claude <noreply@anthropic.com>"'),
    (1, MAIN, 'git commit -am "feat: x\n\nCo-Authored-By: Claude Opus 4 <noreply@anthropic.com>"'),
    (1, MAIN, "git commit --message='x Co-Authored-By: Anthropic <a@anthropic.com>'"),
    (1, MAIN, 'git commit -m "co-authored-by: claude"'),
    (1, MAIN, 'git commit -m "feat: x" -m "Generated with Claude Code"'),
    (1, MAIN, 'git commit -m "🤖 Generated with [Claude Code](https://claude.com/claude-code)"'),
    (1, MAIN, HEREDOC),
    (1, MAIN, "git commit -F " + os.path.join(tmp, "attr.txt")),
    (1, MAIN, "git commit --file=" + os.path.join(tmp, "attr.txt")),
    (1, MAIN, "git -C " + MAIN + " commit -m 'x' -m 'Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, 'git add -A && git commit -m "x\nCo-Authored-By: Claude <c@x>"'),
    # attribution: gh
    (1, MAIN, 'gh pr create --title t --body "Generated with Claude Code"'),
    (1, MAIN, 'gh pr edit 5 --body "Co-Authored-By: Claude <c@x>"'),
    (1, MAIN, "gh pr create --title t --body-file " + os.path.join(tmp, "gen.md")),
    (1, MAIN, "gh pr create -t t -F " + os.path.join(tmp, "attr.txt")),
    # attribution allowed
    (0, MAIN, 'git commit -m "fix: claude settings path"'),
    (0, MAIN, 'git commit -m "docs: add Anthropic API note"'),
    (0, MAIN, 'git commit -m "feat: x" -m "Co-Authored-By: Dev <d@example.com>"'),
    (0, MAIN, HEREDOC_OK),
    (0, MAIN, "git commit -F " + os.path.join(tmp, "clean.txt")),
    (0, MAIN, "git commit -F /nonexistent/file"),
    (0, MAIN, "git log --grep Co-Authored"),
    (0, MAIN, 'git log --grep "Co-Authored-By: Claude"'),
    (0, MAIN, 'echo "Co-Authored-By: Claude"'),
    (0, MAIN, 'gh pr create --title t --body "adds claude settings"'),
    (0, MAIN, "gh pr create -t t -F " + os.path.join(tmp, "clean.txt")),
    (0, MAIN, "ls -la"),
    (0, MAIN, "git status"),
    (0, MAIN, "git commit -m 'unterminated"),
    # F7: prefixes and quote tricks before git commit
    (1, MAIN, "GIT_AUTHOR_NAME=x git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "env X=1 git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "command git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "git -C /tmp commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "git -c user.name=x commit -m 'Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "git commit -m 'Co-Authored-''By: Claude <c@x>'"),
    (1, MAIN, 'git commit -m "Co-Authored-"By": Claude"'),
    (1, MAIN, "env X=1 git commit -F " + os.path.join(tmp, "attr.txt")),
    (1, MAIN, "gh -R o/r pr create --body 'Generated with Claude Code'"),
    (0, MAIN, "env X=1 git commit -m 'fix: claude settings path'"),
    # F13: options after a prefix word
    (1, MAIN, "env -i git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "nice -n 5 git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "sudo -u x git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (1, MAIN, "env -u FOO git commit -m 'x Co-Authored-By: Claude <c@x>'"),
    (0, MAIN, "nice -n 5 git commit -m 'fix: claude settings path'"),
    (0, MAIN, "GIT_AUTHOR_NAME=x git status"),
    # F15: gh global flags, FETCH_HEAD after a fork fetch
    (1, MAIN, "gh -R owner/repo pr create --head fork/tools --base main"),
    (1, MAIN, "gh --repo owner/repo pr create --head release/legacy"),
    (1, MAIN, "gh -R o/r pr merge release/legacy --squash"),
    (1, MAIN, "git fetch origin fork/tools && git merge FETCH_HEAD"),
    (1, MAIN, "git fetch origin release/legacy; git merge --no-ff FETCH_HEAD"),
    (1, MAIN, "git fetch origin fork/tools && git cherry-pick FETCH_HEAD"),
    (0, DEMO, "git fetch origin release/legacy && git merge FETCH_HEAD"),
    (0, MAIN, "git fetch origin main && git merge FETCH_HEAD"),
    (0, MAIN, "git merge FETCH_HEAD"),
    (0, MAIN, "gh -R o/r pr create --head feature/x --base main"),
    (0, MAIN, "gh -R o/r pr list"),
    # file read by command substitution
    (1, tmp, 'git commit -m "$(cat attr.txt)"'),
    (1, tmp, 'git commit -m "$(< attr.txt)"'),
    (1, tmp, 'M=$(cat attr.txt); git commit -m "$M"'),
    (1, tmp, 'git commit -m "`cat attr.txt`"'),
    (1, MAIN, 'gh pr create --body "$(cat ' + os.path.join(tmp, "gen.md") + ')"'),
    (0, tmp, 'git commit -m "$(cat clean.txt)"'),
    (0, tmp, 'git commit -m "$(< clean.txt)"'),
    (0, tmp, 'git commit -m "$(cat missing-file.txt)"'),
    # force-adding local working material
    (1, MAIN, "git add -f .claude/skills/x.md"),
    (1, MAIN, "git add --force specs/001/spec.md"),
    (1, MAIN, "git add -fA .claude"),
    (1, FX, "git add -f ./specs/a.md"),
    (0, MAIN, "git add .claude/skills/x.md"),
    (0, MAIN, "git add -f src/specs/a.ts"),
    (0, MAIN, "git add -f src/app.ts"),
    # round 3 A: message files read through stdin, pipes, other readers, -C
    (1, tmp, "git commit -F - < attr.txt"),
    (1, tmp, "cat attr.txt | git commit -F -"),
    (1, tmp, 'git commit -m "$(cat < attr.txt)"'),
    (1, tmp, 'git commit -m "$(/bin/cat attr.txt)"'),
    (1, tmp, 'git commit -m "$(command cat attr.txt)"'),
    (1, tmp, 'git commit -m "$(cat -n attr.txt)"'),
    (1, tmp, 'git commit -m "$(cat empty.txt attr.txt)"'),
    (1, tmp, 'git commit -m "$(head -n 5 attr.txt)"'),
    (1, tmp, 'git commit -m "$(tail attr.txt)"'),
    (1, tmp, 'git commit -m "$(sed -n p attr.txt)"'),
    (1, tmp, 'read -r M < attr.txt; git commit -m "$M"'),
    (1, "/", "git -C " + tmp + ' commit -m "$(cat attr.txt)"'),
    (1, tmp, 'gh pr create --body "$(cat < gen.md)"'),
    (1, tmp, 'git commit -m "$(cat $MSGFILE)"'),
    (1, tmp, 'git commit -m "$(cat "$DIR/m.txt")"'),
    (1, tmp, "cat attr.txt | git commit -F -"),
    (0, tmp, "git commit -F - < clean.txt"),
    (0, tmp, "cat clean.txt | git commit -F -"),
    (0, tmp, 'git commit -m "$(cat < clean.txt)"'),
    (0, tmp, 'git commit -m "$(head -n 5 clean.txt)"'),
    (0, tmp, 'read -r M < clean.txt; git commit -m "$M"'),
    (0, tmp, 'git commit -m "$(cat fifo.txt)"'),  # a FIFO is skipped, never read (a read would hang)
    (0, tmp, "git commit -m 'fix: x' && cat $LOG"),
    (0, tmp, "git commit -m 'fix: x' && cat attr.txt"),  # a later unrelated cat is not the message source
    # round 3 B: forced add of local material in every spelling
    (1, MAIN, "git add --fo .claude/x"),
    (1, MAIN, "git add --forc .claude/x"),
    (1, MAIN, "git stage -f .claude/x"),
    (1, MAIN, "git update-index --add .claude/x"),
    (1, MAIN, "cd .claude && git add -f x"),
    (1, MAIN, "cd specs/001 && git add -f spec.md"),
    (1, MAIN, "git -C .claude add -f x"),
    (1, MAIN, "git add -f .cl*"),
    (1, MAIN, "git add -f ':(glob).claude/**'"),
    (1, MAIN, "git add -f --pathspec-from-file=list.txt"),
    (0, MAIN, "git add -f src/specs/x.ts"),
    (0, MAIN, "cd src && git add -f app.ts"),
    (0, MAIN, "git -C src add -f app.ts"),
    (0, MAIN, "git update-index --refresh"),
    (0, MAIN, "git stage src/app.ts"),
]


def run(cwd, cmd):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": cmd}, "cwd": cwd}), capture_output=True, text=True, timeout=30)
    if p.returncode:  # a crash must fail the row, not read as "allow"
        raise RuntimeError(f"hook exited {p.returncode}: {p.stderr[-200:]}")
    return "deny" in p.stdout


bad = 0
for want, cwd, cmd in CASES:
    try:
        got = run(cwd, cmd)
    except Exception as e:  # timeout or non-zero exit
        got = f"error: {e}"
    if got != bool(want):
        bad += 1
        print(f"FAIL want={'deny' if want else 'allow'} cwd={os.path.basename(cwd)} cmd={cmd[:90]!r}")
# crash row: garbage payload must produce no output and exit 0
p = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
if p.stdout or p.returncode:
    bad += 1
    print("FAIL crash row: garbage payload")
print(f"{len(CASES) + 1} rows, {bad} failed")
sys.exit(1 if bad else 0)
