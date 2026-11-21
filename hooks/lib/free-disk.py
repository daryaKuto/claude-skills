#!/usr/bin/env python3
"""Free disk space safely before heavy runs .

Two kinds of space, both rebuilt by a tool on its next run:
1. Tool caches, cleared by each tool's OWN cleaner: uv cache prune, npm cache verify, brew cleanup, and Docker dangling
   images and build cache. Never Docker containers or volumes: another session's tests may own them.
2. node_modules of idle repos under ~/Projects (or config.json free_disk_roots). A folder goes only when ALL hold:
   - the repo has a lockfile (package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lockb), so `npm ci` (or the same for
     yarn, pnpm, bun) rebuilds it exactly;
   - nothing in the repo (outside node_modules) and no git HEAD or index changed for IDLE_DAYS (7) days;
   - no running process has its working directory or an open file inside the repo (an editor, dev server or test run);
   - the repo is not under config.json lane_dirs (worktree folders) or the heavy-lock folder, and is not listed in protected_extra_dirs.
It never touches project files, the Trash, app caches in ~/Library/Caches, or worktrees.

  python3 ~/.claude/hooks/lib/free-disk.py          # dry run: what would go, with sizes, and free space now
  python3 ~/.claude/hooks/lib/free-disk.py --yes --caches-only   # the agent form: tool caches only, never node_modules
  python3 ~/.claude/hooks/lib/free-disk.py --yes    # also removes idle node_modules: the user's call, show them the dry run first
(In an agent shell, CLAUDECODE=1, a bare --yes exits 2.) A process counts as using a repo when its cwd or any open file is inside it; if lsof fails,
no node_modules is removed. Docker image and builder prunes are skipped while any container runs.

FREE_DISK_ROOTS (colon list), FREE_DISK_NO_TOOLS=1, FREE_DISK_LSOF (the lsof program; tests point it at /usr/bin/false) and HOOKS_STATE are for tests."""
import json
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
try:  # ../config.json is read once; a missing or broken file means the defaults
    with open(os.environ.get("CLAUDE_HOOKS_CONFIG") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")) as _f:
        CFG = json.load(_f)
except Exception:
    CFG = {}
ROOTS = (os.environ.get("FREE_DISK_ROOTS") or ":".join(os.path.expanduser(r) for r in CFG.get("free_disk_roots", [])) or f"{HOME}/Projects").split(":")
KEEP = [os.path.expanduser(k) for k in CFG.get("lane_dirs", []) + CFG.get("protected_extra_dirs", [])] + [f"{HOME}/.claude/hooks/state/locks"]
LOCKS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")
IDLE_DAYS = 7
STATE = os.environ.get("HOOKS_STATE") or f"{HOME}/.claude/hooks/state"


def free_gb():
    return shutil.disk_usage("/").free // 2**30


def size_mb(path):
    out = subprocess.run(["du", "-sk", path], capture_output=True, text=True).stdout.split()
    return int(out[0]) // 1024 if out else 0


def busy_dirs():
    """Every path a running process has open or as its working directory (plain `lsof -nP -Fn`, about 0.3 s; `lsof +D <repo>` took
    46 s on a large source tree). None when lsof fails or prints nothing: then nobody may be judged idle."""
    try:
        p = subprocess.run([os.environ.get("FREE_DISK_LSOF") or "lsof", "-nP", "-Fn"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode or not p.stdout.strip():
        return None
    return [os.path.realpath(l[1:]) for l in p.stdout.splitlines() if l.startswith("n/")]


def newest_change(repo):
    """Newest mtime in the repo outside node_modules and .git objects, plus git HEAD and index."""
    newest = 0
    for p in (".git/HEAD", ".git/index"):
        if os.path.exists(os.path.join(repo, p)):
            newest = max(newest, os.path.getmtime(os.path.join(repo, p)))
    for d, dirs, files in os.walk(repo):
        dirs[:] = [x for x in dirs if x not in ("node_modules", ".git")]
        for f in files:
            try:
                newest = max(newest, os.lstat(os.path.join(d, f)).st_mtime)
            except OSError:
                pass
    return newest


def candidates():
    busy = busy_dirs()
    if busy is None:
        print("free-disk: lsof failed, so no node_modules is removed (cannot tell which repos are in use)", file=sys.stderr)
    found = []
    for root in ROOTS:
        for d, dirs, _ in os.walk(root):
            if "node_modules" in dirs:
                repo = os.path.realpath(d)
                dirs.remove("node_modules")
                why = None
                if any(repo == k or repo.startswith(k + "/") or k.startswith(repo + "/") for k in map(os.path.realpath, KEEP)):
                    why = "worktree folder or a protected project"
                elif not any(os.path.exists(os.path.join(repo, l)) for l in LOCKS):
                    why = "no lockfile, could not be rebuilt exactly"
                elif busy is None:
                    why = "lsof failed, cannot tell whether a process uses it"
                elif any(b == repo or b.startswith(repo + "/") for b in busy):
                    why = "a running process works inside it or has a file open there"
                elif time.time() - newest_change(repo) < IDLE_DAYS * 86400:
                    why = f"changed in the last {IDLE_DAYS} days"
                found.append((repo, why))
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "dist", "build")]
            if d.count("/") - root.count("/") >= 4:
                dirs[:] = []
    return found


def tool_steps():
    if os.environ.get("FREE_DISK_NO_TOOLS"):
        return []
    steps = [s for s in (["uv", "cache", "prune"], ["npm", "cache", "verify"], ["brew", "cleanup", "--prune=7"]) if shutil.which(s[0])]
    if shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0:
        # Both prunes can drop what a running container's build is using: skip them while any container runs.
        if not subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout.strip():
            steps += [["docker", "image", "prune", "-f"], ["docker", "builder", "prune", "-f"]]
    return steps


def main():
    args = sorted(sys.argv[1:])
    if args not in ([], ["--yes"], ["--dry-run"], ["--caches-only", "--yes"]):
        print("usage: free-disk.py [--yes [--caches-only]]", file=sys.stderr)
        return 2
    yes = "--yes" in args
    # Enforced here because a regex on the command text missed quoted flags, the .sh wrapper and comments. Claude Code sets CLAUDECODE=1 in agent shells.
    if yes and "--caches-only" not in args and os.environ.get("CLAUDECODE") == "1":
        print("agents run --yes --caches-only; removing idle node_modules is the user's call: show the dry run (free-disk.py with no flag)", file=sys.stderr)
        return 2
    before = free_gb()
    steps, cands = tool_steps(), ([] if "--caches-only" in sys.argv else candidates())
    go = [r for r, why in cands if why is None]
    if not yes:
        print(f"free now: {before} GB. --yes would run:")
        for s in steps:
            print("  " + " ".join(s))
        for r, why in cands:
            print(f"  {'remove' if why is None else 'keep  '} {r}/node_modules ({size_mb(r + '/node_modules')} MB){'' if why is None else ': ' + why}")
        return 0
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "free-disk.log"), "a") as log:
        for s in steps:
            p = subprocess.run(s, capture_output=True, text=True)
            log.write(f"{time.strftime('%F %T')} {' '.join(s)}: rc={p.returncode} {(p.stdout or p.stderr).strip()[-120:]}\n")
        for r in go:
            mb = size_mb(r + "/node_modules")
            shutil.rmtree(r + "/node_modules", ignore_errors=True)
            log.write(f"{time.strftime('%F %T')} removed {r}/node_modules ({mb} MB); rebuild with npm ci\n")
        after = free_gb()
        log.write(f"{time.strftime('%F %T')} free {before} -> {after} GB\n")
    print(f"free-disk: {before} GB -> {after} GB free; {len(steps)} cache cleaners, {len(go)} idle node_modules removed (rebuild with npm ci)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
