#!/usr/bin/env python3
"""Cases for lib/env-keys.py: prints exactly the variable names, never any value text. Made-up values only."""
import os
import subprocess
import sys
import tempfile

HOOK = os.environ.get("ENV_KEYS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib/env-keys.py")
NAMES = ["SECRET", "X", "QUOTED", "EQ", "SPACED", "_UNDER", "TAIL"]
VALUES = ["hunter2", "zebra-9931", "quoted-value-777", "a=b=c-4521", "spaced-val-88", "under-val-12", "tail-val-34"]
BODY = """# a comment SECRETCOMMENT=commentvalue-55
SECRET=hunter2

export X=zebra-9931
QUOTED="quoted-value-777"
EQ=a=b=c-4521
  SPACED = spaced-val-88
_UNDER='under-val-12'
not an env line with leaked-text-66
#OLD_KEY=old-value-99
# SPACE_KEY=space-value-98
TAIL=tail-val-34"""

with tempfile.TemporaryDirectory() as d:
    f = os.path.join(d, "fake.env")
    open(f, "w").write(BODY)
    p = subprocess.run([sys.executable, HOOK, f], capture_output=True, text=True, timeout=30)

out = p.stdout + p.stderr
got = [l.strip() for l in p.stdout.splitlines()[1:]]
checks = [
    ("exit 0", p.returncode == 0),
    ("exactly the names, in order", got == NAMES),
    ("count line says 7", "7 variables" in p.stdout.splitlines()[0]),
    ("no value text in stdout or stderr", not any(v in out for v in VALUES + ["commentvalue-55", "leaked-text-66"])),
    ("commented-out name not listed", "SECRETCOMMENT" not in out),
    ("#NAME= and # NAME= lines not listed", "OLD_KEY" not in out and "SPACE_KEY" not in out),
    ("their values do not leak", "old-value-99" not in out and "space-value-98" not in out),
]
bad = 0
for name, ok in checks:
    bad += not ok
    print(("PASS " if ok else "FAIL ") + name)
if bad:
    print("output was:\n" + out)
print(f"{len(checks) - bad} passed, {bad} failed")
sys.exit(1 if bad else 0)
