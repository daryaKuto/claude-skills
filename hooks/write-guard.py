#!/usr/bin/env python3
"""PreToolUse guard for the Write, Edit, MultiEdit and NotebookEdit tools .

tamper-guard only sees Bash, so a subagent could rewrite a guard, the settings or a guard switch with one Edit call. This
refuses that for SUBAGENTS (payloads that carry agent_id: Agent-tool workers, workflow agents, helpers in other worktrees). The main
session (the orchestrator you watch) and your own editor are not affected.

When the orchestrator delegates a guard fix, it opens a window first: write an epoch (seconds) into
~/.claude/hooks/state/write-guard/ALLOW_AGENTS_UNTIL. Subagents cannot open it themselves: that file is inside the
protected hooks folder, Bash writes there are refused by tamper-guard, and Write/Edit there by this guard.

Protected: ~/.claude/hooks/**, ~/.claude/settings*.json, ~/.claude/CLAUDE.md, and the .claude/hooks/** and .claude/settings*.json
of every project folder listed in config.json protected_extra_dirs (lane_dirs lists worktree folders whose .claude/settings*.json
are guarded too). Any crash or unreadable payload on a protected path denies (fail closed)."""
import glob
import json
import os
import sys
import time

HOME = os.path.realpath(os.path.expanduser("~"))
CLAUDE = os.path.join(HOME, ".claude")
try:  # config.json is read once; a missing or broken file means no extra folders
    with open(os.environ.get("CLAUDE_HOOKS_CONFIG") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) as _f:
        CFG = json.load(_f)
except Exception:
    CFG = {}
EXTRA_ROOTS = [os.path.realpath(os.path.expanduser(d)) for d in CFG.get("protected_extra_dirs", [])]
EXTRA_CLAUDE = [os.path.join(r, ".claude") for r in EXTRA_ROOTS]
LANES = [os.path.realpath(os.path.expanduser(d)).lower() for d in CFG.get("lane_dirs", [])]
WINDOW = os.environ.get("WRITE_GUARD_WINDOW") or os.path.join(CLAUDE, "hooks", "state", "write-guard", "ALLOW_AGENTS_UNTIL")
WHY = ("Write guard: guard files (hooks, settings, CLAUDE.md) are changed by the main session in a reviewed change, not by a "
       "subagent. Report the exact edit you need (file, old text, new text) to your orchestrator and continue with the rest.")


def worktree_roots():
    """Roots of the git worktrees of the protected projects (their .claude/settings*.json load the hooks too)."""
    out = []
    for f in [g for r in EXTRA_ROOTS for g in glob.glob(os.path.join(r, ".git", "worktrees", "*", "gitdir"))]:
        try:
            out.append(os.path.dirname(os.path.realpath(open(f).read().strip())).lower())
        except OSError:
            pass
    return out


def switch_file(p):
    """Non-hook files that switch guards off: guard-bin (pkill/killall wrappers), watchdog, ~/.zshenv, the watchdog launchd
    plists, and .claude/settings*.json under lane_dirs or in any worktree of a protected project."""
    base, c = os.path.basename(p), CLAUDE.lower()
    if p in (c + "/guard-bin", c + "/watchdog") or p.startswith((c + "/guard-bin/", c + "/watchdog/")) or p == os.path.join(HOME, ".zshenv").lower():
        return True
    if os.path.dirname(p) == os.path.join(HOME, "Library", "LaunchAgents").lower() and "watchdog" in base and base.endswith(".plist"):
        return True
    if base.startswith("settings") and base.endswith(".json") and os.path.basename(os.path.dirname(p)) == ".claude":
        root = os.path.dirname(os.path.dirname(p))
        return any(root.startswith(l + "/") for l in LANES) or root in worktree_roots()
    return False


def protected(p, cwd=None):
    # macOS file names are case-insensitive: ~/.claude/HOOKS/x.py is the hooks folder, so compare lower-cased
    p = os.path.expanduser(p)
    if cwd and not os.path.isabs(p):  # a relative path is relative to the tool call's cwd, not the hook's own
        p = os.path.join(cwd, p)
    p = os.path.realpath(p).lower()
    if switch_file(p):
        return True
    for root in (CLAUDE.lower(), *(c.lower() for c in EXTRA_CLAUDE)):
        rel = os.path.relpath(p, root)
        if rel.startswith(".."):
            continue
        first, base = rel.split(os.sep, 1)[0], os.path.basename(p)
        if first == "hooks" or (os.sep not in rel and base.startswith("settings") and base.endswith(".json")):
            return True
        if root == CLAUDE.lower() and rel == "claude.md":
            return True
    return False


def window_open():
    try:
        return time.time() < float(open(WINDOW).read().strip())
    except (OSError, ValueError):
        return False


def deny():
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": WHY}}))


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        if not data.get("agent_id"):  # the main session: not this guard's business
            return
        ti = data.get("tool_input") or {}
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        paths = [x for x in (ti.get("file_path"), ti.get("notebook_path"), ti.get("path")) if isinstance(x, str) and x]
        if any(protected(x, cwd) for x in paths) and not window_open():
            deny()
    except Exception:
        # fail closed only when the raw payload is a subagent call naming a protected place
        if '"agent_id"' in raw and any(s in raw for s in ("/.claude/hooks", "/.claude/settings", "/.claude/CLAUDE.md", "/.claude/guard-bin", "/.claude/watchdog", "/.zshenv")):
            deny()


main()
