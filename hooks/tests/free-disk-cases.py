#!/usr/bin/env python3
"""Cases for lib/free-disk.py on a real temp tree (no stand-ins): an idle repo with a lockfile loses node_modules; a repo
with no lockfile, a recently changed repo and a repo a running process works in all keep theirs. Exit 0 only if all pass."""
import os
import shutil
import subprocess
import sys
import tempfile
import time

TOOL = os.environ.get("FREE_DISK_TOOL") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib/free-disk.py")
root = tempfile.mkdtemp(prefix="free-disk-cases-")
old = time.time() - 30 * 86400


def repo(name, lock=True, idle=True):
    r = os.path.join(root, name)
    os.makedirs(os.path.join(r, "node_modules", "pkg"))
    open(os.path.join(r, "node_modules", "pkg", "index.js"), "w").write("x" * 1000)
    open(os.path.join(r, "package.json"), "w").write("{}")
    if lock:
        open(os.path.join(r, "package-lock.json"), "w").write("{}")
    if idle:
        for f in os.listdir(r):
            if f != "node_modules":
                os.utime(os.path.join(r, f), (old, old))
    return r


a, b, c, d = repo("idle"), repo("nolock", lock=False), repo("recent", idle=False), repo("busy")
proc = subprocess.Popen(["sleep", "60"], cwd=d)  # a real process working inside repo d
e = repo("openfile")  # loop 4, E2: a process whose cwd is elsewhere but holds a file open inside the repo
fh = open(os.path.join(e, "package.json"))  # this test process itself holds the file open and its cwd is not in the repo
env = {**{k: v for k, v in os.environ.items() if k != "CLAUDECODE"}, "FREE_DISK_ROOTS": root, "FREE_DISK_NO_TOOLS": "1", "HOOKS_STATE": os.path.join(root, "state")}
fails = 0
try:
    dry = subprocess.run([sys.executable, TOOL], capture_output=True, text=True, env=env, timeout=60).stdout
    want = {a: "remove", b: "no lockfile", c: "changed in the last", d: "running process", e: "open"}
    for r, w in want.items():
        line = next((l for l in dry.splitlines() if f"{os.path.realpath(r)}/node_modules" in l), "")
        if w not in line:
            fails += 1
            print(f"FAIL dry run for {os.path.basename(r)}: want {w!r}, got {line!r}")
    if not all(os.path.isdir(os.path.join(r, "node_modules")) for r in (a, b, c, d, e)):
        fails += 1
        print("FAIL the dry run deleted something")
    subprocess.run([sys.executable, TOOL, "--yes"], capture_output=True, text=True, env=env, timeout=60)
    for r, gone in ((a, True), (b, False), (c, False), (d, False), (e, False)):
        if os.path.isdir(os.path.join(r, "node_modules")) == gone:
            fails += 1
            print(f"FAIL --yes: {os.path.basename(r)} node_modules {'still there' if gone else 'removed'}")
        if not os.path.isfile(os.path.join(r, "package.json")):
            fails += 1
            print(f"FAIL --yes removed a project file in {os.path.basename(r)}")
    # E1: with lsof failing (a real program that exits 1) nothing is removed and the tool says so
    shutil.rmtree(a, ignore_errors=True)
    f = repo("lsofdown2")
    r = subprocess.run([sys.executable, TOOL, "--yes", "--caches-only"], capture_output=True, text=True, env={**env, "FREE_DISK_LSOF": "/usr/bin/false"}, timeout=60)
    r2 = subprocess.run([sys.executable, TOOL, "--yes"], capture_output=True, text=True, env={**env, "FREE_DISK_LSOF": "/usr/bin/false"}, timeout=60)
    if not os.path.isdir(os.path.join(f, "node_modules")) or "lsof failed" not in r2.stderr:
        fails += 1
        print("FAIL lsof failing must keep node_modules and say so:", r2.stderr[:120])
    # loop 3, A: in an agent shell (CLAUDECODE=1) a bare --yes is refused by the tool itself, however the command was spelled
    g = repo("agentguard")
    aenv = {**env, "CLAUDECODE": "1"}
    for args in (["--yes"], ["--yes", "--dry-run"]):
        r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=aenv, timeout=60)
        if args == ["--yes"] and (r.returncode != 2 or "--caches-only" not in r.stderr or not os.path.isdir(os.path.join(g, "node_modules"))):
            fails += 1
            print("FAIL agent shell: a bare --yes must exit 2 and keep node_modules:", r.returncode, r.stderr[:100])
    for args in (["--yes", "--caches-only"], ["--caches-only", "--yes"]):
        r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=aenv, timeout=60)
        if r.returncode != 0 or not os.path.isdir(os.path.join(g, "node_modules")):
            fails += 1
            print(f"FAIL agent shell: {' '.join(args)} must run and keep node_modules:", r.returncode, r.stderr[:100])
    r = subprocess.run(["bash", os.path.join(os.path.dirname(TOOL), "free-disk.sh"), "--yes"], capture_output=True, text=True, env=aenv, timeout=60)
    if r.returncode != 2:
        fails += 1
        print("FAIL the .sh wrapper must refuse a bare --yes in an agent shell, got", r.returncode)
    bad = subprocess.run([sys.executable, TOOL, "--force"], capture_output=True, text=True, env=env).returncode
    if bad != 2:
        fails += 1
        print(f"FAIL an unknown option must exit 2, got {bad}")
finally:
    fh.close()
    proc.terminate()
    proc.wait()
    shutil.rmtree(root, ignore_errors=True)
print(f"free-disk: {fails} failed")
sys.exit(1 if fails else 0)
