#!/usr/bin/env python3
"""Detector for policy-guard.py (fail: open): refuses a heavy command (a full test suite, a build, a
database or Docker stack) that is started without room for it. Reads the hook payload on stdin; prints a PreToolUse deny JSON,
or nothing for "no decision". It never prints "ask".
 (a) inside the folders named by config.json (heavy_scope_roots and lane_dirs, by cwd) a heavy command needs the project's lock wrapper
     (config.json heavy_lock_script) in its text, or the matching lock's owner pid must be an ancestor of this process.
     An empty heavy_lock_script turns rule (a) off. A command run with HEAVY_LOCK=probe in its environment uses the probe lock. WARN-ONLY by default: it logs
     "would deny" to state/heavy-guard/decisions.jsonl and denies only when state/heavy-guard/ENFORCE_LOCK exists or HEAVY_GUARD_ENFORCE=1.
 (b) anywhere, pressure CRITICAL denies a heavy command (unless its text runs the lock wrapper or mem-wait.sh, which wait themselves).
     CRITICAL from low free disk (under 20 GB, or a fast fall) says to run free-disk.py --yes --caches-only, not to wait for memory.
 (e) anywhere, a LONG command (heavy ones, deploys, watches, waits, wrapper scripts, sleep over 30, wait loops) not started with
     run_in_background true is denied: run it again in the background. Off switch: state/heavy-guard/NO_BACKGROUND_RULE.
 (There is no rule c: the letters a, b, e, d keep their names because the cases and the logs cite "rule e".)
 (d) any crash allows and logs the traceback to $HOOKS_STATE/heavy-guard/errors.log.
Heavy is decided by the tool word after the last slash, never by a substring: `echo vitest` and `grep vitest x` are not heavy.
Why: parallel test suites pushed swap past 90 percent and froze the machine; agents took the lock only if they remembered to."""
import json
import os
import re
import importlib.util
import shlex
import shutil
import sys
import time
import traceback

_spec = importlib.util.spec_from_file_location("stash_secret_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stash-secret-guard.py"))
_ssg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ssg)

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
try:  # config.json is read once; a missing or broken file means every project rule is off
    with open(os.environ.get("CLAUDE_HOOKS_CONFIG") or os.path.join(HERE, "config.json")) as _f:
        CFG = json.load(_f)
except Exception:
    CFG = {}
TAKE = CFG.get("heavy_lock_script") or ""  # path of the project's lock wrapper; empty = rule (a) off
LOCK_NAME = os.path.basename(TAKE) or "heavy-lock.sh"
LOCK_DIR = os.environ.get("LOCK_DIR") or os.path.join(HOME, ".claude/hooks/state/locks")
STATE = os.environ.get("HOOKS_STATE") or os.path.join(HOME, ".claude/hooks/state")
SCOPE = [p for p in (os.environ.get("HEAVY_SCOPE_ROOTS", "").split(":") if os.environ.get("HEAVY_SCOPE_ROOTS")
                     else [os.path.expanduser(x) for x in CFG.get("heavy_scope_roots", []) + CFG.get("lane_dirs", [])]) if p]
ENVRX = re.compile(r"^[A-Za-z_]\w*=")
TESTFILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
DBIMG = re.compile(r"(^|/)(postgres|mysql|mariadb|redis)(:|@|$)")
WRAP = {"time", "nice", "nohup", "env", "command", "exec", "caffeinate"}
RUNNERS = {"vitest", "jest", "tsx", "ts-node"}
QUICK = re.compile(r"vitest|jest|tsc|tsx|ts-node|node|npm|npx|docker|cdk|xcodebuild|eas|pg_ctl|postgres|verify|bash|sh\b|zsh|\.bin/")
SEP = {";", "&&", "||", "|", "&", "|&", "\x01"}
TAKE_SUFFIX = "/" + "/".join(TAKE.split("/")[-2:])  # a copy of the wrapper inside a worktree matches by its last two path parts
MEMWAIT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib", "mem-wait.sh")
LEAD = {"(", "{", "$(", "$", "!", "do", "then", "else"}  # group and loop-body openers that hide the command behind them
SID = ""


def peel(toks):
    while toks and toks[0] in LEAD:
        toks = toks[1:]
    return toks


