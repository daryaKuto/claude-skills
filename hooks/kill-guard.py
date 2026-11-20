#!/usr/bin/env python3
"""PreToolUse hook (Bash): refuses broad process kills from Claude Code and every subagent.

Why: a review agent once ran `pkill -f 'sleep 60$' -P 1` to clean up its own test process.
macOS pkill reads options only before the first pattern, so "-P" and "1" became patterns, and "1"
matched every command line containing the digit 1: SIGTERM hit 159 of the user's processes
(Chrome, Claude, Codex, Cursor, Spotify, Adobe, VS Code, Finder). Agents must stop only the pids
they started: `kill <pid>`, or `kill -TERM -- -<pgid>` for a group they started in its own session.
Exit code 2 blocks the call and shows the reason to the agent.
"""
import json
import os
import re
import shlex
import sys

RULES = [
    (re.compile(r"\b(process\.kill|os\.kill|os\.killpg)\(\s*(-1|0)\s*[,)]"),
     "process.kill / os.kill with -1 or 0 signals every process of the user or the whole group."),
]

PKILL_WHY = "pkill and killall are blocked: they match by name, and one misordered option killed 159 of the user's apps."
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SEPS = {";", "&", "&&", "|", "||"}
DATA_ONLY = {"grep", "egrep", "fgrep", "echo", "printf", "cat", "head", "tail", "wc", "jq", "ls", "which", "type"}
# pkill as a command inside one token: after a space, shell punctuation, `=` or a short-option letter run (-Opkill),
# and followed by the end, a space or a separator. File and branch names (pkill-notes.md, fix/pkill-guard, /pkill/p) do not match.
PKILL_IN_TOKEN = re.compile(r"(?<![\w.*-])(pkill|killall)(?![\w./*-])|^-[A-Za-z]*(pkill|killall)(?![\w./*-])")
GIT_TEXT = {"commit", "log", "show", "diff", "status", "blame", "grep", "tag"}
GIT_SAFE_LONG = {"--", "--oneline", "--stat", "--name-only", "--name-status", "--cached", "--staged", "--all", "--no-edit", "--amend",
                 "--message", "--allow-empty", "--porcelain", "--short", "--graph", "--decorate", "--follow", "--patch", "--grep",
                 "--format", "--pretty", "--since", "--until", "--author", "--count", "--line-number", "--ignore-case",
                 "--no-verify", "--signoff", "--no-gpg-sign", "--max-count", "--no-merges", "--regexp-ignore-case", "--date",
                 "--no-color", "--unified"}
GH_TEXT = {("pr", "create"), ("pr", "comment"), ("pr", "edit"), ("pr", "view"), ("issue", "create"), ("issue", "comment"), ("issue", "view")}


def text_only(body):
    """Allowlist of git, gh, rg and man shapes that only take text. Anything else (git rebase -x, gh alias set --shell,
    rg --pre, man -P) gets the pkill scan."""
    cmd, rest = os.path.basename(body[0]), body[1:]
    if cmd == "git":
        # git takes any unique prefix of a long option (--open = --open-files-in-pager), so long options must be on an exact list
        return bool(rest) and rest[0] in GIT_TEXT and not any(
            (x.startswith("--") and x.split("=", 1)[0] not in GIT_SAFE_LONG) or re.fullmatch(r"-[a-zA-Z0-9]*[OcC].*", x) for x in rest[1:])
    if cmd == "gh":
        return tuple(rest[:2]) in GH_TEXT
    if cmd == "rg":
        return not any(x.startswith(("--pre", "--search-zip")) or re.fullmatch(r"-[a-zA-Z]*z[a-zA-Z]*", x) for x in rest)
    if cmd == "man":
        return all(not x.startswith("-") for x in rest)
    return False


