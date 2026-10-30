#!/usr/bin/env python3
"""Generic live-state snapshot for claim verification in ANY project.

Runs a project-defined list of READ-ONLY commands once, stores each output in a folder,
and writes a manifest, a one-screen SUMMARY.md and (with --prev) a CHANGES.md. Workflow
agents then read the folder instead of each re-running the same queries. One pull, one
independent check, many readers: see ../SKILL.md, "Snapshot once".

Config (default: .claude/verification-sources.json in the project root):
  {
    "summary_lines": 15,
    "redact": ["optional extra regex", "..."],
    "sources": [
      {"name": "git-head", "cmd": ["git", "log", "-1", "--format=%h %cd %s"]},
      {"name": "schema",   "cmd": ["supabase", "db", "query", "--linked", "-o", "json", "select ..."], "format": "json"},
      {"name": "tests",    "cmd": "npm test -- --reporter=dot 2>&1 | tail -20", "shell": true, "timeout": 600}
    ]
  }
  - "cmd" is an argv list (preferred) or, with "shell": true, a shell string.
  - "format": "json" parses stdout as JSON (so jq works and CHANGES.md diffs by path);
    anything else is stored as text. "json_key": "rows" keeps only that key: use it when a
    tool wraps results in per-call noise (the Supabase CLI adds a random "boundary" and a
    warning to every `db query`, which would otherwise show up as a change in every diff).
  - Commands MUST be read-only. The script refuses the obvious write verbs (SQL DDL/DML,
    git push/commit/stash/checkout/reset, rm, curl -X POST/PUT/PATCH/DELETE); that guard is
    a backstop, not a proof. The project owner decides what goes in the config.

Secrets: every output is scanned for JWT, API-key, connection-string and private-key shapes
and redacted before it is written. Do not put commands in the config that print PII (user
emails, IPs); summarise to counts instead.

Usage: python3 snapshot.py [--config FILE] [--out DIR] [--prev DIR] [--only a,b]
Prints the snapshot folder on the last line. Exit 0 = all sources OK, 3 = some failed (the
rest are still written; manifest.json says why). A failed source is never "no data".
"""
import argparse, datetime, hashlib, json, os, re, subprocess, sys, tempfile