def mask(s):
    """Log hygiene: hide VAR=value assignments, URL credentials and token-like strings before the prefix is stored."""
    s = re.sub(r"\b([A-Za-z_]\w*)=\S+", r"\1=***", s)
    s = re.sub(r"(://[^/\s:@]+):[^@\s]+@", r"\1:***@", s)
    return re.sub(r"[A-Za-z0-9_-]{20,}", "***", s)


def strip_heredocs(cmd):
    """cmd without here-document bodies (they are text, not commands: `cat > doc.md <<'EOF'` then `sleep 100` or `npm test` lines).
    A body is kept when its operator line feeds a shell (`bash <<EOF`, `sh <<'EOF'`, `| sh`): a shell runs it. Quote-aware (a `<<`
    inside quotes is not a here-document) and skips `$((1<<2))` shifts. The operator and the terminator line stay, so nothing
    after the body is hidden. A body that never ends runs to the end of the command, as in bash."""
    out, i, n, stack, pend = [], 0, len(cmd), [], []  # stack: "s" single quote, "d" double quote, "(" command substitution
    while i < n:
        c, top = cmd[i], (stack[-1] if stack else None)
        if c == "\\" and top != "s":
            out.append(cmd[i:i + 2]); i += 2
            continue
        if top == "s":
            if c == "'":
                stack.pop()
        elif top == "d" and c == '"':
            stack.pop()
        elif top != "d" and c == "'":
            stack.append("s")
        elif top != "d" and c == '"':
            stack.append("d")
        elif cmd.startswith("$((", i) or (top != "d" and cmd.startswith("((", i)):
            depth, j = 0, i  # arithmetic: copy to the matching close verbatim
            while j < n:
                depth += (cmd[j] == "(") - (cmd[j] == ")")
                j += 1
                if depth == 0:
                    break
            out.append(cmd[i:j]); i = j
            continue
        elif cmd.startswith("$(", i) and top != "s":
            stack.append("("); out.append("$("); i += 2
            continue
        elif top == "(" and c == ")":
            stack.pop()
        elif top != "d" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and (h := _ssg.heredoc(cmd, i)):
            pend.append((h[1], h[2])); out.append(cmd[i:h[0]]); i = h[0]
            continue
        elif top != "d" and c == "\n" and pend:
            keep = bool(_ssg.SHELL_LINE.search(cmd[cmd.rfind("\n", 0, i) + 1:i]))
            lines, j = [], i + 1
            while pend:
                d, dash = pend.pop(0)
                while j < n:
                    e = cmd.find("\n", j); e = n if e < 0 else e
                    ln = cmd[j:e]; j = e + 1
                    if (ln.lstrip("\t") if dash else ln) == d:
                        break
                    lines.append(ln)
            out.append("\n" + "\n".join(lines) + "\n" if keep else "\n")
            i = j
            continue
        out.append(c); i += 1
    return "".join(out)


def tokens(cmd):
    text = strip_heredocs(cmd).replace("\n", " \x01 ")  # \x01 is a newline separator: a lock taken on an earlier line counts
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        # An unbalanced quote (an apostrophe in `echo it's done` or in a heredoc body) is not a crash: drop the quote and
        # backslash characters and split again, so rules a, b and e still see the commands after it.
        lex = shlex.shlex(re.sub(r"[\"'\\]", " ", text), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)


