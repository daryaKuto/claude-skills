#!/usr/bin/env python3
"""Cases for tamper-guard.py. The hook only reads the command text; nothing here is executed. Run: python3 tamper-guard-cases.py"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.environ.get("HOOK") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tamper-guard.py")
H = "~/.claude/hooks"
HOME = os.path.expanduser("~")
A = f"{HOME}/.claude/hooks"
CWD = f"{HOME}/Documents"
# A throwaway project folder that config.json lists under protected_extra_dirs, a symlinked spelling of it, and a folder of worktrees (lane_dirs).
TMP = os.path.realpath(tempfile.mkdtemp(prefix="tamper-cases-"))
DASH = f"{TMP}/real/app"
DASHLINK = f"{TMP}/link/app"  # TMP/link is a symlink to TMP/real
LANES = f"{TMP}/lanes"
os.makedirs(DASH)
os.symlink(f"{TMP}/real", f"{TMP}/link")
CFG = f"{TMP}/config.json"
json.dump({"protected_extra_dirs": [DASH], "lane_dirs": [LANES]}, open(CFG, "w"))
os.environ["CLAUDE_HOOKS_CONFIG"] = CFG  # every subprocess below inherits it

# (expect deny?, cwd, command)
CASES = [
    # denied: writes to hooks, every verb and every spelling of the path
    (1, CWD, f"echo x > {H}/commit-guard.py"),
    (1, CWD, f"echo x >> {H}/commit-guard.py"),
    (1, CWD, f"echo x >{A}/policy-guard.py"),
    (1, CWD, f"echo x > $HOME/.claude/hooks/policy-guard.py"),
    (1, CWD, f"echo x > ${{HOME}}/.claude/hooks/policy-guard.py"),
    (1, CWD, f"echo x | tee {H}/a.py"),
    (1, CWD, f"echo x | tee -a {A}/a.py"),
    (1, CWD, f"sed -i 's/a/b/' {H}/commit-guard.py"),
    (1, CWD, f"sed -i.bak 's/a/b/' {H}/commit-guard.py"),
    (1, CWD, f"perl -pi -e 's/a/b/' {H}/commit-guard.py"),
    (1, CWD, f"cp /tmp/x {H}/commit-guard.py"),
    (1, CWD, f"cp -t {H} /tmp/x"),
    (1, CWD, f"mv /tmp/x {H}/commit-guard.py"),
    (1, CWD, f"mv {H}/commit-guard.py /tmp/x"),
    (1, CWD, f"rm {H}/commit-guard.py"),
    (1, CWD, f"rm -rf {H}"),
    (1, CWD, f"rm -f {H}/tests/*.py"),
    (1, CWD, f"rm {H}/*.py"),
    (1, CWD, f"touch {H}/new-guard.py"),
    (1, CWD, f"chmod -x {H}/commit-guard.py"),
    (1, CWD, f"ln -sf /tmp/evil.py {H}/commit-guard.py"),
    (1, CWD, f"truncate -s 0 {H}/commit-guard.py"),
    (1, CWD, f"dd if=/dev/null of={H}/commit-guard.py"),
    (1, CWD, f"python3 -c \"open('{A}/commit-guard.py','w').write('')\""),
    (1, CWD, f"node -e \"require('fs').writeFileSync('{A}/x.js','')\""),
    (1, CWD, f"python3 - <<'EOF'\nopen('{A}/x.py','w').write('')\nEOF"),
    (1, A, "echo x > commit-guard.py"),
    (1, f"{HOME}/.claude", "echo x > hooks/commit-guard.py"),
    (1, CWD, f"cd {H} && rm commit-guard.py"),
    (1, CWD, f"bash -c 'rm {H}/commit-guard.py'"),
    (1, CWD, f"env X=1 rm {H}/commit-guard.py"),
    (1, CWD, f"find {H} -name '*.py' -delete"),
    # git env names are refused only in assignment position; a mere mention is allowed
    (0, CWD, "grep -rn GIT_DIR src"), (0, CWD, "echo $GIT_DIR"), (0, CWD, 'git commit -m "docs: GIT_WORK_TREE note"'),
    (0, CWD, "unset GIT_DIR"), (1, CWD, "GIT_DIR=src git status"), (1, CWD, "GIT_INDEX_FILE+=x git status"),
    (1, CWD, "read GIT_DIR"), (1, CWD, "for GIT_DIR in a b; do git status; done"), (1, CWD, "declare -x GIT_COMMON_DIR"),
    (1, CWD, "bash -c 'echo hi; GIT_DIR=src git status'"), (0, CWD, "bash -c 'echo hi; GIT_DIR=/x git status'"),
    # other files that switch guards off (Bash writes denied, reads allowed)
    (1, CWD, "touch ~/.claude/guard-bin/pkill"), (1, CWD, "echo x > ~/.claude/guard-bin/killall"), (1, CWD, "rm -rf ~/.claude/watchdog"),
    (1, CWD, "echo x >> ~/.zshenv"), (1, CWD, "sed -i 's/a/b/' ~/.zshenv"), (1, CWD, "echo x > ~/Library/LaunchAgents/com.x.disk-watchdog.plist"),
    (1, CWD, f"echo {{}} > {LANES}/wt-a/.claude/settings.json"), (1, CWD, f"cp /tmp/x {LANES}/zz/.claude/settings.local.json"),
    (0, CWD, "cat ~/.claude/guard-bin/pkill"), (0, CWD, "cat ~/.zshenv"), (0, CWD, "ls ~/.claude/watchdog"),
    (0, CWD, "echo x > ~/Library/LaunchAgents/com.x.other.plist"), (0, CWD, f"echo x > {LANES}/wt-a/src/a.ts"),
    # a find over a parent of the guard folders is allowed only with the '*/.claude/*' exclusion before -delete/-exec
    (1, DASH, "find . -name '*.orig' -delete"),
    (1, DASH, "find . -name '*.log' -exec rm {} +"),
    (0, DASH, "find . -not -path '*/.claude/*' -name '*.orig' -delete"),
    (0, DASH, "find . -name '*.log' -not -path '*/.claude/*' -exec rm {} +"),
    (1, DASH, "find . -delete -not -path '*/.claude/*'"),
    (1, DASH, "find . -not -path '*/.claude/*' -name a -o -name b -delete"),
    (1, DASH, "find . -not -path '*/node_modules/*' -name '*.orig' -delete"),
    (1, HOME, "find . -not -path '*/.claude/*' -name '*.orig' -delete; find ~/.claude/hooks -delete"),
    (0, DASH, "find src -name '*.orig' -delete"),
    # the exemption holds only for a STRICT ancestor of a .claude folder (printed paths from inside .claude lack the leading /.claude/)
    (1, DASH + "/.claude", "find . -not -path '*/.claude/*' -name '*.py' -delete"),
    (1, DASH, "find .claude/hooks -not -path '*/.claude/*' -delete"),
    (1, DASH, "find .claude -not -path '*/.claude/*' -name '*.json' -exec rm {} +"),
    (1, f"{HOME}/.claude", "find . -not -path '*/.claude/*' -name '*.py' -delete"),
    (1, CWD, f"ls {H} | xargs rm"),
    (1, CWD, f"curl -o {H}/x.py https://example.com/x"),
    (1, CWD, f"rm -rf {H}/../hooks"),
    # denied: settings and switches
    (1, CWD, "echo '{}' > ~/.claude/settings.json"),
    (1, CWD, "echo '{}' > ~/.claude/settings.local.json"),
    (1, CWD, "sed -i 's/a/b/' $HOME/.claude/settings.json"),
    (1, CWD, "rm ~/.claude/settings.json"),
    (1, CWD, "touch ~/.claude/NO_BACKGROUND_RULE"),
    (1, CWD, "touch ~/.claude/OFF-commit-guard"),
    (1, CWD, f"touch {H}/state/OFF-heavy-guard"),
    (1, CWD, f"touch {H}/state/NO_BACKGROUND_RULE"),
    (1, CWD, f"touch {H}/state/NO_ANYTHING"),
    (1, CWD, f"echo 1 > {H}/state/OFF-tamper-guard"),
    (1, CWD, f"rm {H}/state/heavy-guard/ENFORCE_LOCK"),
    # allowed: reads and runs
    (0, CWD, f"cat {H}/commit-guard.py"),
    (0, CWD, f"grep -n split {H}/commit-guard.py"),
    (0, CWD, f"ls -la {H}"),
    (0, CWD, f"sed -n '1,20p' {H}/commit-guard.py"),
    (0, CWD, f"head -5 {H}/tamper-guard.py"),
    (0, CWD, f"git -C {H} log --oneline"),
    (0, CWD, f"git -C {H} diff"),
    (0, CWD, f"git -C {H} status"),
    (0, CWD, f"git -C {H} add commit-guard.py tests/commit-guard-cases.py"),
    (0, CWD, f"git -C {H} commit -m 'fix: x'"),
    (0, CWD, f"python3 {H}/tests/commit-guard-cases.py"),
    (0, CWD, f"python3 {H}/tests/readonly-battery.py"),
    (0, CWD, f"python3 {H}/commit-guard.py < /tmp/payload.json"),
    (0, CWD, f"python3 -c \"print(open('{A}/commit-guard.py').read())\""),
    (0, CWD, f"cp {H}/commit-guard.py /tmp/backup.py"),
    (0, CWD, f"cp -r {H} /tmp/hooks-copy"),
    (0, CWD, f"ln -s {H}/commit-guard.py /tmp/link"),
    (0, CWD, f"echo x 2>&1 | cat {H}/a.py"),
    (0, CWD, f"grep '>' {H}/commit-guard.py"),
    (0, CWD, f"find {H} -name '*.py'"),
    (0, A, "ls"),
    (0, A, "git log -3"),
    # allowed: writes elsewhere
    (0, CWD, "echo x > /tmp/out.txt"),
    (0, CWD, "touch ~/.claude/projects/note.txt"),
    (0, CWD, "echo x > ~/.claude/settings-notes.txt"),
    (0, CWD, "echo x > ~/.claude/plans/settings.json"),
    (0, CWD, "rm -rf /tmp/old"),
    (0, CWD, "sed -i 's/a/b/' src/app.ts"),
    (0, CWD, "echo x > ~/NO_NOTES"),
    (0, CWD, "echo x > hooks.txt"),
    (0, CWD, "python3 -c \"open('/tmp/x','w').write('hooks')\""),
    # allowed: hook state files and the stricter lock
    (0, CWD, f"echo 1 > {H}/state/mem/last"),
    (0, CWD, f"touch {H}/state/heavy-guard/lock"),
    (0, CWD, f"rm -rf {H}/state/mem/old"),
    (0, CWD, f"touch {H}/state/heavy-guard/ENFORCE_LOCK"),
    (0, CWD, f"echo 1 > {A}/state/heavy-guard/ENFORCE_LOCK"),
    (0, CWD, "echo 'unterminated > ~/.claude/x"),
    # F5: git that rewrites or changes the hooks repo (log, diff, status, show, add, commit stay allowed, see above)
    (1, CWD, f"git -C {H} reset --hard abc123"),
    (1, CWD, f"git -C {H} checkout -- commit-guard.py"),
    (1, CWD, f"git -C {H} restore commit-guard.py"),
    (1, CWD, f"git -C {H} apply /tmp/x.diff"),
    (1, CWD, f"git -C {H} am /tmp/x.patch"),
    (1, CWD, f"git -C {H} revert HEAD"),
    (1, CWD, f"git -C {H} clean -fd"),
    (1, CWD, f"git -C {H} config core.hooksPath /tmp"),
    (1, CWD, f"git -C {H} stash"),
    (1, CWD, f"git --git-dir={H}/.git reset --hard"),
    (1, CWD, f"git --git-dir {H}/.git --work-tree {H} checkout ."),
    (1, A, "git reset --hard HEAD~1"),
    (1, A, "git restore ."),
    (0, CWD, "git reset --hard"),
    (0, CWD, f"git -C {H} show HEAD"),
    (0, CWD, f"git -C {H} log -3"),
    # G2: allowlist, everything else against the hooks repo is refused
    (1, CWD, f"git -C {H} update-index --assume-unchanged x"),
    (1, CWD, f"git -C {H} checkout-index -f -a"),
    (1, CWD, f"git -C {H} read-tree HEAD~1"),
    (1, CWD, f"git -C {H} worktree add /tmp/w"),
    (1, CWD, f"git -C {H} symbolic-ref HEAD refs/heads/x"),
    (1, CWD, f"git -C {H} hash-object -w x"),
    (1, CWD, f"git -C {H} replace a b"),
    (1, CWD, f"git -C {H} branch -D x"),
    (0, CWD, f"git -C {H} branch --list"),
    (0, CWD, f"git -C {H} tag --list"),
    (0, CWD, f"git -C {H} blame commit-guard.py"),
    (0, CWD, f"git -C {H} ls-files"),
    (0, CWD, f"git -C {H} rev-parse HEAD"),
    # G1: interpreter code that names a protected path and can write is refused unless it is a known read-only shape
    (1, CWD, f"python3 -c \"import os as o; getattr(o,'remo'+'ve')('{A}/x.py')\""),
    (1, CWD, f"python3 -c \"f=open; f('{A}/x.py','w')\""),
    (1, CWD, f"python3 -c \"import pathlib as p; p.Path('{A}/x.py').write_text('')\""),
    (1, CWD, f"perl -e \"open(F,'>{A}/x.py')\""),
    (0, CWD, f"python3 -c \"from pathlib import Path; print(Path('{A}/tests/x.json').read_text())\""),
    (0, CWD, f"python3 -c \"print(open('{A}/tests/x.json','rb').read())\""),
    (1, CWD, f"patch {H}/commit-guard.py /tmp/x.diff"),
    (1, CWD, f"patch -d {H} -p1 -i /tmp/x.diff"),
    (1, A, "patch -p1 -i /tmp/x.diff"),
    (0, CWD, "patch -p1 -i /tmp/x.diff"),
    # F6: other write forms
    (1, CWD, f"echo x >| {H}/commit-guard.py"),
    (1, CWD, f"echo \"\\\"\" > {H}/commit-guard.py"),
    (1, CWD, f"ln {H}/commit-guard.py /tmp/hard"),
    (1, CWD, f"cp -l {H}/commit-guard.py /tmp/hard"),
    (0, CWD, f"cp {H}/commit-guard.py /tmp/copy"),
    (1, CWD, f"sed -n 'w {H}/commit-guard.py' /tmp/x"),
    (1, CWD, f"sed 's/a/b/w {H}/commit-guard.py' /tmp/x"),
    (0, CWD, "sed -n 'w /tmp/out' /tmp/x"),
    (1, CWD, f"awk 'BEGIN{{print \"x\" > \"{A}/commit-guard.py\"}}'"),
    (0, CWD, "awk 'BEGIN{print \"x\" > \"/tmp/out\"}'"),
    (1, CWD, f"pushd {H} && rm commit-guard.py"),
    (1, CWD, f"pushd {H} >/dev/null; popd; pushd {H}; echo x > a.py"),
    (1, CWD, f"ditto /tmp/x {H}/commit-guard.py"),
    (1, CWD, f"xattr -w a b {H}/commit-guard.py"),
    (0, CWD, f"xattr -l {H}/commit-guard.py"),
    (1, CWD, f"chflags uchg {H}/commit-guard.py"),
    (1, CWD, f"tar -xf /tmp/a.tar -C {H}"),
    (1, CWD, f"tar xf /tmp/a.tar --directory={H}"),
    (1, A, "tar -xf /tmp/a.tar"),
    (1, CWD, f"tar -cf {H}/x.tar /tmp/y"),
    (0, CWD, f"tar -cf /tmp/x.tar {H}"),
    (0, CWD, "tar -xf /tmp/a.tar -C /tmp/out"),
    # F7: a NUL byte
    (1, CWD, "echo x > /tmp/a\x00b"),
    # F12: read-only interpreter code that only mentions a protected path is allowed
    (0, CWD, f"python3 -c \"import json; print(json.load(open('{HOME}/.claude/settings.json'))['env'])\""),
    # G3: a read shape next to anything else is not the read-only template, so the protected path is not laundered out
    (1, CWD, f"python3 -c \"d=json.load(open('{A}/tests/x.json')); open('/tmp/out','w').write(str(d))\""),
    (1, CWD, f"python3 -c \"print(open('{A}/tests/x.json').read()); open('{A}/x.py','w')\""),
    (1, CWD, f"python3 -c \"print(open('{A}/x.json').read()); import os; os.remove('{A}/x.py')\""),
    (1, CWD, f"python3 - <<'EOF'\nimport json\nprint(json.load(open('{A}/tests/x.json')))\nEOF"),
    # G4: allowed git subcommands with options that write a file or run a program
    (1, CWD, f"git -C {H} log --output=/tmp/x"),
    (1, CWD, f"git -C {H} diff --out=/tmp/x"),
    (1, CWD, f"git -C {H} grep -O vim foo"),
    (1, CWD, f"git -C {H} diff --ext-diff"),
    (1, CWD, f"git -C {H} show --textconv HEAD"),
    (1, CWD, f"git -C {H} grep --open-files-in-pager=sh x"),
    (1, CWD, f"git -c core.pager=sh -C {H} log"),
    (1, CWD, f"git --config-env=core.pager=X -C {H} log"),
    (1, CWD, f"git -C {H} grep -iO evil x"),
    # G5: only the HOME .claude is protected; a project's own .claude folder is not
    (0, CWD, f"D={DASH}/.claude/plans/preview; mkdir -p $D && cp /tmp/x/page/* $D/"),
    (1, CWD, f"D={A}; mkdir -p $D && cp ~/plans/x/page/* $D/"),
    (1, CWD, "D=~/.claude/hooks; cp /tmp/x $D/"),
    (1, HOME, "D=.claude/hooks; cp /tmp/x $D/"),
    (0, CWD, f"git -C {H} diff --stat"),
    (0, CWD, f"git -c color.ui=never log -1"),
    (0, CWD, f"node -e \"console.log(require('fs').readFileSync('{A}/x.js','utf8'))\""),
    (1, CWD, f"python3 -c \"import shutil; shutil.copy('/tmp/x', '{A}/commit-guard.py')\""),
    (1, CWD, f"python3 -c \"import os; os.remove('{A}/commit-guard.py')\""),
    (1, CWD, f"python3 -c \"from pathlib import Path; Path('{A}/x.py').write_text('')\""),
    (1, CWD, f"python3 -c \"p='{A}/x.py'; open(p,'w').write('')\""),
    (1, CWD, f"python3 -c \"import os; os.system('rm {A}/commit-guard.py')\""),
    (1, CWD, f"node -e \"require('fs').rmSync('{A}/x.js')\""),
    (1, CWD, f"python3 -c \"open('{A}/x.py', mode='a').write('')\""),
    # security review: shell glued before the read-only template prefix, and a digit before a bundled -O
    (1, CWD, f"touch$IFS{A}/x;/python3 -c \"print(open('{A}/a').read())\""),
    (1, CWD, f"git -C {H} grep -5O evil x"),
    (0, CWD, f"/usr/bin/python3 -c \"print(open('{A}/a').read())\""),
    # a listed project's own guards are protected; the rest of its .claude folder is not
    (1, CWD, f"echo '' > {DASH}/.claude/hooks/project-guard.py"),
    (1, CWD, f"cp /dev/null {DASH}/.claude/hooks/project-guard.py"),
    (1, CWD, f"echo '{{}}' > {DASH}/.claude/settings.local.json"),
    (1, CWD, f"rm {DASH}/.claude/hooks/project-guard.py"),
    (1, CWD, f"rm -rf {DASH}/.claude"),
    (1, CWD, f"echo x > {DASHLINK}/.claude/hooks/project-guard.py"),
    (1, CWD, f"cp /tmp/x {DASHLINK}/.claude/settings.json"),
    (1, DASH, "echo x > .claude/hooks/project-guard.py"),
    (0, CWD, f"cp /tmp/x {DASH}/.claude/plans/a.md"),
    (0, CWD, f"echo x > {DASH}/.claude/launch.json"),
    (0, CWD, f"rm {DASH}/.claude/plans/a.md"),
    (0, CWD, f"cat {DASH}/.claude/hooks/project-guard.py"),
    # a read-only one-liner with a relative path after cd into ~/.claude is a read; a write there stays denied
    (0, CWD, "cd ~/.claude && python3 -c \"import json; print(json.load(open('settings.json'))['env'])\""),
    (0, f"{HOME}/.claude", "python3 -c \"import json; print(json.load(open('settings.json'))['env'])\""),
    (1, CWD, "cd ~/.claude && python3 -c \"open('settings.json','w').write('')\""),
    (1, CWD, "cd ~/.claude/hooks && python3 -c \"open('commit-guard.py','w').write('')\""),
    (1, CWD, "cd ~/.claude && python3 -c \"print(open('settings.json').read())\" && python3 -c \"open('settings.json','w')\""),
    (1, CWD, "cd ~/.claude && python3 -c \"print(open('settings.json').read())\"; touch settings.json"),
    # security review: removing or moving a parent of a project's hooks names no protected path
    (1, CWD, f"rm -rf {DASH}"),
    (1, CWD, f"rm -rf {TMP}/real"),
    (1, CWD, f"mv {DASH} /tmp/x"),
    (1, CWD, f"cd {TMP} && rm -rf real"),
    (0, CWD, f"rm -rf {DASH}/src"),
    (0, CWD, "rm -rf /tmp/x"),
    # round 3 E: copying a directory named hooks (or a settings file) into a parent of a protected folder
    (1, HOME, "cp -r /tmp/evil/hooks .claude/"),
    (1, CWD, "cp -r /tmp/evil/hooks ~/.claude/"),
    (1, CWD, "rsync -a /tmp/evil/hooks ~/.claude/"),
    (1, CWD, f"cp -r /tmp/evil/hooks {DASH}/.claude/"),
    (1, CWD, f"rsync -a /tmp/evil/hooks {DASH}/.claude/"),
    (1, CWD, "mv /tmp/evil/hooks ~/.claude/"),
    (1, CWD, "ditto /tmp/evil/hooks ~/.claude/"),
    (1, CWD, "cp /tmp/evil/settings.json ~/.claude/"),
    (1, CWD, "rsync -a /tmp/evil/ ~/.claude/"),
    (1, CWD, "cp -r /tmp/evil/. ~/.claude/"),
    (1, CWD, "cp -rT /tmp/evil ~/.claude"),
    (1, CWD, "cp --no-target-directory -r /tmp/evil ~/.claude"),
    (1, CWD, "ditto /tmp/evil ~/.claude"),
    (1, CWD, "cp -r /tmp/e/* ~/.claude/"),
    (1, CWD, f"rsync -a /tmp/evil/ {DASH}/.claude/"),
    (0, CWD, "rsync -a /tmp/x/ ~/plans/y/"),
    (0, CWD, "cp -r /tmp/e/* /tmp/proj/"),
    (0, CWD, "cp -r /tmp/a/hooks /tmp/proj/"),
    (0, CWD, "cp -r /tmp/a/skills ~/.claude/"),
    # round 3 F: code run from inside a guard folder, or a split .claude name
    (1, CWD, "cd ~/.claude && python3 -c \"import os;os.remove('set'+'tings.json')\""),
    (1, CWD, "python3 -c \"import os;os.remove(os.path.expanduser('~/.cla')+'ude/settings.json')\""),
    (1, f"{HOME}/.claude", "python3 -c \"import os;os.remove('set'+'tings.json')\""),
    (1, DASH + "/.claude", "node -e \"require('fs').unlinkSync('set'+'tings.json')\""),
    (0, CWD, "cd ~/.claude && python3 -c \"import json; print(json.load(open('settings.json'))['env'])\""),
    (0, CWD, "cd ~/.claude && python3 -c \"print(1+1)\""),
    (0, CWD, "python3 -c \"import os;os.remove('/tmp/x')\""),
    # coordinator: git is judged only when aimed at the hooks repo, so ordinary git in a protected project is no decision
    (0, DASH, "git checkout $BRANCH"),
    (0, DASH, "git rm src/a.ts"),
    (0, DASH, "git mv a b"),
    (1, CWD, "git -C ~/.claude/hooks reset --hard"),
    # --work-tree and --git-dir may name a PARENT of a guard folder
    (1, CWD, "git --work-tree=~/.claude checkout x -- hooks"),
    (1, CWD, f"git --work-tree={DASH} checkout x -- .claude"),
    (1, CWD, "git --git-dir ~/.claude/hooks/.git reset --hard"),
    (0, CWD, "git --work-tree=/tmp/wt status"),
    (0, CWD, "git --work-tree=~/.claude status"),
    # whole-folder or .claude/hooks-named recursive copy into any parent of a guard folder
    (1, CWD, "cp -r /tmp/evil/. ~/"),
    (1, CWD, f"rsync -a /tmp/evil/ {TMP}/real/"),
    (1, CWD, f"rsync -a /tmp/evil/ {DASH}/"),
    (0, CWD, "cp -r /tmp/p/.claude ~/Documents/"),  # lands in ~/Documents/.claude, not a guard folder
    (0, CWD, "cp -r /tmp/p/hooks ~/"),  # lands in ~/hooks; the generated parent rows in tamper-ancestors-cases.py cover the real paths
    (1, CWD, f"cp -r /tmp/p/real {TMP}/"),  # lands on ~/Documents, a parent of a project's hooks
    (1, CWD, f"ditto /tmp/p {TMP}/real"),
    (0, CWD, "cp -r src/ /tmp/out/"),
    (0, CWD, "cp -r /tmp/p/docs ~/Documents/"),
]


def run(cwd, cmd):
    # A hook that times out or exits non-zero is a failed row, not "no decision".
    try:
        p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": cmd}, "cwd": cwd}), capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    return "deny" in p.stdout if p.returncode == 0 else None


bad = 0
for want, cwd, cmd in CASES:
    if run(cwd, cmd) != bool(want):
        bad += 1
        print(f"FAIL want={'deny' if want else 'allow'} cwd={cwd[-12:]} cmd={cmd[:90]!r}")
p = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
if p.stdout or p.returncode:
    bad += 1
    print("FAIL crash row: garbage payload")
# F16: when commit-guard.py cannot be imported, a command that names a protected place is denied, a harmless one is allowed.
import shutil
import tempfile
d = tempfile.mkdtemp(prefix="tamper-noimport-")
shutil.copy(HOOK, os.path.join(d, "tamper-guard.py"))  # no commit-guard.py next to it
for want, cmd in ((1, f"cat {H}/commit-guard.py"), (0, "ls /tmp")):
    p = subprocess.run([sys.executable, os.path.join(d, "tamper-guard.py")], input=json.dumps({"tool_input": {"command": cmd}, "cwd": CWD}), capture_output=True, text=True)
    if ("deny" in p.stdout) != bool(want):
        bad += 1
        print(f"FAIL import-failure row want={want} cmd={cmd!r}")
shutil.rmtree(d, ignore_errors=True)
# F7: a crash inside scan() is a deny for a command that names a protected place (NO fail-open).
p = subprocess.run([sys.executable, "-c", "import runpy,sys\nns=runpy.run_path(sys.argv[1], run_name='tg')\nns['scan']=lambda *a, **k: 1/0\n"
                    "import io,json\nsys.stdin=io.StringIO(sys.argv[2])\nns['main'].__globals__['scan']=ns['scan']\nns['main']()", HOOK,
                    json.dumps({"tool_input": {"command": f"rm {H}/a.py"}, "cwd": CWD})], capture_output=True, text=True)
if "deny" not in p.stdout:
    bad += 1
    print("FAIL crash-in-scan row (a protected command must be denied)", p.stderr[-200:])
p = subprocess.run([sys.executable, "-c", "import runpy,sys\nns=runpy.run_path(sys.argv[1], run_name='tg')\nns['main'].__globals__['scan']=lambda *a, **k: 1/0\n"
                    "import io\nsys.stdin=io.StringIO(sys.argv[2])\nns['main']()", HOOK,
                    json.dumps({"tool_input": {"command": "ls $X [a]"}, "cwd": CWD})], capture_output=True, text=True)
if "deny" in p.stdout:
    bad += 1
    print("FAIL crash-in-scan row (a harmless command must not be denied)")
# the find deny names the protected place and says how to narrow the find
p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": "find . -name '*.orig' -delete"}, "cwd": DASH}), capture_output=True, text=True)
if "Narrow the find root" not in p.stdout or ".claude/hooks" not in p.stdout or "-not -path '*/.claude/*'" not in p.stdout:
    bad += 1
    print("FAIL find deny message must name the protected path and the rewrite:", p.stdout[:200])
# the generic deny tells the agent how to read a guard file
p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": f"rm {H}/commit-guard.py"}, "cwd": CWD}), capture_output=True, text=True)
if "use cat, jq or the Read tool" not in p.stdout or "json.load template" not in p.stdout:
    bad += 1
    print("FAIL generic deny message must say how to read a guard file:", p.stdout[:200])
# The quick exit stays fast on a harmless command.
import time
t0 = time.perf_counter()
for _ in range(5):
    subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": "ls /tmp"}, "cwd": CWD}), capture_output=True, text=True)
per = (time.perf_counter() - t0) / 5
if per > 0.05:
    bad += 1
    print(f"FAIL harmless command took {per * 1000:.0f} ms (limit 50)")
import shutil as _sh
_sh.rmtree(TMP, ignore_errors=True)
print(f"{len(CASES) + 7} rows, {bad} failed")
sys.exit(1 if bad else 0)
