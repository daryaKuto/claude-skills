#!/usr/bin/env python3
"""Fails with file:line for every hit of a project-specific word in the guard hooks and their docs.

The hooks are generic: project details come from hooks/config.json, so no repo name, product name, account number, branch
name, date of an incident or home path may appear in any file here. Add a word to TERMS when a new private detail could leak.
Words are written as fragments so that this file does not contain them itself.

Scope: every text file under hooks/ and docs/, plus the lines this branch adds to README.md and CLAUDE.md (read from
`git diff` against origin/main, skipped when git cannot answer). Older files such as skills/ are not scanned.
Run on its own: python3 hooks/tests/no-private-terms-cases.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.dirname(HERE)
ROOT = os.path.dirname(HOOKS) if os.path.basename(HOOKS) == "hooks" else HOOKS  # an installed copy scans only itself
J = "".join
TERMS = [  # fragments joined at run time, matched case-insensitively
    J(("gl", "ow-dash")), J(("gl", "ow-")), J(("ail", "ith")), J(("dary", "aku")), J(("dar", "ya ku")),
    J(("demo", "-mode")), J(("agents", "/skills")), J(("aws-app", "-move")), J(("plan", "/aws")),
    J(("things", "board")), J(("firm", "ware")), J(("dry", "fire")), J(("auro", "ra")), J(("supa", "base")),
    J(("dash", "board")), J(("no", "sync")), J(("heavy-", "take")), J(("chu", "nk/")), J(("Develop", "ment.")),
    J(("/Us", "ers/")), J(("/ho", "me/da")),
]
REGEXES = [  # (name, pattern)
    ("12-digit account number", r"(?<!\d)\d{12}(?!\d)"),
    ("lane name (letter c plus 2 or 3 digits)", r"\bc\d{2,3}[ab]?\b"),
    ("dated incident (2026-MM-DD)", r"\b2026-\d\d-\d\d\b"),
    ("compact date 2026MMDD", r"\b2026\d{4}\b"),
]
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
term_rx = re.compile("|".join(re.escape(t) for t in TERMS), re.I)
rx = [(n, re.compile(p, re.I)) for n, p in REGEXES]
hits = scanned = 0


def why(line):
    m = term_rx.search(line)
    if m:
        return m.group(0)
    for name, r in rx:
        if r.search(line):
            return name


def report(label, n, w):
    global hits
    hits += 1
    print(f"HIT {label}:{n}: {w}")


scan_dirs = [HOOKS] + ([os.path.join(ROOT, "docs")] if os.path.isdir(os.path.join(ROOT, "docs")) else [])
for top in scan_dirs:
    for d, dirs, files in os.walk(top):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            path = os.path.join(d, f)
            try:
                raw = open(path, "rb").read()
            except OSError:
                continue
            if b"\0" in raw:
                continue
            scanned += 1
            for n, line in enumerate(raw.decode("utf-8", "replace").split("\n"), 1):
                w = why(line)
                if w:
                    report(os.path.relpath(path, ROOT), n, w)

if os.path.isdir(os.path.join(ROOT, ".git")):  # lines added to the two older files that this branch edits
    try:
        diff = subprocess.run(["git", "-C", ROOT, "diff", "-U0", "origin/main", "--", "README.md", "CLAUDE.md"],
                              capture_output=True, text=True, timeout=30).stdout
    except Exception:
        diff = ""
    cur, n = "", 0
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("@@"):
            n = int(re.search(r"\+(\d+)", line).group(1)) - 1
        elif line.startswith("+") and not line.startswith("+++"):
            n += 1
            w = why(line[1:])
            if w:
                report(cur, n, w)
print(f"no-private-terms: {scanned} files scanned, {hits} hits")
sys.exit(1 if hits else 0)