SECRET_RE = [r"eyJ[\w-]{15,}\.[\w-]+\.[\w-]+", r"\bsk-[A-Za-z0-9_-]{20,}", r"\bsb_secret_\w+",
             r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://\S+", r"\bAKIA[0-9A-Z]{16}\b",
             r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"]
WRITE_RE = re.compile(
    r"(?i)\b(insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+(table|index|function|schema|view)|alter\s+(table|function|role)"
    r"|truncate\s|create\s+(table|index|function|policy|role|or\s+replace)|grant\s|revoke\s)"
    r"|\bgit\s+(push|commit|stash|checkout|reset|rebase|merge)\b|\brm\s+-|\bcurl\b[^|]*\s-X\s*(POST|PUT|PATCH|DELETE)")

def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def flatten(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flatten(v, f"{p}.{k}" if p else str(k))
    elif isinstance(x, list) and x and all(isinstance(e, dict) for e in x):
        key = next((k for k in ("id", "name", "slug", "key", "table_name", "file", "path", "version") if k in x[0]), None)
        for i, e in enumerate(x):
            yield from flatten(e, f"{p}[{e.get(key, i) if key else i}]")
    else:
        yield p, json.dumps(x, sort_keys=True, default=str)

def diff_source(prev_file, cur_text, is_json):
    old = open(prev_file).read()
    if is_json:
        try:
            a, b = dict(flatten(json.loads(old))), dict(flatten(json.loads(cur_text)))
            return [f"  - {k}: {a.get(k, '(absent)')[:80]} -> {b.get(k, '(absent)')[:80]}"
                    for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        except ValueError:
            pass
    ol, nl = old.splitlines(), cur_text.splitlines()
    return [f"  - removed: {l[:120]}" for l in ol if l not in set(nl)] + [f"  + added: {l[:120]}" for l in nl if l not in set(ol)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=".claude/verification-sources.json")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "verification-state"))
    ap.add_argument("--prev")
    ap.add_argument("--only", help="comma-separated source names to pull")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    redact = [re.compile(r) for r in SECRET_RE + cfg.get("redact", [])]
    def scrub(t):
        for r in redact:
            t = r.sub("[REDACTED]", t)
        return t
    only = set(a.only.split(",")) if a.only else None
    out = os.path.join(a.out, datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(out)
    manifest = {"created_at": now(), "config": os.path.abspath(a.config), "cwd": os.getcwd(), "sources": {}, "verdict": "UNVERIFIED"}
    summary = [f"# Snapshot {now()}", f"Project: {os.getcwd()}. Read this first; open the files for detail.", ""]
    changes = [f"# Changes since {a.prev}", ""] if a.prev else None
    n = cfg.get("summary_lines", 15)
    for src in cfg["sources"]:
        name = src["name"]
        if only and name not in only:
            continue
        cmd, shell = src["cmd"], bool(src.get("shell"))
        text_cmd = cmd if isinstance(cmd, str) else " ".join(cmd)
        started = now()
        is_json = src.get("format") == "json"
        fname = f"{name}.json" if is_json else f"{name}.txt"
        try:
            if WRITE_RE.search(text_cmd):
                raise ValueError("refused: command looks like a write (see WRITE_RE); snapshots are read-only")
            r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=src.get("timeout", 120))
            if r.returncode not in src.get("ok_exit_codes", [0]):
                raise RuntimeError(f"exit {r.returncode}: {r.stderr.strip()[:300]}")
            body = scrub(r.stdout)
            if is_json:
                parsed = json.loads(body)
                if src.get("json_key"):
                    parsed = parsed[src["json_key"]]
                body = json.dumps(parsed, indent=1, default=str)
            open(os.path.join(out, fname), "w").write(body)
            manifest["sources"][name] = {"status": "OK", "file": fname, "pulled_at": started,
                                         "sha256": hashlib.sha256(body.encode()).hexdigest(), "cmd": scrub(text_cmd)}
            lines = body.splitlines()
            summary.append(f"## {name} ({len(lines)} lines{', json' if is_json else ''})")
            summary += lines[:n] + ([f"... {len(lines) - n} more lines in {fname}"] if len(lines) > n else []) + [""]
            if changes is not None:
                pf = os.path.join(a.prev, fname)
                if os.path.exists(pf):
                    ch = diff_source(pf, body, is_json)
                    changes.append(f"- {name}: {len(ch)} changes" + ("" if ch else " (unchanged)"))
                    changes += ch[:60] + ([f"  ... {len(ch) - 60} more"] if len(ch) > 60 else [])
                else:
                    changes.append(f"- {name}: no previous copy")
        except Exception as e:  # recorded, never silently dropped
            manifest["sources"][name] = {"status": "FAILED", "pulled_at": started, "error": scrub(str(e))[:300], "cmd": scrub(text_cmd)}
            summary += [f"## {name}: FAILED ({scrub(str(e))[:200]})", ""]
    open(os.path.join(out, "SUMMARY.md"), "w").write("\n".join(summary) + "\n")
    if changes is not None:
        open(os.path.join(out, "CHANGES.md"), "w").write("\n".join(changes) + "\n")
    open(os.path.join(out, "manifest.json"), "w").write(json.dumps(manifest, indent=1))
    link = os.path.join(a.out, "latest")
    if os.path.islink(link):
        os.remove(link)
    os.symlink(out, link)
    failed = [k for k, v in manifest["sources"].items() if v["status"] != "OK"]
    if failed:
        print(f"FAILED sources: {', '.join(failed)} (see manifest.json)", file=sys.stderr)
    print(out)
    sys.exit(3 if failed else 0)

if __name__ == "__main__":
    main()
