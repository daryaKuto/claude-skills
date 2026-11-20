#!/usr/bin/env python3
"""PreToolUse hook (Bash): the one dispatcher. Runs stash-secret-guard.py, commit-guard.py, tamper-guard.py and heavy-guard.py (next to
this file) in parallel as black boxes with the same stdin, and prints the strictest answer: deny > ask > no decision > allow.
It detects nothing itself, never raises, and prints nothing for no decision. A detector that prints nothing, is missing, crashes or
prints garbage is skipped, except a "closed" detector on a command it could really refuse: then the dispatcher denies (a broken
safety check must not read as "allowed"). The heavy detector guards the machine, not data, so a broken one lets the command through
("open"). One that runs out of the time budget is skipped the same way. No scanning of raw text for bad words happens here: each
detector reads the command as shell words. Cases: tests/policy-guard-cases.py."""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

T0, BUDGET = time.time(), 4.0  # seconds in all; the hook timeout is 5 s
HOOKS = os.path.dirname(os.path.abspath(__file__))
RANK = {"allow": 0, "none": 1, "ask": 2, "deny": 3}
UNSURE = "unsure"
QUOTE = r"[\"'$\\`]"  # a quote, $, backslash or backtick can hide a word from a regex
# name, path, quick gate (a superset of the detector's own quick exit), fail mode, danger pattern.
# fail "closed": when the detector crashes, exits non-zero, prints garbage or runs out of time on a command that matches its DANGER pattern
# (a narrow one: only commands the detector could really refuse, never a plain ls), the dispatcher denies. "open": skip it.
DETECTORS = (
    # git stash in every form, and reads of secret files or the environment. No quick gate: the guard takes ~20 ms and a word list
    # goes stale every time a new secret path is added.
    ("stash", f"{HOOKS}/stash-secret-guard.py", re.compile(""), "closed",
     re.compile(r"\bstash\b|\bprintenv\b|find-(generic|internet)-password|\bauth\s+token\b|\.env\b|\.aws/credentials|\.git-credentials|\.netrc\b")),
    # Merges out of the configured fork branches, and Claude attribution typed into a commit or PR.
    ("commit", f"{HOOKS}/commit-guard.py", re.compile(r"\b(git|gh)\b.*\b(merge|pull|rebase|cherry-pick|commit|add|pr)\b", re.S), "closed",
     re.compile(r"co-authored-by|generated with|\.claude/|specs/", re.I)),
    # Writes to the hooks, the settings files or a guard switch (OFF-*, NO_*) from Bash, so an agent cannot switch a guard off.
    ("tamper", f"{HOOKS}/tamper-guard.py", re.compile(""), "closed",  # always runs: after `cd ~/.claude/hooks` a bare `rm x.py` names no hook path
     re.compile(r"\.claude/(hooks|settings)|OFF-|NO_BACKGROUND_RULE")),
    # Heavy runs need the heavy lock (when one is configured), and nothing heavy starts while memory is critical. It guards the machine,
    # not data, so a broken check lets the command through.
    ("heavy", f"{HOOKS}/heavy-guard.py",
     re.compile(r"vitest|jest|tsc|tsx|ts-node|node|npm|npx|docker|cdk|xcodebuild|eas|pg_ctl|postgres|verify|bash|\bsh\b|zsh|\.bin/|"
                r"\buntil\b|\bwhile\b|\bsleep\b|watch|deploy|terraform|\bwait\b|\./"),
     "open", None),
)
DANGER = {n: (mode, rx) for n, _, _, mode, rx in DETECTORS}


def broken(name, cmd):
    """The deny for a closed detector that could not run on a command it could refuse; None for an open one or a harmless command."""
    mode, rx = DANGER.get(name, ("open", None))
    if mode == "closed" and rx.search(cmd):
        return "deny", f"policy: the {name} check could not run; retry the command, do not respell it"


def run(name, path, raw, cmd=""):
    """None (printed nothing: no decision), UNSURE (out of time), (answer, reason), or the deny from broken() when a closed detector
    crashed, exited non-zero (a missing file too) or printed garbage on a dangerous command (otherwise those are None, skipped)."""
    left = BUDGET - (time.time() - T0)
    if left < 0.05:
        return UNSURE
    try:
        p = subprocess.run([sys.executable, path], input=raw, capture_output=True, text=True, timeout=left)
        if p.returncode:
            return broken(name, cmd)
        if not p.stdout.strip():
            return None  # no decision
        o = json.loads(p.stdout)["hookSpecificOutput"]
        kind, why = o["permissionDecision"], o["permissionDecisionReason"]
        return (kind, why) if kind in ("allow", "ask", "deny") and isinstance(why, str) else broken(name, cmd)
    except subprocess.TimeoutExpired:
        return UNSURE
    except Exception:
        return broken(name, cmd)


RAW = ""
# The gate regexes use `.*` with re.S, which is quadratic: a 30,000-word command took 14.7 s. Every command over HUGE
# characters is denied before any gate runs.
HUGE = 40_000


def main():
    global RAW
    raw = RAW = sys.stdin.read()
    cmd = json.loads(raw)["tool_input"]["command"]
    if not isinstance(cmd, str):
        return
    if len(cmd) > HUGE:  # a word search could miss `g""it pu''sh` or a $X expansion in text this big
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason":
              "policy: this command is over 40 KB, which the checks cannot read. Put the text in a file with the Write tool and run the file, or split the command."}}))
        return
    todo = [(n, p) for n, p, gate, _, _ in DETECTORS if gate.search(cmd)]
    if not todo:
        return  # ThreadPoolExecutor(0) raises, which used to be swallowed as an allow
    with ThreadPoolExecutor(len(todo)) as ex:
        got = list(ex.map(lambda d: run(d[0], d[1], raw, cmd), todo))
    answers = [a for a in (broken(n, cmd) if r == UNSURE else r for (n, _), r in zip(todo, got) if r) if a]
    if answers:
        kind, why = max(answers, key=lambda a: RANK[a[0]])  # the first of equals wins
        if kind != "none":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind, "permissionDecisionReason": why}}))


try:
    main()
except Exception:
    try:  # an internal error: deny when the command could be refused by any closed detector, else allow
        cmd = json.loads(RAW)["tool_input"]["command"]
        if isinstance(cmd, str) and any(broken(n, cmd) for n in DANGER):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": "policy: the policy check could not run; retry the command, do not respell it"}}))
    except Exception:
        pass
sys.exit(0)
