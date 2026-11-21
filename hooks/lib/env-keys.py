#!/usr/bin/env python3
"""Print only the variable NAMES an env file defines, never their values: python3 ~/.claude/hooks/lib/env-keys.py .env [...]

Why: agents may not read .env files (secret guard, Read denies), but sometimes need to know which variables exist, for
example when .env.example is out of date. stash-secret-guard allows exactly this path; a copy
anywhere else is refused, and the tamper guard stops agents rewriting this file. Prints NAME lines only; a line that is
not `NAME=...` (or `export NAME=...`) prints nothing, so a value can never leak, even from a file that is not an env file."""
import re, sys

NAME = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
for path in sys.argv[1:] or [".env"]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            names = [m.group(1) for line in f if (m := NAME.match(line))]
    except OSError as e:
        print(f"{path}: cannot read ({e.strerror})")
        continue
    print(f"{path}: {len(names)} variables")
    for n in names:
        print(f"  {n}")