def lock_before_heavy(cmd, cwd, names, taken=False, depth=0):
    """(taken, bad): `taken` once a segment RUNS one of `names` as its command word (also under bash/sh/zsh and bash -c);
    `bad` if a heavy segment comes before that. Text that only mentions the script (`echo heavy-lock.sh`) does not count."""
    if depth > 3:
        return taken, False
    items = sequence(cmd)
    for k, (seg, sep) in enumerate(items):
        toks = peel(seg)
        skip = False
        while toks and (ENVRX.match(toks[0]) or os.path.basename(toks[0]) in WRAP or toks[0] in LEAD):
            if os.path.basename(toks[0]) == "command" and toks[1:2] in (["-v"], ["-V"]):
                skip = True  # `command -v heavy-lock.sh` looks the script up; it does not run it
                break
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                toks = toks[1:]
        if skip or not toks:
            continue
        tool, args = os.path.basename(toks[0]), [x for x in toks[1:] if x != "--"]
        counts = False
        if tool in names:
            counts = real_lock_script(toks[0], cwd, names, True) and not HELP.intersection(args)
        elif tool in ("bash", "sh", "zsh") and args[:1] == ["-c"] and len(args) > 1:
            t2, bad = lock_before_heavy(args[1], cwd, names, taken, depth + 1)
            if bad:
                return t2, True
            counts = t2 and not taken
        elif tool in ("bash", "sh", "zsh") and [x for x in args if not x.startswith("-")][:1] and \
                os.path.basename([x for x in args if not x.startswith("-")][0]) in names:
            at = next(j for j, x in enumerate(args) if not x.startswith("-"))
            syntax_only = any(re.fullmatch(r"-\w*n\w*", f) for f in args[:at])  # bash -n only parses
            counts = real_lock_script(args[at], cwd, names, False) and not HELP.intersection(args[at + 1:]) and not syntax_only
        elif classify_seg(seg, cwd, depth) and not taken:
            return taken, True
        if counts:
            nxt = items[k + 1][0][:1] if k + 1 < len(items) else []
            after_ok = sep in (None, "&&", "\x01") or (sep == "||" and nxt in (["exit"], ["return"]))  # `|| true` or `;` lets the heavy part run when the lock failed
            before = items[k - 1] if k else None
            before_ok = not before or not (before[1] == "||" or (before[1] == "&&" and os.path.basename(before[0][0]) in ("false", "exit", "return")))
            taken = taken or (after_ok and before_ok)
    return taken, False


HELP = {"--help", "-h", "--version"}


def real_lock_script(path, cwd, names, bare_is_path):
    """The path really is the configured lock wrapper (or a copy of it in a scoped worktree) or this hooks dir's mem-wait.sh, not
    a same-named file elsewhere. A bare command word is looked up on PATH; a bare script argument of bash is relative to cwd."""
    base = os.path.basename(path)
    if base not in names:
        return False
    full = os.path.join(cwd, os.path.expanduser(path)) if ("/" in path or path.startswith("~") or not bare_is_path) else shutil.which(base)
    if not full or not os.path.isfile(full):
        return False
    full = os.path.realpath(full)
    if base == "mem-wait.sh":
        return full == os.path.realpath(MEMWAIT)
    return bool(TAKE) and full == os.path.realpath(TAKE) or (bool(TAKE) and full.endswith(TAKE_SUFFIX) and any(full.startswith(os.path.realpath(r).rstrip("/") + "/") for r in SCOPE))


def sequence(cmd):
    """[(tokens, separator after it)]: separator is ; && || | & or \\x01 (a newline); None for the last."""
    out, cur = [], []
    for t in tokens(cmd):
        if t in SEP:
            out.append((cur, t))
            cur = []
        else:
            cur.append(t)
    return [(s, sep) for s, sep in out + [(cur, None)] if s]


def segments(cmd):
    out, cur = [], []
    for t in tokens(cmd):
        if t in SEP:
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    return [s for s in out + [cur] if s]


def one_test_file(args):
    return sum(bool(TESTFILE.search(a)) for a in args) == 1


def classify(cmd, cwd, depth=0):
    """List of locks the command needs: "heavy" and/or "probe" (empty = light). Skips a script that takes the lock itself."""
    if depth > 3:
        return []
    kinds = []
    for seg in segments(cmd):
        kinds += classify_seg(seg, cwd, depth)
        if len(seg) == 2 and seg[0] == "cd":
            cwd = seg[1] if os.path.isabs(seg[1]) else os.path.join(cwd, seg[1])
    return kinds


