#!/usr/bin/env python3
"""Cases for vscode-guard.sh (PostToolUse on Bash). Each case runs the real hook with cwd = a fresh temp dir
that already holds the "cloned" repo with a .vscode/ folder (no network). Exit 0 only if all pass.
Security rows: a $(...) or backtick inside the clone line must never run (the old `eval` ran it a second time)."""
import json
import os
import re
import subprocess
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vscode-guard.sh")
CFG = os.path.join(tempfile.mkdtemp(), "config.json")
json.dump({"trusted_github_owners": ["trusted-user", "Trusted-Org"]}, open(CFG, "w"))


def git(*a, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True)


def make_repo(path, kind, url):
    """kind: clone = a real local clone made just now; old = a repo made by init+commit (no clone reflog entry);
    nogit = a plain folder. The repo gets a .vscode and origin = the URL the command names."""
    if kind == "nogit":
        os.makedirs(os.path.join(path, ".vscode"))
        return
    src = tempfile.mkdtemp()
    git("init", "-q", cwd=src)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=src)
    if kind in ("clone", "clone-old"):
        git("clone", "-q", src, path, cwd=src)
    elif kind in ("noreflog", "noreflog-old"):
        git("clone", "-q", "-c", "core.logAllRefUpdates=false", src, path, cwd=src)
    else:
        os.makedirs(path)
        git("init", "-q", cwd=path)
        git("commit", "-q", "--allow-empty", "-m", "i", cwd=path)
    git("remote", "remove", "origin", cwd=path) if kind != "old" else None
    git("remote", "add", "origin", url, cwd=path)
    os.makedirs(os.path.join(path, ".vscode"))
    if kind == "clone-old":  # the clone happened 10 minutes ago
        rl = os.path.join(path, ".git", "logs", "HEAD")
        old = str(int(time.time()) - 600)
        with open(rl) as f:
            txt = re.sub(r"> \d+ ", "> " + old + " ", f.read())
        with open(rl, "w") as f:
            f.write(txt)
    if kind == "noreflog-old":  # no reflog; .git created 10 minutes ago (macOS lowers the birth time to an older mtime)
        os.utime(os.path.join(path, ".git"), (time.time() - 600, time.time() - 600))


def run(cmd, repo_dir, resp="ok", kind="clone"):
    """Returns (probe_created, vscode_still_there, srcdir_vscode_still_there) for one hook run. resp: what git printed
    (ok = a clean clone, a string = that stderr, None = no tool_response in the payload)."""
    work = tempfile.mkdtemp()
    m = re.search(r"https://github\.com/\S+|git@github\.com:\S+", cmd)
    url = m.group(0) if m else "https://github.com/someone/evilrepo"
    make_repo(os.path.join(work, repo_dir), kind, url)
    make_repo(os.path.join(work, "srcdir"), "clone", "https://github.com/someone/srcdir")  # a sibling a misparse would hit
    probe = os.path.join(work, "PROBE")
    cmd = cmd.replace("<PROBE>", probe)
    payload = {"tool_input": {"command": cmd}}
    if resp is not None:
        payload["tool_response"] = {"stdout": "", "stderr": f"Cloning into '{repo_dir}'...\n" if resp == "ok" else resp}
    subprocess.run(["bash", HOOK], input=json.dumps(payload),
                   capture_output=True, text=True, timeout=30, cwd=work, env={**os.environ, "CLAUDE_HOOKS_CONFIG": CFG})
    return (os.path.exists(probe), os.path.isdir(os.path.join(work, repo_dir, ".vscode")),
            os.path.isdir(os.path.join(work, "srcdir", ".vscode")))