def pkill_word(t):
    """True when pkill/killall is a command word, not only mentioned (grep -n pkill notes.txt, git commit -m '...pkill...').
    A segment containing a wrapper (sudo -u x pkill, xargs pkill, find -exec pkill) counts any pkill word in it."""
    seg = []
    for w in t + [";"]:
        if w not in SEPS and w not in ("(", ")", "{", "}", "!"):
            seg.append(w.lstrip("`"))
            continue
        body = seg
        while body and re.fullmatch(r"\w+=.*", body[0]):
            body = body[1:]
        # Fail closed: any pkill word counts unless the segment starts with a command that only reads or prints text
        # (a list of launchers to catch, like timeout, watch, if, while, would always miss one).
        if body and os.path.basename(body[0]) in DATA_ONLY:
            body = []
        elif body and body is seg and text_only(body):  # a VAR=x prefix (GIT_EXTERNAL_DIFF, GIT_PAGER) can run a command
            body = []  # git commit -m '...pkill...' is text; git rebase -x, rg --pre, gh alias --shell, man -P run commands
        # a word inside one quoted token counts too: git rebase -x 'pkill node', less +'!pkill node'
        # glued forms too: git grep -Opkill, GIT_EXTERNAL_DIFF=pkill (only over-blocks a word like "unpkill" outside text-only commands)
        if any(PKILL_IN_TOKEN.search(x) for x in seg if body):
            return True
        seg = []
    return False


def plain_text(cmd):
    """One simple command that only reads or prints text: no shell operators, substitutions or redirects, balanced quotes."""
    if re.search(r"[;&<>\n`]|\$\(|\|\||\|&", cmd):
        return False
    try:  # a plain pipe is fine when every stage is text only (git show x | grep pkill); echo pkill | sh is not
        parts = [shlex.split(p) for p in cmd.split("|")]
    except ValueError:
        return False
    return all(t and (os.path.basename(t[0]) in DATA_ONLY or text_only(t)) for t in parts)


def tokens(cmd):
    """shlex unquotes quotes and backslashes, so a quoted '-1', `p\\kill` and pk''ill read as plain words."""
    try:
        lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = False
        return list(lex)
    except ValueError:  # unbalanced quote: plain split with quotes stripped, still deny-biased
        return re.sub(r"['\"\\]", "", cmd).split()


def broad_kill(t):
    """Reason if a shell `kill` targets pid 0 (whole group) or -1 (every process), or a target we cannot
    read ($(...), ${...}, backtick, $VAR could be 0 or -1). Options come first: -SIG, -<num>, -s/-n <sig>.
    After `--` everything is a target, so `-- -1` is a pid, but `-1 12345` is signal 1 to one pid (allowed).
    A literal positive pid stays allowed."""
    for n, w in enumerate(t):
        if w.rsplit("/", 1)[-1] != "kill":  # /bin/kill and /usr/bin/kill too (regression found in review loop 2)
            continue
        k = n  # kill run by xargs gets its pids from another command: they cannot be read here
        while k > 0 and t[k - 1] not in SEPS:
            k -= 1
            if t[k] == "xargs":
                return "kill run by xargs takes pids from another command (pgrep ... | xargs kill) and could hit more than you started."
        a = []
        for x in t[n + 1:]:
            if x in SEPS:
                break
            a.append(x)
        if any("$" in x or "`" in x for x in a):
            return "a kill target is built by the shell ($, ${}, $(), backtick) and could be 0 or -1; write the literal pid."
        if a == ["-1"]:  # a lone -1 is a usage error today, but some kill builtins read it as the target
            return "kill -1 signals every process of the user."
        i = 0
        if i < len(a) and a[i].startswith("-") and a[i] != "--":
            i += 2 if a[i] in ("-s", "-n") else 1
        targets = a[i + 1:] if i < len(a) and a[i] == "--" else a[i:]
        if any(re.fullmatch(r"\s*[-+]?\d+\s*", x) and int(x.strip()) in (0, -1) for x in targets):  # bash reads " -1" and "00" as pids
            return "kill -1 or kill 0 signals every process of the user or the whole group."
    return None


KILL_WORD = re.compile(r"(?<![\w.])((?:Process\.|os\.|process\.)?)kill\b(?!all)")  # Node's process.kill takes the pid first, like os.kill
KILL_ARGS = re.compile(r"--|-?\w+")
RAW_KILL_WHY = "a kill of 0 or -1 (every process of the user or the whole group) was found inside quotes or another language."


