#!/usr/bin/env python3
"""Read-only checks on ../settings.example.json (override the path with SETTINGS=<file>, for example ~/.claude/settings.json, to test your real file).
Guards only work if they are registered and their files exist; nothing else tests that. Exit 0 only if all pass."""
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
PATH = os.path.expanduser(os.environ.get("SETTINGS") or os.path.join(HOOKS_DIR, "settings.example.json"))
s = json.load(open(PATH))
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def entries(event):
    for block in s.get("hooks", {}).get(event, []):
        for h in block.get("hooks", []):
            yield block.get("matcher", ""), h


# 1. every hook command points at a file that exists
for event in s.get("hooks", {}):
    for _, h in entries(event):
        for tok in shlex.split(h["command"])[1:]:
            tok = tok.replace("~/.claude/hooks/", HOOKS_DIR + "/")  # the example names the install folder; check the files next to this suite
            tok = os.path.expanduser(tok)
            if tok.startswith("/"):
                check(os.path.exists(tok), f"{event} hook file exists: {tok}")
                break


def find(event, script):
    return [(m, h) for m, h in entries(event) if script in h["command"]]


# 2. the two Bash guards: PreToolUse, Bash matcher, fail closed, with a timeout
for script in ("policy-guard.py", "kill-guard.py"):
    hits = [h for m, h in find("PreToolUse", script) if "Bash" in m.split("|")]
    check(bool(hits), f"{script} registered on PreToolUse for Bash")
    for h in hits:
        check(h.get("onFailure") == "block", f"{script} has onFailure=block")
        check(isinstance(h.get("timeout"), (int, float)) and h["timeout"] > 0, f"{script} has a timeout")

# 3. shed-load on PostToolUse covering Bash, Agent and Workflow
hits = find("PostToolUse", "shed-load.py")
check(bool(hits), "shed-load.py registered on PostToolUse")
for tool in ("Bash", "Agent", "Workflow"):
    check(any(tool in m.split("|") for m, _ in hits), f"shed-load.py matcher covers {tool}")

# 4. env
check(s.get("env", {}).get("BASH_DEFAULT_TIMEOUT_MS") == "60000", 'env BASH_DEFAULT_TIMEOUT_MS is "60000"')

# 5. deny rules
deny = set(s.get("permissions", {}).get("deny", []))
REQUIRED = [
    "Bash(git stash*)", "Bash(printenv*)", "Bash(env)", "Bash(git -c *)", "Bash(git --config-env*)",
    "Read(**/.env)", "Read(**/.env.local)", "Read(~/.aws/credentials)", "Read(**/*.pem)", "Read(**/*.key)",
    "Read(~/.netrc)", "Read(**/id_rsa)", "Read(**/id_ed25519)", "Read(**/id_ecdsa)",
    # every secret file name the Read tool must refuse (exact names, so the tracked .env.local.example stays readable)
    "Read(**/.env.*.local)", "Read(**/.env.production)", "Read(**/.env.staging)", "Read(**/.env.local.backup)",
    "Read(**/.env.local.prod)", "Read(**/.env.prod)", "Read(**/.env.preprod)", "Read(**/.env.development)", "Read(**/.env.dev)",
    "Read(**/.env.test)", "Read(**/.env.qa)", "Read(**/.env.stage)", "Read(**/.env.live)", "Read(**/.env.ci)", "Read(**/.envrc)",
    "Read(**/*.p12)", "Read(~/.git-credentials)", "Read(~/.npmrc)", "Read(~/.pypirc)", "Read(~/.aws/sso/cache/**)",
    "Read(~/.config/gh/hosts.yml)", "Read(~/.docker/config.json)",
]
for rule in REQUIRED:
    check(rule in deny, f"deny rule present: {rule}")

# The tracked example file must stay readable: no Read deny glob may match it (the globs are gitignore-style, `**/` = any folder).
import fnmatch
for example in (".env.local.example", ".env.example", ".env.sample"):
    hit = [r for r in deny if r.startswith("Read(**/") and fnmatch.fnmatchcase(example, r[len("Read(**/"):-1])]
    check(not hit, f"no Read deny matches {example}" + (f" (matched by {hit})" if hit else ""))

# 6. every bypass-corpus row that says a settings deny rule covers it must name a rule that exists
rows = json.load(open(os.path.join(HERE, "bypass-corpus.json")))
for r in rows:
    m = re.search(r"settings deny (.+)$", r.get("covered_by", ""))
    if m:
        check(m.group(1).strip() in deny, f"corpus covered_by rule exists in deny: {m.group(1).strip()} ({r['command']})")

print(f"{sum(1 for _ in fails)} failed" if fails else "all passed")
if fails:
    print("MISSING: " + "; ".join(fails))
sys.exit(1 if fails else 0)
