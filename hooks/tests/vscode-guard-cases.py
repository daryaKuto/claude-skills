#!/usr/bin/env python3
"""Cases for vscode-guard.sh (PostToolUse on Bash). Each case runs the real hook with cwd = a fresh temp dir
that already holds the "cloned" repo with a .vscode/ folder (no network). Exit 0 only if all pass.
Security rows: a $(...) or backtick inside the clone line must never run (the old `eval` ran it a second time)."""
import json
import os
import subprocess
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vscode-guard.sh")
CFG = os.path.join(tempfile.mkdtemp(), "config.json")
json.dump({"trusted_github_owners": ["trusted-user", "Trusted-Org"]}, open(CFG, "w"))


def run(cmd, repo_dir, resp="ok"):
    """Returns (probe_created, vscode_still_there) for one hook run. resp: what git printed (ok = a clean clone,
    a string = that stderr, None = no tool_response in the payload)."""
    work = tempfile.mkdtemp()
    os.makedirs(os.path.join(work, repo_dir, ".vscode"))
    probe = os.path.join(work, "PROBE")
    cmd = cmd.replace("<PROBE>", probe)
    payload = {"tool_input": {"command": cmd}}
    if resp is not None:
        payload["tool_response"] = {"stdout": "", "stderr": f"Cloning into '{repo_dir}'...\n" if resp == "ok" else resp}
    subprocess.run(["bash", HOOK], input=json.dumps(payload),
                   capture_output=True, text=True, timeout=30, cwd=work, env={**os.environ, "CLAUDE_HOOKS_CONFIG": CFG})
    return os.path.exists(probe), os.path.isdir(os.path.join(work, repo_dir, ".vscode"))


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
]

bad = 0
for name, cmd, repo, want_probe, want_vscode, *r in CASES:
    probe, vscode = run(cmd, repo, *r)
    ok = probe == want_probe and vscode == want_vscode
    bad += not ok
    print("PASS" if ok else "FAIL", name, "" if ok else f"(probe={probe}, vscode_kept={vscode})")
print(f"{len(CASES) - bad} passed, {bad} failed")
raise SystemExit(1 if bad else 0)