def raw_broad_kill(cmd):
    """Raw-text scan for kill 0 / kill -1 hidden in quotes or code: trap 'kill -1', perl -e 'kill 9, -1', Process.kill(9,-1),
    subprocess.run(['kill','-1']), ssh h 'kill -1'. Same reading as broad_kill: options first, then targets. os.kill(pid, 0) is the
    ordinary liveness probe, so call forms only look at the pid argument (os.kill: first, Process.kill: second) or any -1."""
    for m in KILL_WORD.finditer(cmd):
        rest = cmd[m.end():m.end() + 80]
        a = KILL_ARGS.findall(re.split(r"[;|&\n]", rest)[0])[:6]
        if rest.startswith("("):  # code call
            pid = a[1:2] if m.group(1) == "Process." else a[:1]
            if "-1" in a[:2] or any(re.fullmatch(r"-?0+", x) for x in pid):
                return RAW_KILL_WHY
            continue
        i = 0
        if a and a[0].startswith("-") and a[0] != "--":
            i = 2 if a[0] in ("-s", "-n") else 1
        targets = a[i + 1:] if a[i:i + 1] == ["--"] else a[i:]
        # a leading -1 is signal 1 only when a literal pid follows (trap 'kill -1' EXIT has none)
        if (a[:1] == ["-1"] and not (len(a) > 1 and a[1].isdigit())) or any(re.fullmatch(r"-?0+|-1", x) and x != "-0" for x in targets):
            return RAW_KILL_WHY
    return None


def check(cmd, depth=0):
    for pattern, why in RULES:
        if pattern.search(cmd):
            return why
    if "kill" in cmd and not plain_text(cmd):
        why = raw_broad_kill(cmd)
        if why:
            return why
    # Fail closed on the raw text: a pkill word anywhere denies unless the whole command is one plain text command
    # (grep -n pkill notes.txt, git commit -m '...pkill...'). Pipes, ;, &, redirects, newlines, $( ) and backticks
    # void the exemption: echo "$(pkill x)", echo it's; pkill x, echo pkill x | sh all ran pkill past the token pass.
    if PKILL_IN_TOKEN.search(cmd) and not plain_text(cmd):
        return PKILL_WHY
    t = tokens(cmd)
    if pkill_word(t):
        return PKILL_WHY
    seg = []  # pids fanned out by xargs or parallel, also inside sh -c "kill {}"
    for w in t + [";"]:
        if w not in SEPS:
            seg.append(w)
            continue
        if any(os.path.basename(x) in ("xargs", "parallel") for x in seg) and any(re.search(r"(^|[\s/;&|(])kill($|\s)", x) for x in seg):
            return "kill run by xargs or parallel takes pids from another command (pgrep ... | xargs kill) and could hit more than you started; kill the literal pid you recorded."
        seg = []
    why = broad_kill(t)
    if why or depth > 3:
        return why
    for n, w in enumerate(t):  # bash -c '<inner>': scan the inner string too
        if w == "eval" and n + 1 < len(t):
            why = check(" ".join(t[n + 1:]), depth + 1)
            if why:
                return why
        if os.path.basename(w) in SHELLS:
            for j in range(n + 1, min(n + 4, len(t) - 1)):
                if re.fullmatch(r"-[a-z]*c[a-z]*", t[j]):
                    why = check(t[j + 1], depth + 1)
                    if why:
                        return why
    return None


try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)
if not isinstance(cmd, str):  # null, list or int: nothing to judge
    sys.exit(0)

# Hooks time out at 5 s and the scan is slow on huge text (1 MB took 7.7 s): refuse a big command that could hold a kill.
if len(cmd) > 10_000 and re.search(r"(?:(?<![A-Za-z])|(?<=p))k\W*i\W*l\W*l(?:(?![A-Za-z])|(?=all))", cmd):  # kill, pkill, killall (split forms like k''ill count), not skill or skills; the token passes are quadratic in the number of kill words: 200 KB of them ran for minutes
    why = "the command is over 10 KB and mentions kill, too big to check in the hook time limit; put it in a script file and run the file."
else:
    why = check(cmd)
if why:
    print(f"Blocked by ~/.claude/hooks/kill-guard.py: {why} "
          "Stop only pids you recorded when you started them: `kill <pid>`, or `kill -TERM -- -<pgid>` "
          "for a process group you started yourself (setsid or detached). Use pgrep only to look.",
          file=sys.stderr)
    sys.exit(2)
sys.exit(0)
