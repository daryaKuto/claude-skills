"""Memory and disk pressure for the gates (rule pyramid Task 8.1). status() -> {"level": OK|WARN|CRITICAL|UNKNOWN, "line": str}.
Runs lib/mem-check.sh at most every 15 s; the answer is cached in $HOOKS_STATE/mem/cache.json (temp file + os.replace) under a
mkdir lock, and a caller that finds the lock held reads the last cached value. Any failure or a check over 2 s is UNKNOWN, which
every gate treats as OK (fail open). PRESSURE_FAKE=OK|WARN|CRITICAL|UNKNOWN overrides it for tests; MEM_CHECK swaps the script."""
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = ("OK", "WARN", "CRITICAL")
TTL, TIMEOUT = 15, 2


def _dir():
    return os.path.join(os.environ.get("HOOKS_STATE") or os.path.expanduser("~/.claude/hooks/state"), "mem")


def _read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _measure():
    script = os.environ.get("MEM_CHECK") or os.path.join(HERE, "mem-check.sh")
    try:
        p = subprocess.run(["bash", script], capture_output=True, text=True, timeout=TIMEOUT,
                           env={**os.environ, "MEM_STATE_DIR": _dir()})
        line = p.stdout.strip().splitlines()[0] if p.stdout.strip() else ""
        level = line.split(" ", 1)[0]
        return {"level": level if level in LEVELS else "UNKNOWN", "line": line}
    except Exception:
        return {"level": "UNKNOWN", "line": "mem-check failed or timed out"}


def status():
    fake = os.environ.get("PRESSURE_FAKE")
    if fake:
        return {"level": fake, "line": f"{fake} (PRESSURE_FAKE)"}
    try:
        d = _dir()
        os.makedirs(d, exist_ok=True)
        cache, lock = os.path.join(d, "cache.json"), os.path.join(d, "cache.lock")
        c = _read(cache)
        if c and time.time() - c.get("ts", 0) < TTL:
            return {"level": c["level"], "line": c["line"]}
        try:
            os.mkdir(lock)
        except FileExistsError:
            try:  # a lock older than 10 s belongs to a crashed caller
                if time.time() - os.path.getmtime(lock) > 10:
                    os.rmdir(lock)
            except OSError:
                pass
            return {"level": c["level"], "line": c["line"]} if c else {"level": "UNKNOWN", "line": "no cached value yet"}
        try:
            r = _measure()
            tmp = f"{cache}.{os.getpid()}"
            with open(tmp, "w") as f:
                json.dump({**r, "ts": time.time()}, f)
            os.replace(tmp, cache)
            return r
        finally:
            os.rmdir(lock)
    except Exception:
        return {"level": "UNKNOWN", "line": "pressure.status failed"}
