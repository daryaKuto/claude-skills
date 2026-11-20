#!/usr/bin/env python3
"""PreToolUse hook (Bash): denies a shell command that writes, moves, deletes, chmods or links a guard file.
Same contract as commit-guard.py: payload JSON on stdin; prints a deny decision, or nothing for "no decision". Never raises.

Protected: everything under ~/.claude/hooks/ (the hooks, their tests and backups), ~/.claude/settings*.json, the .claude/hooks/ and
.claude/settings*.json of every project folder listed in config.json protected_extra_dirs, and any file named
OFF-*, NO_* (NO_BACKGROUND_RULE included) under ~/.claude. These are the guards and their switches: only you, or the Edit
tool in a reviewed change, may change them. config.json lane_dirs lists folders of git worktrees whose .claude/settings*.json are guarded too.
Allowed: reads, running a hook or a tests/*.py file, writes elsewhere, writes under hooks/state/ (hooks keep their own state there)
except the switch names above, and creating hooks/state/heavy-guard/ENFORCE_LOCK (it only makes a guard stricter; deleting it is denied).

This is a best-effort TEXT check of the command, not a sandbox. It does not stop a determined bypass: a script written elsewhere and then
run, an editor, a tar archive that unpacks into the hooks, or a path built by the shell at run time can all still get past it. Git aimed
at a guard folder is checked: --work-tree, --git-dir, GIT_WORK_TREE and GIT_DIR (a relative, shell-built or unreadable value is refused),
each against the guard folders AND their parents. It catches the common and the accidental forms.
Parent-folder rule: a check that protects a folder also covers every parent of it. rm, mv, a whole-folder copy
(rsync src/, cp -r src/., ditto, a glob) or git work-tree aimed at ~, ~/Documents or a protected project's root changes the guard
as surely as touching it. tests/tamper-ancestors-cases.py generates its rows from the guard folders, so a narrowing fails there.
One allowed exception: `find <parent> ... -not -path '*/.claude/*' -delete` (or -exec rm), because every guard file lives under .claude;
a find without that exclusion, or with -o or parentheses, is denied with a message that says how to narrow it. The expected way to change a hook is the Edit tool in a reviewed
change, which this guard never sees.
Reuses split(), words() and head() from commit-guard.py (imported lazily; if that import fails, every command that names a protected place is denied).
"""
import fnmatch
import glob
import importlib.util
import json
import os
import re
import shlex
import sys

split = words = head = None  # filled by load() once the quick exit says the command needs a closer look


def load():
    """Import commit-guard.py's helpers; False when that fails (main() then denies anything that names a protected place)."""
    global split, words, head
    try:
        spec = importlib.util.spec_from_file_location("commit_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "commit-guard.py"))
        cg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cg)
        split, words, head = cg.split, cg.words, cg.head
        return True
    except Exception:
        return False

FIX = "Tamper guard: guards and their switches are changed only by the user or with the Edit tool in a reviewed change; do not respell it, do not ask the user. To read a guard file use cat, jq or the Read tool; a read-only python one-liner must be a plain `python3 -c \"print(open(path).read())\"` or json.load template."
HOME = os.path.expanduser("~")


def rp(p):
    """realpath, lower-cased: macOS file names are case-insensitive, so ~/.claude/HOOKS is the hooks folder. Every path
    compare in this file goes through here (found in review); text regexes are re.I for the same reason."""
    return os.path.realpath(p).lower()


CLAUDE = rp(os.path.join(HOME, ".claude"))
HOOKS = os.path.join(CLAUDE, "hooks")
# Project folders whose own guards are loaded from their .claude/hooks are protected too (config.json, read once; a missing or broken
# file means none). Only their hooks/ folder and settings*.json: plans, skills and launch.json under the same .claude stay writable.
try:
    with open(os.environ.get("CLAUDE_HOOKS_CONFIG") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) as _f:
        CFG = json.load(_f)
except Exception:
    CFG = {}
EXTRA_ROOTS = [rp(os.path.expanduser(d)) for d in CFG.get("protected_extra_dirs", [])]
EXTRA_CLAUDE = [os.path.join(r, ".claude") for r in EXTRA_ROOTS]
EXTRA_HOOKS = [os.path.join(c, "hooks") for c in EXTRA_CLAUDE]
LANES = [rp(os.path.expanduser(d)) for d in CFG.get("lane_dirs", [])]

# Cheap pre-filter on the raw command (a superset of what scan() can deny).
GATE = re.compile(r"\.claude|hooks|OFF-|NO_|settings|ENFORCE_LOCK|guard-bin|watchdog|zshenv", re.I)
# Any text that could name a protected place: used when the guard itself cannot run and must decide blind.
MENTION_RX = re.compile(r"\.claude|hooks|OFF-|NO_|settings|ENFORCE_LOCK", re.I)