def classify_seg(toks, cwd, depth):
    env = {}
    toks = peel(toks)
    while toks:  # peel VAR=x assignments and wrappers (time, nice -n 5, env, ...) off the front
        toks = peel(toks)
        if not toks:
            break
        if ENVRX.match(toks[0]):
            k, v = toks[0].split("=", 1)
            env[k] = v
            toks = toks[1:]
        elif os.path.basename(toks[0]) in WRAP:
            nice_n = toks[0] == "nice" and toks[1:2] == ["-n"]
            toks = toks[3 if nice_n else 1:]
            while toks and toks[0].startswith("-"):
                toks = toks[1:]
        else:
            break
    if not toks:
        return []
    tool, args = os.path.basename(toks[0]), toks[1:]
    lock = "probe" if env.get("HEAVY_LOCK") == "probe" else "heavy"
    if tool in (LOCK_NAME, "mem-wait.sh", "mem-check.sh"):
        return []
    if tool == "cd":
        return []
    if tool == "eval":
        return classify(" ".join(args), cwd, depth + 1)
    if tool == "npx":
        a = [x for x in args if not x.startswith("-")]
        return classify_seg(a, cwd, depth) if a else []
    if tool in RUNNERS or "node_modules/.bin/" in toks[0]:
        return [] if one_test_file(args) else [lock]
    if tool == "tsc":
        return [lock] if "-b" in args or "--build" in args else []
    if tool == "node":
        return [lock] if "--test" in args and not one_test_file(args) else []
    if tool in ("verify", "verify.sh"):
        return [lock]
    if tool in ("xcodebuild",) or (tool == "eas" and "build" in args and "--local" in args):
        return [lock]
    if tool == "cdk":
        return [lock] if "synth" in args or "synthesize" in args else []
    if tool == "pg_ctl":
        return [lock] if "start" in args else []
    if tool == "postgres":
        return [lock] if "-D" in args else []
    if tool == "docker-compose":
        return [lock] if "up" in args else []
    if tool == "docker":
        if args[:1] == ["compose"]:
            return [lock] if "up" in args else []
        if args[:1] == ["run"]:
            return [lock] if any(DBIMG.search(a) for a in args[1:]) else []
        return []
    if tool == "npm":
        return classify_npm(args, cwd, depth, lock)
    if tool in ("bash", "sh", "zsh"):
        a = [x for x in args if x != "--"]
        if a[:1] == ["-c"] and len(a) > 1:
            return classify(a[1], cwd, depth + 1)
        a = [x for x in a if not x.startswith("-")]
        return classify_script(a[0], cwd, depth, lock) if a else []
    return []


def classify_script(path, cwd, depth, lock):
    full = path if os.path.isabs(path) else os.path.join(cwd, path)
    try:
        with open(full, errors="replace") as f:
            lines = [l for _, l in zip(range(200), f)]
    except OSError:
        return []
    text = "".join(lines)
    if LOCK_NAME in text:
        return []  # the script takes the lock itself
    kinds = []
    for l in lines:
        if l.strip() and not l.lstrip().startswith("#"):
            try:
                kinds += classify(l, os.path.dirname(full), depth + 1)
            except ValueError:
                pass
    return kinds


def classify_npm(args, cwd, depth, lock):
    prefix, rest, i = cwd, [], 0
    while i < len(args):
        a = args[i]
        if a == "--prefix" and i + 1 < len(args):
            prefix = args[i + 1] if os.path.isabs(args[i + 1]) else os.path.join(cwd, args[i + 1])
            i += 1
        elif a.startswith("--prefix="):
            prefix = a.split("=", 1)[1]
            prefix = prefix if os.path.isabs(prefix) else os.path.join(cwd, prefix)
        elif a.startswith("-") and not rest:
            pass
        else:
            rest.append(a)
        i += 1
    if not rest:
        return []
    sub, more = rest[0], rest[1:]
    if sub in ("test", "t", "tst"):
        return [] if one_test_file(more) else [lock]
    if sub == "ci":
        return [lock]
    if sub in ("run", "run-script") and more:
        name, extra = more[0], more[1:]
        if name in ("build", "verify", "test"):
            return [] if one_test_file(extra) else [lock]
        try:
            with open(os.path.join(prefix, "package.json")) as f:
                text = json.load(f)["scripts"][name]
        except Exception:
            return []
        return classify(text + " " + " ".join(extra), prefix, depth + 1)
    return []


def ancestors():
    pids, pid = set(), os.getpid()
    import subprocess
    for _ in range(40):
        try:
            pid = int(subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=1).stdout)
        except Exception:
            break
        if pid <= 1:
            break
        pids.add(pid)
    return pids


def owner_pid(lock):
    try:
        with open(os.path.join(LOCK_DIR, lock, "owner")) as f:
            return int(f.read().split()[1])  # "<name> <pid> <time> <what> <lock>"
    except Exception:
        return None


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def secs(s):
    """sleep operand in seconds: 90, 1.5m, 1e3, infinity. Anything else counts as 0."""
    unit = s[-1] if len(s) > 1 and s[-1] in "smhd" else ""
    try:
        return float(s[:-1] if unit else s) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    except ValueError:
        return 0


