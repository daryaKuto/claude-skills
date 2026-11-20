#!/usr/bin/env python3
"""PreToolUse hook (Bash): denies (1) merging a permanent fork into anything and (2) hand-typed Claude attribution.
Same contract as stash-secret-guard.py: payload JSON on stdin; prints a deny decision, or nothing for "no decision". Never raises.

1. Forks: the branches listed in config.json fork_branches are permanent forks that must never merge into the default branch
   (an empty list turns this rule off). `git merge|pull|rebase|cherry-pick`
   whose SOURCE is a fork is denied unless the current branch (read from the -C dir or the payload cwd) is that same fork, so
   main INTO the fork still works. `gh pr create|merge` with a fork as head and main (or no --base) as base is denied.
2. Attribution: a `git commit` or `gh pr create|edit` whose text (inline, or a -F/--file/--body-file file up to 64 KB) has a
   Co-Authored-By trailer naming Claude or Anthropic, or "Generated with ... Claude". The raw command text is searched, because the
   usual `-m "$(cat <<'EOF' ...)"` form cannot be read word by word.
Reuses split() and words() from stash-secret-guard.py.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

_spec = importlib.util.spec_from_file_location("stash_secret_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stash-secret-guard.py"))
_ssg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ssg)
split, words = _ssg.split, _ssg.words

try:  # config.json is read once; a missing or broken file means no fork branches
    with open(os.environ.get("CLAUDE_HOOKS_CONFIG") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) as _f:
        FORKS = [b for b in json.load(_f).get("fork_branches", []) if isinstance(b, str) and b]
except Exception:
    FORKS = []

FORK_FIX = "Fork guard: this branch is a permanent fork; merges only go from main into it. Do not respell it, do not ask the user."
ATTR_FIX = "Attribution guard: remove the Claude attribution line (Co-Authored-By or Generated with). Do not respell it, do not ask the user."
FORK_RE = re.compile(r"^(refs/(heads|remotes)/)?([\w.-]+/)?(" + ("|".join(re.escape(b) for b in FORKS) or "(?!)") + ")$")
ATTR_RE = re.compile(r"co-authored-by:[^\n]*(claude|anthropic)|generated with[^\n]*claude", re.I)
LOCAL_FIX = ("Local-material guard: .claude/ and specs/ are local agent working material and are never committed (they are gitignored on purpose); "
             "do not force-add them.")
LOCAL_RE = re.compile(r"^(?:.*/)?\.claude(/|$)|^specs(/|$)")
FETCHED = set()  # forks named by a `git fetch` earlier in the same command, so a later `merge FETCH_HEAD` is caught
PREFIX = {"env", "command", "exec", "sudo", "nohup", "time", "nice"}
GIT_OPT_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def fork_of(arg):
    """The fork name an argument points at (also for a range a..b, a suffix ~2 or ^), or None."""
    for part in re.split(r"\.{2,3}", arg):
        part = re.sub(r"[~^]\d*$", "", part.split(":")[0] if arg.count(":") == 1 else part)
        m = FORK_RE.match(part)
        if m:
            return m.group(4)
    return None


def branch(d):
    try:
        return subprocess.run(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return ""


def read_file(path, cwd):
    try:
        with open(os.path.join(cwd, os.path.expanduser(path)), "rb") as f:
            return f.read(65536).decode("utf-8", "replace")
    except Exception:
        return ""


def file_args(args):
    """Paths passed with -F / --file / --body-file (short clusters like -aF too)."""
    out = []
    for i, a in enumerate(args):
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a in ("--file", "--body-file"):
            out.append(nxt)
        elif a.startswith(("--file=", "--body-file=")):
            out.append(a.split("=", 1)[1])
        elif re.fullmatch(r"-\w*F.*", a) and not a.startswith("--"):
            rest = a.split("F", 1)[1]
            out.append(rest or nxt)
    return [p for p in out if p and p != "-"]


def opt_value(args, names):
    for i, a in enumerate(args):
        if a in names and i + 1 < len(args):
            return args[i + 1]
        for n in names:
            if n.startswith("--") and a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def repo_top(d):
    """git toplevel for d, or for its nearest existing ancestor (a `cd` target may not exist yet)."""
    d = os.path.realpath(d)
    while not os.path.isdir(d) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    try:
        return os.path.realpath(subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=2).stdout.strip() or d)
    except Exception:
        return d


def judge_add(sub, rest, d):
    """LOCAL_FIX for a forced add (or update-index --add) of .claude/ or specs/, judged by the path relative to the
    repo top from the effective cwd (cd and -C resolved). A glob, pathspec magic or --pathspec-from-file in a forced add is denied
    outright: it cannot be resolved here, so name exact files."""
    opts = [a for a in rest if a.startswith("-") and a != "--"]
    force = (sub == "update-index" and "--add" in opts) or any(
        a == "-f" or (re.fullmatch(r"-\w*f\w*", a) and not a.startswith("--")) or (a.startswith("--") and len(a) >= 4 and "--force".startswith(a)) for a in opts)
    if not force:
        return None
    paths = [a for a in rest if not a.startswith("-")]
    if any(a.startswith("--pathspec-from-file") for a in opts) or any(re.search(r"[*?\[]", a) or a.startswith(":") for a in paths):
        return LOCAL_FIX + " A glob, pathspec magic or --pathspec-from-file cannot be checked: name the exact files."
    top = repo_top(d)
    for a in paths:
        if LOCAL_RE.match(os.path.relpath(os.path.realpath(os.path.join(d, os.path.expanduser(a))), top)):
            return LOCAL_FIX
    return None


def judge_git(args, cwd):
    d = cwd
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            d = os.path.join(d, args[i + 1])
        i += 2 if args[i] in GIT_OPT_ARG else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "fetch":
        FETCHED.update(f for f in map(fork_of, rest) if f)
        return None
    if sub in ("merge", "pull", "cherry-pick"):
        cands = [a for a in rest if not a.startswith("-")]
        if "FETCH_HEAD" in cands:
            cands += sorted(FETCHED)
    elif sub in ("add", "stage", "update-index"):
        return judge_add(sub, rest, d)
    elif sub == "rebase":
        onto = opt_value(rest, ("--onto",))
        pos = [a for a in rest if not a.startswith("-") and a != onto]
        cands = pos[:1] + ([onto] if onto else [])
    else:
        return None
    forks = {f for f in map(fork_of, cands) if f}
    if forks and not forks <= {branch(d)}:
        return FORK_FIX
    return None


def judge_gh(args, cwd):
    args = gh_args(args)
    if args[:2] not in (["pr", "create"], ["pr", "merge"]):
        return None
    rest = args[2:]
    base = opt_value(rest, ("--base", "-B"))
    if base is not None and base not in ("main", "master"):
        return None
    head = opt_value(rest, ("--head", "-H"))
    if head is None and args[1] == "merge":
        head = next((a for a in rest if not a.startswith("-")), None)
    if head is None:
        head = branch(cwd)
    return FORK_FIX if head and fork_of(head.split(":")[-1]) else None


PREFIX_VALUE = {"nice": {"-n"}, "sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U"}, "env": {"-u", "-C", "-S"}}


def strip_prefix(t):
    """Drop env assignments and prefix commands with their options (env -i, nice -n 5, sudo -u x, env -u FOO)."""
    while t and (re.fullmatch(r"\w+=.*", t[0]) or os.path.basename(t[0].lstrip("\\")) in PREFIX):
        pre = os.path.basename(t[0].lstrip("\\"))
        t = t[1:]
        while pre in PREFIX and t and t[0].startswith("-"):
            t = t[2:] if t[0] in PREFIX_VALUE.get(pre, ()) else t[1:]
    return t


def judge(seg, cwd, depth=0):
    t = words(seg)
    if t is None:
        return None
    t = strip_prefix(t)
    if not t:
        return None
    cmd, args = os.path.basename(t[0].lstrip("\\")), t[1:]
    if cmd in ("bash", "sh", "zsh", "dash", "ksh"):
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return scan(args[i + 1], cwd, depth + 1)
    elif cmd == "eval":
        return scan(" ".join(args), cwd, depth + 1)
    elif cmd == "git":
        return judge_git(args, cwd)
    elif cmd == "gh":
        return judge_gh(args, cwd)
    return None


def head(t):
    """(command, args) of a token list after env assignments and prefix commands, or (None, [])."""
    t = strip_prefix(t)
    return (os.path.basename(t[0].lstrip("\\")), t[1:]) if t else (None, [])


GH_OPT_ARG = {"-R", "--repo", "--hostname"}


def gh_args(args):
    """gh args with global flags (-R owner/repo, --repo=x) dropped from the front."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GH_OPT_ARG else 1
    return args[i:]