CREATE, DESTROY = "create", "destroy"
INTERP = re.compile(r"^(python[\d.]*|node(js)?|perl|ruby|php|deno|bun)$")
CODE_FLAG = re.compile(r"^-[A-Za-z]*[ce]$|^--eval$")
PROT_TEXT = re.compile(r"\.claude|/hooks\b|\bhooks/|OFF-|NO_[A-Z]|settings[\w.-]*\.json|ENFORCE_LOCK", re.I)
# Any word that can write, move, delete or run something, in python, node, perl, ruby or php source.
WRITE_CAP = re.compile(r"open|write|remove|unlink|rename|replace|copy|move|rmtree|Path|os\.|shutil|fs\.|subprocess|system|exec|chmod|chown|touch|"
                       r"truncate|symlink|link|mkdir|append|File|popen|spawn|\bos\b|getattr|builtins|__import__|\brm|Sync", re.I)
_L = r"""(?:'[^'"\\$`;]*'|"[^'"\\$`;]*")"""  # a plain string literal: no escapes, no shell or statement characters inside
_RD = r"""['"]r[bt]?['"]"""
# The ONLY interpreter programs allowed to name a protected path: the whole command is one read-only one-liner of these shapes.
RO_PROG = re.compile(
    r"(?:(?:/[\w.+-]+)*/)?(?:python[\d.]*|node)\s+-[ce]\s+(['\"])(?:"  # plain path only: \S* let `touch$IFS<hook>;/python3` through
    rf"(?:import json;\s*)?print\(json\.load\(open\({_L}\)\)(?:\[{_L}\])*\)"
    rf"|print\(open\({_L}(?:,\s*{_RD})?\)\.read\(\)\)"
    rf"|(?:from pathlib import Path;\s*)?print\(Path\({_L}\)\.read_(?:text|bytes)\(\)\)"
    rf"|console\.log\(require\({_L}\)\.readFileSync\({_L}(?:,\s*{_L})?\)\)"
    r")\1")


MENTION = False  # set per command in main(): does it name a protected place anywhere (after quote removal)?


FIND_FIX = ("Tamper guard: this find would delete or run rm under a folder that holds protected guard files (a protected project's .claude/hooks and "
            "settings*.json, or ~/.claude/hooks). Narrow the find root (find src ...) or add -not -path '*/.claude/*' before -delete or -exec; "
            "do not ask the user.")


def is_switch(base):
    return base.upper().startswith(("OFF-", "NO_"))


def resolve(tok, cwd):
    """Real absolute path for a token, or None when a variable or command substitution is left in it."""
    t = tok.replace("${HOME}", HOME).replace("$HOME", HOME)
    if "$" in t or "`" in t:
        return None
    t = os.path.expanduser(t)
    if not os.path.isabs(t):
        t = os.path.join(cwd, t)
    return rp(os.path.normpath(t))


LAUNCH = rp(os.path.join(HOME, "Library", "LaunchAgents"))


def worktree_roots():
    """Roots of the git worktrees of the protected projects (read from .git/worktrees/*/gitdir; the main checkout is the project root)."""
    out = []
    for f in [g for r in EXTRA_ROOTS for g in glob.glob(os.path.join(r, ".git", "worktrees", "*", "gitdir"))]:
        try:
            out.append(rp(os.path.dirname(open(f).read().strip())))
        except OSError:
            pass
    return out


def switch_file(path):
    """Files outside hooks/ that switch a guard off: the pkill/killall wrappers, the watchdog, ~/.zshenv (file-size cap, renice, PATH
    shim), the watchdog launchd plists, and .claude/settings*.json of any worktree of a protected project or under lane_dirs (the hooks are loaded from it)."""
    base = os.path.basename(path)
    if any(path == d or path.startswith(d + "/") for d in (CLAUDE + "/guard-bin", CLAUDE + "/watchdog")):
        return True
    if path == rp(os.path.join(HOME, ".zshenv")):
        return True
    if os.path.dirname(path) == LAUNCH and "watchdog" in base and base.endswith(".plist"):
        return True
    if fnmatch.fnmatch(base, "settings*.json") and os.path.basename(os.path.dirname(path)) == ".claude":
        root = os.path.dirname(os.path.dirname(path))
        return any(root.startswith(l + "/") for l in LANES) or root in worktree_roots()
    return False