def long_seg(toks, cwd, depth):
    while toks:
        toks = peel(toks)
        if not toks:
            break
        if ENVRX.match(toks[0]):
            toks = toks[1:]
        elif os.path.basename(toks[0]) in WRAP or toks[0] == "npx":
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                toks = toks[1:]
        else:
            break
    if not toks:
        return False
    tool, args = os.path.basename(toks[0]), toks[1:]
    if tool in ("until", "while", "for"):
        return True  # the caller only passes a loop whose body sleeps
    if tool == "eval":
        return long_cmd(" ".join(args), cwd, depth + 1)
    if tool == "sleep":
        return bool(args) and secs(args[0]) > 30
    if tool == "cdk":
        return "deploy" in args
    if tool == "terraform":
        return "apply" in args
    if tool == "docker":
        return "build" in args[:2]
    if tool == "gh":
        return args[:2] == ["run", "watch"] or (args[:2] == ["pr", "checks"] and "--watch" in args)
    if tool == "aws":
        return "wait" in args
    if tool == "npm":
        a = [x for x in args if not x.startswith("-")]
        return a[:1] in (["run"], ["run-script"]) and len(a) > 1 and a[1].startswith("deploy")
    if tool in ("bash", "sh", "zsh") or tool.endswith(".sh"):
        a = [x for x in args if x != "--"]
        if tool in ("bash", "sh", "zsh"):
            if a[:1] == ["-c"] and len(a) > 1:
                return long_cmd(a[1], cwd, depth + 1)
            a = [x for x in a if not x.startswith("-")]
            path = a[0] if a else ""
        else:
            path = toks[0]
        if not path:
            return False
        full = path if os.path.isabs(path) else os.path.join(cwd, path)
        try:
            with open(full, errors="replace") as f:
                text = "".join(l for _, l in zip(range(200), f))
        except OSError:
            return False
        # a lock wrapper takes the lock itself (right for rule a) but still runs for minutes
        return bool(re.search(re.escape(LOCK_NAME), text))
    return False


def long_cmd(cmd, cwd, depth=0):
    """True if the command takes a while. Light things (one test file, tsc --noEmit, lint, git, gh pr view) are not long."""
    if depth > 3:
        return False
    if classify(cmd, cwd):
        return True
    total = 0
    loops = []  # open loops: [kind, item count or None, sum of body sleeps, longest body sleep]
    for seg in segments(cmd):
        seg = peel(seg)
        if not seg:
            continue
        if seg[0] in ("until", "while", "for"):
            # `$(ls); do` lexes as one segment: split the header from the body at the first `do`
            cut = seg.index("do") if "do" in seg else len(seg)
            loops.append([seg[0], item_count(seg[:cut]) if seg[0] == "for" else None, 0, 0])
            seg = peel(seg[cut + 1:])
            if not seg:
                continue
        if seg[0] == "done" and loops:
            if loop_long(loops.pop()):
                return True
            continue
        if long_seg(seg, cwd, depth):
            return True
        if os.path.basename(seg[0]) == "sleep" and len(seg) > 1:
            if loops:
                loops[-1][2] += secs(seg[1])
                loops[-1][3] = max(loops[-1][3], secs(seg[1]))
            else:
                total += secs(seg[1])  # `sleep 20; sleep 20` waits as long as `sleep 40`
    return total > 30 or any(loop_long(l) for l in loops)


def item_count(seg):
    """Items of `for x in a b c` or `{1..40}` when the list is literal, else None."""
    if "in" not in seg:
        return None
    items = seg[seg.index("in") + 1:]
    n = 0
    for it in items:
        r = re.fullmatch(r"\{(\d+)\.\.(\d+)\}", it)
        if r:
            n += abs(int(r.group(2)) - int(r.group(1))) + 1
        elif re.search(r"[$`(){}*?\[]", it):
            return None
        else:
            n += 1
    return n


def loop_long(l):
    kind, count, total, longest = l
    if kind != "for":
        return total > 0  # a wait loop has no known end: any sleep in it is a poll
    return count * total > 30 if count is not None else longest > 5