# (name, command, repo dir name, probe must exist, .vscode must survive)
CASES = [
    ("command substitution is not run", 'git clone https://github.com/someone/evilrepo $(touch <PROBE>)', "evilrepo", False, True),
    ("backtick is not run", 'git clone https://github.com/someone/evilrepo `touch <PROBE>`', "evilrepo", False, True),
    ("plain clone of a stranger's repo removes .vscode", 'git clone --depth 1 "https://github.com/someone/evilrepo"', "evilrepo", False, False),
    ("explicit target dir removes .vscode", "git clone https://github.com/someone/evilrepo mycopy", "mycopy", False, False),
    ("trusted user repo keeps .vscode", "git clone https://github.com/trusted-user/app", "app", False, True),
    ("Trusted-User (case-insensitive) keeps .vscode", "git clone https://github.com/Trusted-User/app", "app", False, True),
    # Quotes are stripped, then the line is split on spaces, so the target "my copy" reads as "my": no such dir, the
    # hook skips. It does not clean that clone, but it also never touches anything else.
    ("quoted target with a space is skipped safely", 'git clone https://github.com/someone/evilrepo "my copy"', "my copy", False, True),
    ("not a clone is ignored", "git status", "evilrepo", False, True),
    # a trusted owner is exempt; a failed clone or an unknown outcome never deletes from an existing folder
    ("trusted org repo keeps .vscode", "git clone https://github.com/trusted-org/web-app", "web-app", False, True),
    ("Trusted-Org over ssh keeps .vscode", "git clone git@github.com:Trusted-Org/device-app.git", "device-app", False, True),
    ("failed clone into an existing folder keeps .vscode", "git clone https://github.com/someone/evilrepo", "evilrepo", False, True, "fatal: destination path 'evilrepo' already exists and is not an empty directory.\n"),
    ("clone that printed Cloning then fatal keeps .vscode", "git clone https://github.com/someone/evilrepo", "evilrepo", False, True, "Cloning into 'evilrepo'...\nfatal: repository not found\n"),
    ("no tool_response in the payload does nothing", "git clone https://github.com/someone/evilrepo", "evilrepo", False, True, None),
    # round 6: a quiet clone prints no "Cloning into" line; the folder holding .git is the proof it succeeded
    ("git clone -q removes .vscode", "git clone -q https://github.com/someone/evilrepo", "evilrepo", False, False, ""),
    ("git clone --quiet removes .vscode", "git clone --quiet https://github.com/someone/evilrepo", "evilrepo", False, False, ""),
    ("git clone 2>/dev/null removes .vscode", "git clone https://github.com/someone/evilrepo 2>/dev/null", "evilrepo", False, False, ""),
    ("git clone 2>&1 | tail -1 removes .vscode", "git clone https://github.com/someone/evilrepo 2>&1 | tail -1", "evilrepo", False, False, ""),
    ("quiet clone with an explicit dir and 2> /dev/null", "git clone -q https://github.com/someone/evilrepo mycopy 2> /dev/null", "mycopy", False, False, ""),
    ("quiet clone of a trusted user's repo keeps .vscode", "git clone -q https://github.com/trusted-user/glow", "glow", False, True, ""),
    # round 7: a failed quiet clone into an OLD repo reaches the hook too; only a clone made just now is cleaned
    ("failed quiet clone || true keeps an old repo's .vscode", "git clone -q https://github.com/someone/evilrepo || true", "evilrepo", False, True, "", "old"),
    ("failed clone ; true keeps an old repo's .vscode", "git clone https://github.com/someone/evilrepo 2>/dev/null; true", "evilrepo", False, True, "", "old"),
    ("failed clone 2>/dev/null; echo x keeps an old repo's .vscode", "git clone https://github.com/someone/evilrepo 2>/dev/null; echo x", "evilrepo", False, True, "", "old"),
    ("quiet clone into a folder without .git keeps .vscode", "git clone -q https://github.com/someone/evilrepo", "evilrepo", False, True, "", "nogit"),
    # clustered short flags: the value after -qb / -qj / -qo is not the URL
    ("-qb main: the clone is cleaned, the sibling is not", "git clone -qb main https://github.com/someone/evilrepo fresh", "fresh", False, False, "", "clone", True),
    ("-qj 2: the clone is cleaned, the sibling is not", "git clone -qj 2 https://github.com/someone/evilrepo fresh", "fresh", False, False, "", "clone", True),
    ("-qj4 glued number is still quiet", "git clone -qj4 https://github.com/someone/evilrepo fresh", "fresh", False, False, "", "clone", True),
    ("-qo up: the clone is cleaned, the sibling is not", "git clone -qo up https://github.com/someone/evilrepo fresh", "fresh", False, False, "", "clone", True),
    ("-qb main with a local source dir leaves the source alone", "git clone -qb main srcdir fresh", "fresh", False, False, "", "clone", True),
    # round 8: every clustered short flag ends in a value letter, not only the ones with q
    ("-vb main: the clone is cleaned, the sibling is not", "git clone -vb main https://github.com/someone/evilrepo fresh", "fresh", False, False, "ok", "clone", True),
    ("-lb main: the clone is cleaned, the sibling is not", "git clone -lb main https://github.com/someone/evilrepo fresh", "fresh", False, False, "ok", "clone", True),
    ("-sb main: the clone is cleaned, the sibling is not", "git clone -sb main https://github.com/someone/evilrepo fresh", "fresh", False, False, "ok", "clone", True),
    # a quiet clone with no reflog (core.logAllRefUpdates=false) is proven by the age of .git
    ("quiet clone without a reflog removes .vscode", "git clone -q -c core.logAllRefUpdates=false https://github.com/someone/evilrepo", "evilrepo", False, False, "", "noreflog"),
    ("stderr-hidden clone without a reflog removes .vscode", "git clone -c core.logAllRefUpdates=false https://github.com/someone/evilrepo 2>/dev/null", "evilrepo", False, False, "", "noreflog"),
    ("failed quiet re-clone into an old folder without a reflog keeps .vscode", "git clone -q -c core.logAllRefUpdates=false https://github.com/someone/evilrepo || true", "evilrepo", False, True, "", "noreflog-old"),
    ("quiet clone whose reflog is 10 minutes old keeps .vscode", "git clone -q https://github.com/someone/evilrepo || true", "evilrepo", False, True, "", "clone-old"),
    # trailing slash on the target; bare `2> /dev/null` with no explicit dir
    ("target with a trailing slash is cleaned", "git clone https://github.com/someone/evilrepo evilrepo/", "evilrepo", False, False),
    ("bare 2> /dev/null with no explicit dir is cleaned", "git clone https://github.com/someone/evilrepo 2> /dev/null", "evilrepo", False, False, ""),
    # a stderr redirect after && belongs to another command: this is a normal (non-quiet) clone
    ("2>/dev/null after && is not the clone's", "git clone https://github.com/someone/evilrepo fresh && echo x 2>/dev/null", "fresh", False, True, "fatal: destination path 'fresh' already exists\n"),
]

bad = 0
for name, cmd, repo, want_probe, want_vscode, *r in CASES:
    want_src = r[2] if len(r) > 2 else True  # r = [resp, kind, sibling .vscode must survive]
    probe, vscode, src = run(cmd, repo, *r[:2])
    ok = probe == want_probe and vscode == want_vscode and src == want_src
    bad += not ok
    print("PASS" if ok else "FAIL", name, "" if ok else f"(probe={probe}, vscode_kept={vscode})")
print(f"{len(CASES) - bad} passed, {bad} failed")
raise SystemExit(1 if bad else 0)