def git_sub(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_OPT_ARG else 1
    return args[i] if i < len(args) else None


READERS = {"cat", "head", "tail", "sed", "tac", "nl", "awk", "cut", "paste", "fold", "more", "less"}
SUBST_FIX = ("Attribution guard: a commit or PR whose text comes from a file named by a variable or an unreadable path cannot be checked. "
             "Write the message to a literal file and use git commit -F <file> (or gh pr create --body-file <file>). Do not respell it, do not ask the owner.")


def read_files(paths, dirs):
    """(text, unreadable): content of the regular files named, tried in each dir. A FIFO or device is skipped (reading it could hang)."""
    out, bad = [], False
    for p in paths:
        for d in dirs:
            f = os.path.join(d, os.path.expanduser(p))
            if os.path.isfile(f):
                txt = read_file(f, "")
                bad = bad or (not txt and not os.access(f, os.R_OK))
                out.append(txt)
                break
    return "\n".join(out), bad


def git_dirs(args, cwd):
    """cwd plus every -C directory of a git command: -F is read relative to the -C dir, a $(cat f) relative to cwd."""
    dirs, d, i = [cwd], cwd, 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            d = os.path.join(d, os.path.expanduser(args[i + 1]))
            dirs.insert(0, d)
        i += 2 if args[i] in GIT_OPT_ARG else 1
    return dirs


def attribution(segs, cmd, cwd):
    """ATTR_FIX when some segment is a commit / pr create|edit and the command text or a file it reads carries attribution.
    Files read: -F/--body-file, every `< file` redirect, and every file operand of cat/head/tail/sed/... in any segment
    ($( ) and backtick bodies are segments too). A reader whose path is a variable, or an unreadable file, is SUBST_FIX when
    the commit takes its message from stdin or a substitution is in play."""
    hit, dirs, stdin_fed = False, [cwd], False
    for seg in segs:
        t = words(seg) or seg.split()  # an unterminated quote (the $( heredoc form) still has a readable head
        c, args = head(t)
        if (c == "git" and git_sub(args) == "commit") or (c == "gh" and gh_args(args)[:2] in (["pr", "create"], ["pr", "edit"])):
            hit = True
            cd = git_dirs(args, cwd) if c == "git" else [cwd]
            dirs += [x for x in cd if x not in dirs]
            stdin_fed = stdin_fed or "-" in args
            if ATTR_RE.search(read_files(file_args(args), cd)[0]):
                return ATTR_FIX
    if not hit:
        return None
    subst = "$(" in cmd or "`" in cmd
    # split() leaves a $( ) inside double quotes as one quote-broken segment, so the bodies are split on their own
    bodies = [b for m in re.finditer(r"\$\(([^()]*)\)|`([^`]*)`", cmd) for b in split(m.group(1) or m.group(2) or "")]
    for seg in [(s, "|" in cmd) for s in segs] + [(b, True) for b in bodies]:
        seg, feeds = seg  # a top-level `cat f` only feeds the commit through a pipe; `git commit -m x && cat f` is not a message source
        t = words(seg)
        if not t:
            continue
        t, reads = _ssg.redirects(t)
        c, args = head(t)
        paths = list(reads) + ([a for a in args if not a.startswith("-")] if c in READERS and feeds else [])
        if not paths:
            continue
        text, bad = read_files([p for p in paths if "$" not in p], dirs)
        if ATTR_RE.search(text):
            return ATTR_FIX
        if (bad or any("$" in p for p in paths)) and (subst or stdin_fed):
            return SUBST_FIX
    # quotes and backslashes removed so 'Co-Authored-''By: Claude' cannot split the trailer
    return ATTR_FIX if ATTR_RE.search(re.sub(r"['\"\\]", "", cmd)) else None


def scan(cmd, cwd, depth=0):
    if depth > 5:
        return None
    if depth == 0:
        FETCHED.clear()
    segs = split(cmd)
    for seg in segs:
        t = words(seg)
        if t and os.path.basename(t[0]) == "cd" and len(t) > 1:  # later segments run in the new dir
            cwd = os.path.join(cwd, os.path.expanduser(t[1]))
        if (r := judge(seg, cwd, depth)):
            return r
    return attribution(segs, cmd, cwd)


def main():
    try:
        p = json.loads(sys.stdin.read())
        cmd = p["tool_input"]["command"]
        if not isinstance(cmd, str):
            return
        why = scan(cmd, p.get("cwd") or os.getcwd())
    except Exception:
        return
    if why:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": why}}))


if __name__ == "__main__":
    main()