def rule_e(d, cmd, cwd):
    if (d.get("tool_input") or {}).get("run_in_background") is True:
        return
    if os.path.exists(f"{STATE}/heavy-guard/NO_BACKGROUND_RULE"):
        return
    if long_cmd(cmd, cwd):
        deny("policy: this command takes a while; run the same command again with run_in_background: true. You are notified when "
             "it ends, so do not poll, sleep or tail it; do other work meanwhile. Do not respell the command and do not ask the user.")


def decide(cmd, cwd):
    """Rules (a) and (b). Returns True when it printed a deny."""
    if not QUICK.search(cmd):
        return
    kinds = classify(cmd, cwd)
    if not kinds:
        return
    if os.environ.get("HEAVY_GUARD_CRASH"):
        raise RuntimeError("injected crash")
    real = os.path.realpath(cwd) if os.path.exists(cwd) else cwd
    in_scope = any(real == r or real.startswith(r.rstrip("/") + "/") or cwd.startswith(r.rstrip("/") + "/") or cwd == r for r in SCOPE)
    if TAKE and in_scope:
        anc = None
        for lock in sorted(set(kinds)):
            taken, bad = lock_before_heavy(cmd, cwd, (LOCK_NAME,))
            if taken and not bad:
                continue
            if anc is None:
                anc = ancestors()
            if owner_pid(lock) not in anc:
                # Warn-only until the logs have been reviewed: log the would-be deny and let the command run.
                # Enforce with HEAVY_GUARD_ENFORCE=1 or the flag file state/heavy-guard/ENFORCE_LOCK.
                if not (os.environ.get("HEAVY_GUARD_ENFORCE") == "1" or os.path.exists(f"{STATE}/heavy-guard/ENFORCE_LOCK")):
                    try:
                        os.makedirs(f"{STATE}/heavy-guard", exist_ok=True)
                        with open(f"{STATE}/heavy-guard/decisions.jsonl", "a") as f:
                            f.write(json.dumps({"t": int(time.time()), "would": "deny", "lock": lock, "cwd": cwd, "session_id": SID, "cmd": mask(cmd)[:80]}) + "\n")
                    except Exception:
                        pass
                    continue
                env = "HEAVY_LOCK=probe " if lock == "probe" else ""
                # The lock holder must be the script that runs the suite (the wrapper records its caller's pid), so both go in one script.
                deny(f"policy: this {lock} command runs only under the {lock} lock. Put it in a script that first runs "
                     f"`{env}bash {TAKE} <name> <what> || exit 3`, then the command, then releases the lock, and run that "
                     f"script; do not respell the command, and do not ask the user.")
                return True
    taken, bad = lock_before_heavy(cmd, cwd, (LOCK_NAME, "mem-wait.sh"))
    if "heavy" in kinds and not (taken and not bad):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
        import pressure
        st = pressure.status()
        if st["level"] == "CRITICAL":
            # mem-check is also CRITICAL when free disk is under disk_block_gb or fell fast; waiting never frees disk, so say what does.
            m = re.search(r"\bdisk=(\d+)G", st["line"])
            try:
                block = int(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib", "limits.json")))["disk_block_gb"])
            except Exception:
                block = 20
            if " fall=" in st["line"] or (m and int(m.group(1)) < block):
                deny(f"free disk is under {block} GB: run `python3 ~/.claude/hooks/lib/free-disk.py --yes --caches-only` in the background, "
                     f"check `df -g /`, then retry once; if still under {block} GB stop and tell the user. Now: {st['line']}")
                return True
            deny(f"memory is critical: run it through {LOCK_NAME} (it waits for room), or wait with ~/.claude/hooks/lib/mem-wait.sh "
                 f"in the background, then retry once; do not respell. Now: {st['line']}")
            return True


def main():
    global SID
    try:
        d = json.load(sys.stdin)
        SID = str(d.get("session_id") or "")
        cmd, cwd = (d.get("tool_input") or {}).get("command", "") or "", d.get("cwd") or os.getcwd()
        if not decide(cmd, cwd):
            rule_e(d, cmd, cwd)
    except Exception:
        try:
            os.makedirs(f"{STATE}/heavy-guard", exist_ok=True)
            with open(f"{STATE}/heavy-guard/errors.log", "a") as f:
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass


main()