def protected(path, kind):
    base = os.path.basename(path)
    if switch_file(path):
        return True
    if path == HOOKS or path.startswith(HOOKS + "/"):
        rel = path[len(HOOKS) + 1:]
        if rel == "state":
            return kind == DESTROY
        if rel == "state/write-guard" or rel.startswith("state/write-guard/"):
            return True  # write-guard's agent window (ALLOW_AGENTS_UNTIL): a subagent opening it switches that guard off
        if rel.startswith("state/"):
            if is_switch(base):
                return True
            return base.upper() == "ENFORCE_LOCK" and kind == DESTROY
        return True
    if path.startswith(CLAUDE + "/") and is_switch(base):
        return True
    if os.path.dirname(path) == CLAUDE and fnmatch.fnmatch(base, "settings*.json"):
        return True
    if any(path == h or path.startswith(h + "/") for h in EXTRA_HOOKS):
        return True
    if os.path.dirname(path) in EXTRA_CLAUDE and fnmatch.fnmatch(base, "settings*.json"):
        return True
    if kind == DESTROY and any(h.startswith(path.rstrip("/") + "/") for h in EXTRA_HOOKS):  # rm -rf <repo>/.claude, <repo> or a parent takes its hooks with it
        return True
    return kind == DESTROY and HOOKS.startswith(path.rstrip("/") + "/")  # rm -rf ~/.claude or ~ takes the hooks with it


def braces(tok, depth=0):
    """Bash brace expansion of one word ({a,b} lists and {1..3} ranges), so `.cl{a,}ude` is checked as .claude too."""
    m = re.search(r"\{([^{}]*)\}", tok)
    if not m or depth > 6:
        return [tok]
    inner, out = m.group(1), []
    r = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", inner)
    if "," in inner:
        parts = inner.split(",")
    elif r and abs(int(r.group(2)) - int(r.group(1))) < 200:
        a, b = int(r.group(1)), int(r.group(2))
        parts = [str(i) for i in range(a, b + (1 if b >= a else -1), 1 if b >= a else -1)]
    else:  # a lone {x} is literal in bash; keep it and expand anything after it
        return [tok[:m.end()] + rest for rest in braces(tok[m.end():], depth + 1)]
    for p in parts:
        out += braces(tok[:m.start()] + p + tok[m.end():], depth + 1)
    return out[:500]


def exact_braces(tok):
    """True when braces() expands this word exactly: every {..} is a comma list, a numeric range under 200, or a lone
    literal {x} with no '..' in it, and the result fits the 500-word cap."""
    for inner in re.findall(r"\{([^{}]*)\}", tok):
        if "," in inner:
            continue
        r = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", inner)
        if r and abs(int(r.group(2)) - int(r.group(1))) < 200:
            continue
        if ".." in inner:  # letter or step range ({a..c}, {1..9..2}) or a huge one: not emulated
            return False
    return len(braces(tok)) < 500 and tok.count("{") <= 6


def hits(tok, kind, cwd):
    """True when a path token, any word its braces expand to, or any file a glob in it matches, is protected."""
    if "{" in tok and not exact_braces(tok):
        # A write target with a brace form we cannot expand exactly (letter or step range, huge range) is refused wherever
        # it points: matching keywords on a rewritten word was bypassable twice (found in review).
        # The hint tells the agent to write the names out.
        return True
    if "{" in tok:
        words = braces(tok)
        if len(words) > 1 or words[0] != tok:
            return any(hits(w, kind, cwd) for w in words if "{" not in w or w != tok)
    p = resolve(tok, cwd)
    if p is None:
        # A write target built by the shell ($D/OFF-x after D=~/.claude/hooks) cannot be checked. Refuse it when the
        # command mentions a protected place anywhere; elsewhere ($TMPFILE, $OUT) it stays allowed (found in review).
        return MENTION
    if any(c in tok for c in "*?["):
        raw = os.path.expanduser(tok.replace("$HOME", HOME))
        found = glob.glob(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
        return any(protected(rp(f), kind) for f in found) or protected(p, kind)
    return protected(p, kind)


def operands(args, with_value=()):
    out, i, end = [], 0, False
    while i < len(args):
        a = args[i]
        if not end and a == "--":
            end = True
        elif not end and a in with_value:
            i += 1
        elif end or a == "-" or not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def redirect_targets(seg):
    """Targets of unquoted > and >> in a raw segment (fd duplications like 2>&1 are skipped)."""
    out, q, i = [], None, 0
    while i < len(seg):
        c = seg[i]
        if q:
            if q == '"' and c == "\\":
                i += 1  # an escaped quote inside double quotes does not close them
            elif c == q:
                q = None
        elif c in "'\"":
            q = c
        elif c == "\\":
            i += 1
        elif c == ">":
            j = i + 1
            while j < len(seg) and seg[j] in ">|":
                j += 1
            if j < len(seg) and seg[j] == "&":
                i = j
            else:
                while j < len(seg) and seg[j] == " ":
                    j += 1
                k, qq = j, None
                while k < len(seg) and (qq or seg[k] not in " \t"):
                    if qq:
                        qq = None if seg[k] == qq else qq
                    elif seg[k] in "'\"":
                        qq = seg[k]
                    k += 1
                w = words(seg[j:k])
                if w:
                    out.append(w[0])
                i = k - 1
        i += 1
    return out


def prot_text(a):
    b = re.sub(r"hooks/state/(?!OFF-|NO_|ENFORCE_LOCK)", "", a)  # hook state files are not protected (see protected())
    return bool(PROT_TEXT.search(b))


def inline_code(cmd, cwd, depth, seg=None):
    """True when interpreter source text names a protected path AND holds any write-capable word, unless the only mentions are
    read-only shapes (open(<literal>) with mode r/rb, Path(<literal>).read_text(), fs.readFileSync(<literal>)). Denying by default
    means an alias, a variable or a call shape we do not list still gets refused."""
    t = cmd.replace('\\"', '"')  # python3 -c "open(\"x\",\"w\")": the shell quoting is not part of the code
    # Code run from inside a guard folder (after cd, or a cwd already there) can hit a file by a relative name it builds
    # ('set'+'tings.json'), and `.cla` + `ude` splits hide the folder name: both count as naming a protected place.
    rc = rp(cwd)
    inside = any(rc == r or rc.startswith(r + "/") for r in (CLAUDE, *EXTRA_CLAUDE))
    named = (".claude" in cmd.lower() and re.search(r"hooks|settings|OFF-|NO_", cmd, re.I)) or inside or re.search(r"\.cla(?!ude)", t, re.I)
    if not named:
        return False
    # Decided on the original text: names a protected path and can write -> refused, unless the whole command is one read-only template.
    # The read-only template is matched against this one segment, so `cd ~/.claude && python3 -c "<read>"` is a read; other
    # segments of the command are judged on their own (a write in any of them still denies).
    one = (seg if seg is not None else cmd).replace('\\"', '"').strip()
    for other in split(cmd.replace(">|", ">")):
        if other.strip() == (seg or "").strip():
            continue
        w = words(other) or []
        if not (w and w[0] in ("cd", "pushd") and not re.search(r"[$`]", other)):
            one = ""  # anything but a plain cd next to the template (`touch$IFS<hook>;/python3 -c ...`) keeps the whole-command rule
    return bool((prot_text(t) or inside or re.search(r"\.cla(?!ude)", t)) and WRITE_CAP.search(t) and not RO_PROG.fullmatch(one))


def child_writes(srcs, dest, c="", args=(), cwd="/"):
    """cp -r /tmp/evil/hooks ~/.claude/ writes ~/.claude/hooks/*: when a source's name is a protected child (hooks, settings*.json)
    the destination's child of that name is a write target too. The source need not exist, so only its name is read.
    When the destination IS a guard parent (~/.claude or a protected project's .claude) and the copy brings in a whole folder's
    contents (rsync src/ dest, cp src/. dest, cp -T, ditto, or a source with a glob) the children hooks and settings.json are
    write targets too: the names inside the source are not known."""
    if not dest:
        return []
    kids = [os.path.basename(s.rstrip("/")).lower() for s in srcs]  # compared with lower-cased guard paths (rp)
    # every source lands as dest/<its name>: let protected() and switch_file() judge each (cp ~/evil/.zshenv ~/, cp x/guard-bin ~/.claude/)
    out = [(os.path.join(dest, k), CREATE) for k in kids if k]
    p = resolve(dest, cwd)
    if not p:
        return out
    whole = (c == "ditto" or (c == "rsync" and any(s.endswith("/") for s in srcs)) or any(s.endswith("/.") for s in srcs)
             or "--no-target-directory" in args or any(re.fullmatch(r"-[A-Za-z]*T[A-Za-z]*", a) for a in args)
             or any(re.search(r"[*?\[]", s) for s in srcs))
    if p in (CLAUDE, *EXTRA_CLAUDE) and whole:
        out += [(os.path.join(dest, "hooks"), CREATE), (os.path.join(dest, "settings.json"), CREATE)]
    # A recursive copy into a parent of a guard folder (~, ~/Documents, a project root) lands in it when the copy is whole-folder
    # or the source is itself named .claude or hooks.
    recursive = c == "ditto" or (c in ("cp", "rsync") and any(re.fullmatch(r"-[A-Za-z]*[raR][A-Za-z]*", a) or a in ("--recursive", "--archive") for a in args))
    if recursive:
        for g in (CLAUDE, *EXTRA_CLAUDE, HOOKS, *EXTRA_HOOKS):
            base = p.rstrip("/") + "/"
            if g.startswith(base):  # the source lands on the guard when its name is the next folder on the way down
                first = g[len(base):].split("/", 1)[0]
                if whole or any(k == first or re.search(r"[*?\[]", k) for k in kids):
                    out.append((os.path.join(g, "hooks") if g in (CLAUDE, *EXTRA_CLAUDE) else g, CREATE))
    return out


def writes(c, args, cwd):
    """(path token, kind) pairs a command writes to."""
    out = []
    if c == "tee":
        out += [(a, CREATE) for a in operands(args)]
    elif c in ("touch", "mkdir"):
        out += [(a, CREATE) for a in operands(args)]
    elif c in ("rm", "rmdir", "unlink", "shred"):
        out += [(a, DESTROY) for a in operands(args)]
    elif c == "truncate":
        out += [(a, DESTROY) for a in operands(args, ("-s", "--size", "-r", "--reference"))]
    elif c in ("chmod", "chown", "chgrp"):
        out += [(a, DESTROY) for a in operands(args, ("--reference",))]  # the mode token never resolves to a protected path
    elif c == "mv":
        ops = operands(args, ("-t", "-S"))
        t = next((args[i + 1] for i, a in enumerate(args) if a == "-t" and i + 1 < len(args)), None)
        out += [(a, DESTROY) for a in ops[:-1]] + [(ops[-1], CREATE)] if ops else []
        if t:
            out.append((t, CREATE))
        out += child_writes(ops if t else ops[:-1], t or (ops[-1] if ops else None), c, args, cwd)
    elif c in ("cp", "install", "rsync", "ln"):
        ops = operands(args, ("-t", "-S", "-e"))
        t = next((args[i + 1] for i, a in enumerate(args) if a == "-t" and i + 1 < len(args)), None)
        out.append((t or ops[-1], CREATE)) if (t or ops) else None
        if c != "ln":
            out += child_writes(ops if t else ops[:-1], t or (ops[-1] if ops else None), c, args, cwd)
        # A hard link (ln without -s, cp -l) to a protected SOURCE lets a later write through the new name change the hook.
        flags = [a for a in args if a.startswith("-") and not a.startswith("--")]
        if (c == "ln" and not any("s" in f for f in flags) and "--symbolic" not in args) or (c == "cp" and (any("l" in f for f in flags) or "--link" in args)):
            out += [(a, CREATE) for a in (ops if t else ops[:-1])]
    elif c == "ditto":
        ops = operands(args)
        out += [(ops[-1], CREATE)] if ops else []
        out += child_writes(ops[:-1], ops[-1] if ops else None, c, args, cwd)
    elif c == "chflags":
        out += [(a, DESTROY) for a in operands(args)[1:]]
    elif c == "xattr" and any(re.fullmatch(r"-[a-z]*[wdc][a-z]*", a) for a in args):
        out += [(a, DESTROY) for a in operands(args)]
    elif c == "dd":
        out += [(a[3:], CREATE) for a in args if a.startswith("of=")]
    elif c == "sed" and any(re.fullmatch(r"-[A-Za-z]*i.*|--in-place.*", a) for a in args):
        out += [(a, CREATE) for a in operands(args)]
    elif c in ("perl", "ruby") and any(re.fullmatch(r"-[A-Za-z]*i.*", a) for a in args):
        out += [(a, CREATE) for a in operands(args)]
    elif c in ("awk", "gawk") and "inplace" in args:
        out += [(a, CREATE) for a in operands(args)]
    elif c == "curl":
        out += [(args[i + 1], CREATE) for i, a in enumerate(args) if a in ("-o", "--output") and i + 1 < len(args)]
    elif c == "wget":
        out += [(args[i + 1], CREATE) for i, a in enumerate(args) if a in ("-O", "--output-document") and i + 1 < len(args)]
    elif c == "find" and ("-delete" in args or any(a in ("-exec", "-execdir", "-ok") for a in args)):
        roots = []
        for a in args:
            if a.startswith("-") or a in ("(", "!"):
                break
            roots.append(a)
        # A find whose root only CONTAINS the guard folders (the repo root, ~) is safe when an exclusion of '*/.claude/*' ANDs in before the
        # first -delete/-exec: every hook, settings file and switch lives under a .claude folder, so none can match. Any -o, -or or ( drops
        # the proof (the exclusion might not cover the other branch). A root that is inside a guard folder still counts.
        stop = next(i for i, a in enumerate(args) if a == "-delete" or a in ("-exec", "-execdir", "-ok"))
        pre = args[:stop]
        excl = (any(a in ("-not", "!") and pre[i + 1:i + 3] == ["-path", "*/.claude/*"] for i, a in enumerate(pre))
                and not any(a in ("-o", "-or", "(", "\\(") for a in args))
        # Only a STRICT ancestor of a .claude folder is exempt: from a root at or inside .claude the printed paths lack the leading "/.claude/".
        def exempt(a):
            r = resolve(a, cwd)
            return r is not None and any(g.startswith(r.rstrip("/") + "/") for g in (CLAUDE, *EXTRA_CLAUDE))
        out += [(a, DESTROY) for a in roots if not (excl and exempt(a))]
    return out


def judge(seg, cwd, whole, depth):
    t = words(seg)
    if t is None:
        t = seg.split()
    c, args = head(t)
    for tok in redirect_targets(seg):
        if hits(tok, CREATE, cwd):
            return FIX
    if not c:
        return None
    if c in ("bash", "sh", "zsh", "dash", "ksh"):
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return scan(args[i + 1], cwd, depth + 1)
    elif c == "eval":
        return scan(" ".join(args), cwd, depth + 1)
    elif c == "xargs":
        c2, a2 = head(args)  # xargs rm: the file names come from stdin, so the command text decides
        if c2 and writes(c2, a2 + [x for x in re.findall(r"\S+", whole)], cwd):
            return FIX
        return None
    elif INTERP.match(c):
        _, a2 = head(words(re.sub(r"<<-?\s*\S+", "", seg)) or [])  # heredoc marker is not a script name
        ops = operands(a2, ("-m", "-W", "-X", "-I"))
        coded = any(CODE_FLAG.match(a) for a in args) or (("<<" in seg) and ops in ([], ["-"]))
        if coded and inline_code(whole, cwd, depth, seg):
            return FIX
    for tok, kind in writes(c, args, cwd) + special(c, args, cwd, depth):
        if tok is True or hits(tok, kind, cwd):
            return FIND_FIX if c == "find" else FIX
    return None


# Allowlist: against the hooks repo only these git subcommands run (the build commits its own work); everything else is refused.
GIT_OK = {"log", "show", "diff", "status", "blame", "ls-files", "rev-parse", "cat-file", "grep", "shortlog", "describe", "add", "commit"}


def in_hooks(p, cwd):
    """The path is the hooks repo or inside it. Only git aimed at the hooks repo itself counts: an ancestor test would match
    a project root and ~, and deny ordinary git checkout and git rm there."""
    r = rp(os.path.join(cwd, os.path.expanduser(p)))
    return r == HOOKS or r.startswith(HOOKS + "/")


def guard_or_parent(p, cwd):
    """--work-tree / --git-dir name the files git changes, so a PARENT of a guard folder (~/.claude, a project root) counts too;
    -C and the cwd only count when inside the hooks repo (ordinary git in a project root stays allowed)."""
    r = rp(os.path.join(cwd, os.path.expanduser(p))).rstrip("/")
    # the guard folder itself, anything inside it, or any parent of it (tests/tamper-ancestors-cases.py holds this rule)
    return any(r == g or r.startswith(g + "/") or g.startswith(r + "/") for g in (HOOKS, *EXTRA_HOOKS, CLAUDE, *EXTRA_CLAUDE))


def git_on_hooks(args, cwd):
    """True for a history-rewriting or tree-changing git subcommand aimed at the hooks repo (-C, --git-dir, --work-tree or the cwd)."""
    d, hit, cfg, i, trees = cwd, False, False, 0, []
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            d, i = os.path.join(d, os.path.expanduser(args[i + 1])), i + 1
        elif a in ("--git-dir", "--work-tree") and i + 1 < len(args):
            trees, i = trees + [args[i + 1]], i + 1
        elif a.startswith(("--git-dir=", "--work-tree=")):
            trees.append(a.split("=", 1)[1])
        elif a in ("-c", "--namespace", "--exec-path", "--config-env") and i + 1 < len(args):
            cfg, i = cfg or a in ("-c", "--config-env"), i + 1
        elif a.startswith("--config-env="):
            cfg = True
        i += 1
    # a relative --work-tree / --git-dir may resolve against the cwd or the -C folder: check both (fail closed)
    hit = any(not os.path.expanduser(t).startswith("/") or re.search(r"[$`*?{\[]", t)  # relative or shell-built: refuse
              or guard_or_parent(t, cwd) for t in trees)
    sub =args[i] if i < len(args) else None
    if not (hit or in_hooks(d, cwd)):
        return False
    if cfg:  # -c can set core.pager, core.fsmonitor, alias.x=!cmd ...: it runs commands
        return True
    rest = args[i + 1:]
    for a in rest:  # options that write a file or run a program (git accepts any unique prefix of a long option)
        o = a.split("=")[0]
        if (a.startswith("-") and not a.startswith("--") and "O" in a) or (o.startswith("--") and len(o) >= 4 and any(b.startswith(o) for b in ("--output", "--open-files-in-pager", "--ext-diff", "--textconv", "--exec"))):
            return True
    if sub in ("branch", "tag"):  # listing only
        return not ("--list" in rest or "-l" in rest)
    return sub is not None and sub not in GIT_OK


def special(c, args, cwd, depth):
    """Write targets that are not a plain operand: (path, kind) pairs, or (True, _) for 'refuse'."""
    out = []
    if c == "git" and git_on_hooks(args, cwd):
        out.append((True, DESTROY))
    elif c == "patch":
        ds = [args[i + 1] for i, a in enumerate(args) if a in ("-d", "--directory") and i + 1 < len(args)] + \
             [a.split("=", 1)[1] for a in args if a.startswith("--directory=")]
        ops = operands(args, ("-d", "--directory", "-i", "--input", "-p", "--strip", "-r", "--reject-file", "-F", "--fuzz", "-B", "-V", "-z", "-Y", "-D"))
        out += [(a, CREATE) for a in ops + ds + [args[i + 1] for i, a in enumerate(args) if a in ("-o", "--output") and i + 1 < len(args)]]
        if not ds:
            out.append((".", CREATE))  # patch edits the files its diff names, relative to the cwd
    elif c in ("sed", "gsed"):
        for a in args:  # the w command and the s///w flag write to a file
            for m in re.finditer(r"(?:^|[;{}\s0-9$,!])w\s+([^\s;}]+)|/w\s*([^\s;}]+)", a):
                out.append((m.group(1) or m.group(2), CREATE))
    elif c in ("awk", "gawk", "mawk", "nawk"):
        for a in args:  # print > "file", print | "cmd", system("cmd")
            out += [(m.group(1), CREATE) for m in re.finditer(r'>>?\s*"([^"]+)"', a)]
            for m in re.finditer(r'(?:\|\s*&?\s*|system\s*\(\s*)"([^"]+)"', a):
                if scan(m.group(1), cwd, depth + 1):
                    out.append((True, CREATE))
    elif c in ("tar", "gtar", "bsdtar"):
        old = args[0] if args and not args[0].startswith("-") else ""
        flags = old + "".join(a[1:] for a in args if re.fullmatch(r"-[A-Za-z]+", a))
        dests = []
        for i, a in enumerate(args):
            if a in ("-C", "--directory") and i + 1 < len(args):
                dests.append(args[i + 1])
            elif a.startswith("--directory="):
                dests.append(a.split("=", 1)[1])
            elif re.fullmatch(r"-[A-Za-z]*C", a) and i + 1 < len(args):
                dests.append(args[i + 1])
            elif a.startswith("-C") and len(a) > 2:
                dests.append(a[2:])
        if "C" in old:
            dests += [a for a in args[1:] if not a.startswith("-")]
        if "x" in flags or "--extract" in args or "--get" in args:
            out += [(d, CREATE) for d in dests] + ([] if dests else [(".", CREATE)])
        if re.search(r"[cru]", flags) or "--create" in args or "--append" in args:  # the archive file itself is written
            out += [(args[i + 1], CREATE) for i, a in enumerate(args) if (a == "--file" or re.fullmatch(r"-[A-Za-z]*f", a)) and i + 1 < len(args)]
            out += [(a.split("=", 1)[1], CREATE) for a in args if a.startswith("--file=")]
            if old and "f" in old and len(args) > 1:
                out.append((args[1], CREATE))
    return out


def scan(cmd, cwd, depth=0):
    if depth > 5:
        return None
    stack = []  # pushd/popd
    for seg in split(cmd.replace(">|", ">")):  # split() cuts at `|`, which would hide the target of a noclobber override `>|`
        t = words(seg)
        name = os.path.basename(t[0]) if t else ""
        if name in ("cd", "pushd"):
            to = [a for a in t[1:] if not a.startswith("-") or a == "-"]
            if name == "pushd":
                stack.append(cwd)
            nc = resolve(to[0], cwd) if to and to[0] != "-" else (HOME if not to and name == "cd" else None)
            cwd = nc or cwd
        elif name == "popd" and stack:
            cwd = stack.pop()
        if (r := judge(seg, cwd, cmd, depth)):
            return r
    return None


GIT_ENV = r"GIT_(?:WORK_TREE|DIR|COMMON_DIR|INDEX_FILE)"
DECLARERS = ("export", "declare", "typeset", "local", "readonly", "read", "mapfile", "readarray")
SHELLS = ("bash", "sh", "zsh", "dash", "ksh", "eval")


def git_env_assignments(cmd, depth=0):
    """(literal NAME=value / NAME+=value words, bare) for the git env names in assignment position. bare is True when a name is
    assigned without a readable value: export/declare/typeset/local/readonly/read/mapfile/readarray NAME, printf -v NAME, for NAME in.
    shlex joins split spellings (G''IT_DIR, "GIT_WORK"_"TREE") first. Text inside bash -c / eval strings is checked too."""
    try:
        lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        toks = cmd.split()
    literal, bare, seg = [], False, []

    def flush():
        nonlocal bare
        if not seg:
            return
        cmd0 = next((os.path.basename(w) for w in seg if "=" not in w and os.path.basename(w) not in ("env", "command", "builtin")), "")
        if cmd0 in DECLARERS and any(re.fullmatch(GIT_ENV, w) for w in seg[1:]):
            bare = True
        if cmd0 == "printf" and any(re.fullmatch(rf"-v({GIT_ENV})?", w) and (w != "-v" or i + 1 < len(seg) and re.fullmatch(GIT_ENV, seg[i + 1]))
                                    for i, w in enumerate(seg)):
            bare = True
        if seg[0] == "for" and len(seg) > 1 and re.fullmatch(GIT_ENV, seg[1]):
            bare = True
        if depth < 4:  # any quoted word with a space or ; may be run by a wrapper (timeout, nohup, xargs, sudo, find -exec)
            for w in seg:
                if re.search(r"=\s*\$?'?GIT_(WORK_TREE|DIR|COMMON_DIR|INDEX_FILE)\b|\$'[^']*GIT_", w):
                    bare = True  # a nameref target (declare -n r=GIT_DIR) or an ANSI-C quoted name
                if re.search(r"\s|;", w):
                    lit, b = git_env_assignments(w, depth + 1)
                    literal.extend(lit)
                    bare = bare or b

    for w in toks:
        if re.fullmatch(r"[;&|()<>]+", w):
            flush()
            seg = []
            continue
        seg.append(w)
        if re.fullmatch(rf"{GIT_ENV}\+?=.*", w, re.S):
            literal.append(w.replace("+=", "=", 1))
    flush()
    return literal, bare


def deny(why):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": why}}))


def blind_mention(cmd, cwd):
    """Used when the guard itself broke: refuse only what could touch a protected place, let everything else through."""
    try:
        return bool(MENTION_RX.search(cmd)) or rp(cwd).startswith(CLAUDE)
    except Exception:
        return True


def main():
    try:
        p = json.loads(sys.stdin.read())
        cmd = p["tool_input"]["command"]
        if not isinstance(cmd, str):
            return
        cwd = p.get("cwd") or os.getcwd()
    except Exception:
        return  # not a payload for this hook: no decision
    try:
        if "\x00" in cmd:  # a NUL byte makes os.path calls raise, and no real command needs one
            return deny("Tamper guard: a command containing a NUL byte is refused; remove it.")
        # The quick exit reads a normalised copy: quotes and backslashes can split a word (`.cl'a'ude`), and a glob,
        # `$` or backtick can build a protected path the raw text never spells (found in review).
        norm = re.sub(r"['\"\\]", "", cmd)
        global MENTION
        # Also count decoded text as a mention: a path built with base64, xxd or \x escapes can hide .claude. A path
        # obfuscated some other way is an accepted gap; refusing every variable write target would block ordinary dev.
        # Only the HOME .claude counts (a project's own .claude folder is not protected): ~/.claude, $HOME/.claude, ${HOME}/.claude,
        # an absolute spelling, a relative .claude when the cwd is the home folder, or a cwd already inside ~/.claude.
        rc = rp(cwd)
        homes = "|".join(re.escape(h) for h in {HOME, rp(HOME)})
        MENTION = bool(re.search(rf"(?:~|\$HOME|\$\{{HOME\}}|{homes})/\.claude", norm, re.I)
                       or (rc == rp(HOME) and re.search(r"(?<![\w./-])\.claude\b", norm, re.I))
                       or rc == CLAUDE or rc.startswith(CLAUDE + "/")
                       or re.search(r"base64\s+(-d|-D|--decode)|xxd\s+-r|\\x[0-9a-fA-F]{2}|\\[0-7]{3}|\$'", cmd))
        # rm/mv always get the full check: removing a parent folder (rm -rf ~/Documents) names no protected path
        if not GATE.search(norm) and not re.search(r"[*?\[{$`]|\b(rm|rmdir|mv|cp|rsync|ditto)\b|--(work-tree|git-dir)\b|\bGIT_(WORK_TREE|DIR|COMMON_DIR|INDEX_FILE)\b", cmd + " " + re.sub(r"[\"'\\]", "", cmd)) and not rp(cwd).startswith((CLAUDE, *EXTRA_CLAUDE)):
            return
        # GIT_WORK_TREE=, GIT_DIR= and friends point git at a folder the same way --work-tree does (parent-folder rule)
        # Fail closed: a value that is not a literal absolute path (relative to some cd or -C, or built by $ ` * {) is refused.
        literal, bare = git_env_assignments(cmd)
        # a name given no value we can read (export NAME, read NAME, printf -v NAME, for NAME in) is refused outright;
        # merely mentioning the name (grep, echo $GIT_DIR, a commit message) is not an assignment and is allowed
        if bare:
            literal = ["GIT_DIR="]
        for w in literal:
            v = os.path.expanduser(w.split("=", 1)[1].rstrip(";&|)"))
            if not v.startswith("/") or re.search(r"[$`*?{\[]", v) or guard_or_parent(v, cwd):
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": FIX}}))
                return
        if not load():
            why = FIX if blind_mention(cmd, cwd) else None
        else:
            why = scan(cmd, cwd)
    except Exception:
        # Never an allow by accident: a crash on a command that could touch a protected place is a deny.
        why = FIX if blind_mention(cmd, cwd) else None
    if why:
        deny(why)


if __name__ == "__main__":
    main()
