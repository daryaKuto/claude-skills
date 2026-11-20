#!/usr/bin/env python3
"""PreToolUse hook (Bash): denies every `git stash` form and every command that would print a secret.
Same contract as push-guard.py: payload JSON on stdin; prints a deny decision, or nothing for "no decision". Never raises.

Stash: stashes are shared across worktrees, so one agent's pop takes another's work (a hard rule: never git stash).
Secrets: a reader (cat, head, grep, ...) on .env*, *.pem, *.key, *.p12, id_rsa*, ~/.aws/credentials, ~/.netrc,
~/.git-credentials; printenv; bare env; export -p; bare set; keychain reads with -w/-g; aws configure get of a key; gh auth token.

The command is split on ; & | newline ( ) and backticks outside single quotes, then each segment is read with shlex.
`bash -c '...'`, `sh -c`, `eval`, `$(...)` are scanned again. Prefix words (env, command, exec, sudo, nohup, time, a leading
backslash, VAR=x) are stripped first. A quote trick shlex cannot read makes the text unreadable: a segment that mentions
stash or a secret word is then denied, anything else passes.
"""
import fnmatch
import itertools
import json
import os
import re
import shlex
import sys

STASH_FIX = "Stash guard: git stash is never allowed (stashes are shared across worktrees). Commit work in progress to a branch (git switch -c wip/<name>; git commit). Do not respell it."
SECRET_FIX = "Secret guard: this would print a secret. To learn which variables a .env file defines, run python3 ~/.claude/hooks/lib/env-keys.py <file> (names only; values are never printed). Read only non-secret files (.env.example is fine). Do not respell it."
ENV_FIX = "Secret guard: this would print the values of environment variables, secrets included. To list variable names only, run python3 ~/.claude/hooks/lib/env-keys.py <env file> (values are never printed); to check one variable is set, run [ -n \"$NAME\" ] && echo set. Do not respell it."
GIT_C_FIX = "Git guard: git's -c and --config-env global options, GIT_CONFIG_* variables, and writes to alias.*, include.path and includeIf.* are not allowed (they can define an alias that runs git stash). Drop the option or variable; for a new branch use git switch -c <name> after the subcommand."
GIT_ENV = re.compile(r"GIT_CONFIG(_COUNT|_KEY_\w+|_VALUE_\w+|_PARAMETERS|_GLOBAL|_SYSTEM|_NOSYSTEM)?=")
GIT_CFG_KEY = re.compile(r"(alias|include|includeif)(\.|$)", re.I)
GIT_CFG_VERBS = {"set", "unset", "get", "list", "edit", "rename-section", "remove-section"}
GIT_CFG_READ = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "--unset", "--unset-all", "--show-origin", "--get-color", "--get-colorbool"}
GIT_CFG_FILE = {"-f", "--file", "--blob", "--type", "--comment", "--value", "--default", "--url"}
INTERP = re.compile(r"(python[\d.]*|node(?:js)?|ruby|perl)")
STR_LIT = re.compile(r"""(['"`])(.*?)\1""", re.S)
PS_VALUE_OPTS = {"-o", "-p", "-t", "-u", "-U", "-G", "-g", "-C", "-O", "-n", "-N", "-M"}
READERS = {"cat", "head", "tail", "less", "more", "bat", "grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk", "cp", "base64"}
PREFIX = {"command", "exec", "sudo", "nohup", "time", "builtin", "nice"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SAFE_ENV_SUFFIX = (".example", ".sample", ".template")
GIT_OPT_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SEP = set(";&|\n()`")
# Tools that never print a file's content; they may name a secret path (ls .env, test -f .env, touch, chmod, git add .env).
ENV_KEYS = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib", "env-keys.py"))
# commands that never print a file's content (wc prints only counts)
NO_PRINT = {"ls", "test", "[", "[[", "stat", "file", "wc", "touch", "chmod", "chown", "rm", "echo", "printf", "cd", "basename", "dirname"}
GIT_NO_PRINT = {"status", "add", "rm", "mv", "ls-files", "check-ignore", "commit", "restore", "reset"}
GIT_DIFF_NAMES = {"--stat", "--name-only", "--name-status", "--shortstat", "--numstat", "-q", "--quiet"}
# Flags that make git print file content: diff -p/-u/-U<n>/--no-index/--exit-code (it also prints the patch); status/add/commit -v/-p.
GIT_DIFF_PRINT = re.compile(r"--no-index|--patch|--exit-code|-\w*[puU]\w*")
GIT_VERBOSE_PRINT = re.compile(r"--patch|-\w*[vp]\w*")
# Words that are the value of an option that only names a path to skip or load, never to print.
SKIP_VALUE = {"--exclude", "--exclude-from", "--ignore"}
CRASH_DANGER = re.compile(r"stash|printenv|find-generic-password|find-internet-password|auth\s+token|\.env|\.aws/credentials|\.git-credentials|\.netrc")
# git subcommands that may name a secret path only with these options (-m's value is a message, not a path).
GIT_PLAIN_OPTS = {"-A", "--all", "--", "-m", "-q", "--quiet", "-s", "--short", "--porcelain", "-b"}
GIT_PLAIN_SUBS = {"status", "add", "commit", "restore", "reset", "rm", "mv"}
GIT_DIFF_OK = GIT_DIFF_NAMES | {"--cached", "--staged", "--"}
DOCKER_UP_SUBS = {"up", "down", "build", "pull", "stop", "restart", "ps"}
DOCKER_VALUE_OPTS = {"--env-file", "-f", "--file", "-p", "--project-name", "--profile", "--project-directory", "--ansi", "--parallel"}
SHELL_LINE =re.compile(r"(?:^|[|;&(])\s*(?:\w+=\S*\s+|(?:sudo|env|command|exec|nohup|time)\s+)*(?:\S*/)?(?:bash|sh|zsh|dash|ksh)(?=\s|$)")
# Tools whose last positional word is the destination: only the sources can be printed (mv also moves a secret away).
COPIERS = {"cp", "rsync", "install", "ditto", "mv"}
# Option whose value names an env file the program loads for itself (not printed); never for a reader or a container run.
ENV_OPTS = {"--env", "--env-file", "--dotenv", "--envfile", "--env-path", "--dotenv-path"}
HOMES = ("HOME", "XDG_CONFIG_HOME")
# Interpreter code (python -c, node -e ...) that prints the whole environment; one key (os.environ.get, process.env.X) is fine.
ENV_DUMP = {"python": re.compile(r"\benvironb?\b(?!\s*(?:\.(?:get|setdefault|pop)\b|\[))"),
            "node": re.compile(r"process\.env\b(?!\s*(?:\.\w|\[))|process\s*\[\s*['\"`]env['\"`]\s*\](?!\s*(?:\.\w|\[))"
                               r"|\{[^}]*\benv\b[^}]*\}\s*(?:=\s*process\b(?!\s*\.)|from\s*['\"](?:node:)?process['\"])"
                               r"|require\(\s*['\"](?:node:)?process['\"]\s*\)\s*\.env\b(?!\s*(?:\.\w|\[))"),
            "ruby": re.compile(r"\bENV\b(?!\s*(?:\[|\.fetch\b|\.key\?))"),
            "perl": re.compile(r"%ENV\b"),
            # awk: only ENVIRON["LITERAL"] reads one variable; `in ENVIRON`, ENVIRON[k] and a bare ENVIRON walk them all
            "awk": re.compile(r"\bENVIRON\b(?!\s*\[\s*\"[^\"]*\"\s*\])")}
HOME_FIX = "Git guard: changing HOME or XDG_CONFIG_HOME points git at another config (it could define a stash alias); use the real HOME, or set the one variable your tool needs."
AWS_CWD = [False]  # set by a cd whose target the guard cannot resolve ($ or backtick): a bare `credentials` or `config` word may then be the AWS secret file
try:
    CWD = [os.getcwd()]  # tracked working directory: the payload cwd, moved by each literal cd
except OSError:
    CWD = ["/"]
START_CWD = [CWD[0]]
AWS_DIR = os.path.realpath(os.path.expanduser("~/.aws"))
# Programs that read their own --env/--env-file value (a config they load, not print). Anything else judges the value as a path.
ENV_LOADERS = {"npx", "tsx", "vite", "vitest", "next", "node", "nodejs", "npm", "pnpm", "yarn"}  # not dotenv: `dotenv -p` / `dotenv list` print values
PATTERN_CMDS = {"grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk"}
# only options that take a value (not -F, -v, -T, which are flags and would hide a file operand after them)
PATTERN_VALUE_OPTS = {"-m", "-A", "-B", "-C", "-g", "-t", "-j", "--include", "--exclude", "--exclude-dir", "--max-count", "--context", "--glob", "--type"}
# Interpreter code that starts the shell commands env, printenv or set through a runner (subprocess, system, exec, child_process).
RUNNER = re.compile(r"subprocess|os\.(?:system|popen|exec\w*|spawn\w*)|child_process|\b(?:exec\w*|spawn\w*|system|popen|Popen)\s*\(|%x|`")
ENV_CMD_STR = re.compile(r"""['"`]\s*(?:\S*/)?(?:env|set)\s*(?:[|;&>][^'"`]*)?['"`]|['"`]\s*(?:\S*/)?printenv\b[^'"`]*['"`]""")
GLOB_NAMES = [".env", ".env.local", ".env.production", ".envrc", "a.pem", "a.key", "a.p12", "id_rsa", "id_ed25519",
              ".netrc", ".git-credentials", ".npmrc", ".pypirc"]


def heredoc(cmd, i):
    """Parse a here-document operator at cmd[i] ("<<"). Returns (end, delimiter, dash), or None when the delimiter word
    cannot be resolved (empty, or holds $ or a backtick): the caller then treats the following lines as plain commands.
    Bash rule: the word runs to the next unquoted blank or ;|&<>(), then quote removal."""
    n, j, dash = len(cmd), i + 2, False
    if cmd.startswith("-", j):
        dash, j = True, j + 1
    while j < n and cmd[j] in " \t":
        j += 1
    word, start = [], j
    while j < n and cmd[j] not in " \t\n;|&<>()":
        c = cmd[j]
        if c == "'":
            e = cmd.find("'", j + 1)
            if e < 0:
                return None
            word.append(cmd[j + 1:e]); j = e + 1
        elif c == '"':
            j += 1
            while j < n and cmd[j] != '"':
                if cmd[j] in "$`":
                    return None
                if cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '$`"\\':
                    j += 1
                word.append(cmd[j]); j += 1
            if j >= n:
                return None
            j += 1
        elif c == "\\":
            if j + 1 >= n or cmd[j + 1] == "\n":
                return None
            word.append(cmd[j + 1]); j += 2
        elif c in "$`":
            return None
        else:
            word.append(c); j += 1
    d = "".join(word)
    return (j, d, dash) if d and j > start else None


def split(cmd):
    """Segments of cmd, quote-aware; $( and backticks open a new segment, so their content is scanned too.
    A here-document body comes back as one segment starting with \\0 (scan() reads it in body mode)."""
    out, cur, q, i = [], [], None, 0
    arith, skip = 0, 0
    pend = []  # (delimiter, dash) of here-documents opened on the current line
    while i < len(cmd):
        c = cmd[i]
        # Comments are NOT skipped: three attempts to tell a real comment from a `#` inside a word, ${...} or after a
        # subshell were each bypassable (found in review). Scanning comment text as code can only over-block.
        # Arithmetic context: entered on an unquoted $(( or a command-initial ((, left on the matching )). Only quotes
        # and comments are ignored by construction (quoted parens never count), so only here is << a shift.
        # Any unquoted (( opens arithmetic (after for, if, while, !, { or ; too): bash reads (( nowhere else
        # (found in review: `for ((i=1<<2; ...))` was parsed as a here-document).
        if q is None and arith == 0 and (cmd.startswith("$((", i) or cmd.startswith("((", i)):
            arith, skip = 2, i + (3 if c == "$" else 2)
        elif q is None and arith and i >= skip and c in "()":
            arith += 1 if c == "(" else -1
        if q is None and arith and cmd.startswith("<<", i):
            cur.append("<<"); i += 2  # a shift inside $((...)) or ((...)), not a here-document
            continue
        if q is None and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and (h := heredoc(cmd, i)):
            pend.append((h[1], h[2])); cur.append(cmd[i:h[0]]); i = h[0]
            continue
        if q is None and c == "\n" and pend:  # a body that never ends runs to the end of the command
            out.append("".join(cur)); cur = []
            # A shell reads its body as commands, so mark it "\1" (scanned with no env/set exemption).
            mark = "\1" if SHELL_LINE.search(cmd[cmd.rfind("\n", 0, i) + 1:i]) else "\0"
            lines, j = [], i + 1
            while pend:
                d, dash = pend.pop(0)
                while j < len(cmd):
                    e = cmd.find("\n", j); e = len(cmd) if e < 0 else e
                    ln = cmd[j:e]; j = e + 1
                    if (ln.lstrip("\t") if dash else ln) == d:  # exact match: bash does not trim spaces
                        break
                    lines.append(ln)
            out.append(mark + "\n".join(lines))
            i = j
            continue
        if q == "'":
            cur.append(c)
            q = None if c == "'" else q
        elif q == '"':
            if c == "\\" and i + 1 < len(cmd):
                cur.append(c + cmd[i + 1]); i += 1
            elif cmd.startswith("$(", i) or c == "`":
                out.append("".join(cur)); cur = []
            else:
                cur.append(c)
                q = None if c == '"' else q
        elif c == "\\" and i + 1 < len(cmd):
            cur.append(c + cmd[i + 1]); i += 1
        elif c in "'\"":
            q = c; cur.append(c)
        elif c in SEP:
            out.append("".join(cur)); cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def aws_secret(a, base, bare=("credentials", "config")):
    """True when path word a resolves, against the tracked cwd, to the AWS credentials or config file or to something under
    the sso cache dir. After a cd the guard could not resolve (AWS_CWD) only a bare word literally in `bare` counts: never a
    glob, and the caller drops `config` for non-readers and `bare` entirely for a grep/rg/sed/awk pattern word."""
    if "$" in a or "`" in a:
        return False
    t = a.rstrip("/")
    d = t.rsplit("/", 1)[0] if "/" in t else None
    dpath = CWD[0] if d is None else os.path.realpath(os.path.join(CWD[0], os.path.expanduser(d or "/")))
    cache = AWS_DIR + "/sso/cache"
    if dpath == AWS_DIR:
        if base and (fnmatch.fnmatchcase("credentials", base) or fnmatch.fnmatchcase("config", base)):  # also cred*, c[r]edentials, *
            return True
    elif d is None and AWS_CWD[0] and (base in bare or (re.search(r"[*?\[]", base)
                                                         and ("[" in base or fnmatch.fnmatchcase("credentials", base)))):
        return True  # any glob that could match credentials (*, ?*, [[:alpha:]]*) counts; wc, ls and stat never print content
    return dpath == cache or dpath.startswith(cache + "/")


def secret_path(arg, short_glob=True, bare=("credentials", "config")):
    """short_glob False: a glob with fewer than 3 literal characters (.*, .??*) is not judged, because as a grep pattern it is a regex."""
    a = arg.strip("'\"")
    if not a or a.startswith("-"):
        return False
    a = re.sub(r"^(?:(?:if|of)=|(?:\w+=)?@)", "", a)  # dd if=.env, curl -d @.env, curl -F f=@.env
    if not a:
        return False
    base = a.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]  # "HEAD:.env" names .env too
    if aws_secret(a, base, bare):
        return True
    if re.fullmatch(r"\.env(\..+)?", base) or re.fullmatch(r"\.env[*?\[].*", base):
        return not base.endswith(SAFE_ENV_SUFFIX)
    if base == ".envrc" or base in (".netrc", ".git-credentials", ".npmrc", ".pypirc"):
        return True
    if base.endswith((".pem", ".key", ".p12")) or re.fullmatch(r"id_(rsa|dsa|ecdsa|ed25519)(?!.*\.pub$).*", base):
        return True
    if a.endswith((".aws/credentials", ".aws/config", ".config/gh/hosts.yml", ".docker/config.json")) or ".aws/sso/cache" in a:
        return True
    lit = re.sub(r"[*?\[\]]", "", base)
    if lit != base and base and (base[0] == "." or len(lit) >= 3):  # a glob: does it reach a secret file name? (shell globs skip dotfiles unless the pattern starts with a dot)
        if len(lit) < 3 and not short_glob:
            return False
        return any(fnmatch.fnmatchcase(n, base) and (base[0] == "." or n[0] != ".") for n in GLOB_NAMES)
    return False


def words(seg):
    try:  # punctuation_chars splits a glued "<" or ">" into its own word (cat<.env)
        lx = shlex.shlex(seg, posix=True, punctuation_chars="<>")
        lx.whitespace_split, lx.commenters = True, ""
        return list(lx)
    except ValueError:
        return None


def redirects(t):
    """(words without redirections, input files read by "<")"""
    rest, reads, i = [], [], 0
    while i < len(t):
        w = t[i]
        if re.fullmatch(r"\d*<<<?", w) or re.fullmatch(r"\d*(<<|<<-)", w):
            i += 2  # here-doc delimiter or here-string: not a file
        elif re.fullmatch(r"\d*<", w):
            reads += t[i + 1:i + 2]; i += 2
        elif re.fullmatch(r"\d*>+&?|\d*<>", w):
            i += 2  # output target: writing a file prints nothing
        else:
            rest.append(w); i += 1
    return rest, reads


def docker_up_form(cmd, args):
    """True for `docker compose|docker-compose [options] <sub>` with sub in DOCKER_UP_SUBS: these never run a command in a
    container, so --env-file only loads variables. run, exec, config and plain `docker run` print or expose the values."""
    rest = args[1:] if cmd == "docker" and args[:1] == ["compose"] else args if cmd == "docker-compose" else None
    if rest is None:
        return False
    k = 0
    while k < len(rest) and rest[k].startswith("-"):
        k += 2 if rest[k] in DOCKER_VALUE_OPTS else 1
    if k >= len(rest) or rest[k] not in DOCKER_UP_SUBS:
        return False
    # up in the foreground streams container logs (an app may log its env) and build can echo build args: only a
    # detached up and the subcommands that start nothing keep the exemption (found in review).
    if rest[k] == "up":
        return any(a in ("-d", "--detach") for a in rest[k + 1:])
    return rest[k] not in ("build", "restart")


def judge(seg, depth=0, body=False):
    """A deny reason for one segment, or None. body: here-document text, where a bare env or set is a word, not a command."""
    t = words(seg)
    if t is None:  # unreadable quoting: fall back to the raw text
        if re.search(r"stash", seg) and re.search(r"\bgit\b", seg):
            return STASH_FIX
        if re.search(r"\.env\b|\.pem|\.key|id_rsa|credentials|printenv", seg):
            return SECRET_FIX
        return None
    for k, w in enumerate(t):  # bash <<< 'env': a shell runs the here-string as commands
        if re.fullmatch(r"\d*<<<", w) and k + 1 < len(t) and any(os.path.basename(x) in SHELLS for x in t[:k]):
            if r := scan(t[k + 1], depth + 1):
                return r
    t, reads = redirects(t)
    if any(GIT_ENV.match(w.lstrip("\\")) for w in t):
        return GIT_C_FIX  # git config injected through the environment (VAR=x prefix, env, export) can define a stash alias
    # HOME / XDG_CONFIG_HOME only where it is assigned: HOME= / HOME+= words, a declare/export/typeset/local/readonly name,
    # `for HOME in`, and the name after read, mapfile, readarray or printf -v. The bare word elsewhere (grep HOME, echo HOME,
    # printenv HOME) is plain text; $HOME and ${HOME} expansions stay allowed.
    u = list(t)
    while u and (re.fullmatch(r"\w+=.*", u[0]) or u[0].lstrip("\\") in PREFIX | {"builtin", "env"}):
        u = u[1:]
    if any(re.match(r"\\?(HOME|XDG_CONFIG_HOME)\+?=", w) for w in t) or (
            u[:1] in (["for"], ["select"]) and u[1:2] and u[1].lstrip("\\") in HOMES) or (
            u and u[0] in ("declare", "typeset", "local", "export", "readonly")  # nameref: declare -n r=HOME; r=/tmp/h
            and any(re.search(r"(^|=)(HOME|XDG_CONFIG_HOME)\b", w)
                    or re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", w)  # any nameref: its target can be built by the shell
                    or (not w.startswith("-") and not re.fullmatch(r"[A-Za-z_]\w*(\+?=.*)?", w))  # a name built by $ or `
                    for w in u[1:])):
        return HOME_FIX  # a fake HOME (in this segment or exported for later ones) points git at a .gitconfig with a stash alias
    # read, mapfile, readarray and printf -v assign through a name argument; a name built by $ or ` could be HOME
    for k, w in enumerate(t):
        if w in ("read", "mapfile", "readarray", "printf"):
            args = list(itertools.takewhile(lambda x: x not in (";", "&&", "||", "|", "&", "<", "<<<", ">", "\n"), t[k + 1:]))
            if w == "printf":  # only the name after -v is assigned
                names = [args[args.index("-v") + 1]] if "-v" in args[:-1] else []
            else:  # option values (-d x, -u fd, -p prompt) are skipped; the rest are names
                names = [x for j, x in enumerate(args) if not x.startswith("-") and not (j and args[j - 1] in ("-d", "-u", "-p", "-n", "-N", "-t", "-C", "-c", "-O", "-s"))]
            if any(x.lstrip("\\") in HOMES for x in names):
                return HOME_FIX
            names += [x for x in args if x.startswith("-")]  # bundled forms: printf -v$v, read -a$v
            if any(re.search(r"[$`]", x) for x in names):
                return HOME_FIX
    if any(secret_path(r) for r in reads):
        return SECRET_FIX  # any command fed a secret file on stdin can print it
    while t:  # strip words that only run the next word
        w = t[0].lstrip("\\")
        base = os.path.basename(w)
        if re.fullmatch(r"\w+=.*", w):
            t = t[1:]
        elif base == "env":
            t = t[1:]
            while t and (t[0].startswith("-") or re.fullmatch(r"\w+=.*", t[0])):
                skip = 2 if t[0] in ("-u", "-C", "-S") else 1
                t = t[skip:]
            if not t:
                return None if body else ENV_FIX  # bare env prints the whole environment
        elif base in PREFIX:
            t = t[1:]
            if t and t[0] in ("-v", "-V"):
                return None
            while t and t[0].startswith("-"):
                t = t[1:]
        else:
            break
    if not t:
        return None
    cmd, args = os.path.basename(t[0].lstrip("\\")), t[1:]
    # The names-only helper prints variable names, never values . Only this exact path counts: a copy
    # elsewhere could print values, and the tamper guard stops agents rewriting this one.
    if cmd in ("python3", "python") and args and os.path.realpath(os.path.expanduser(args[0])) == ENV_KEYS:
        return None
    if cmd in SHELLS or cmd == "eval":
        if cmd == "eval":
            return scan(" ".join(args), depth + 1)
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return scan(args[i + 1], depth + 1)
        return None
    if cmd == "git":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            if args[i] == "-c" or args[i].startswith("--config-env"):
                return GIT_C_FIX  # a global -c can define an alias for stash; git's own parser takes only the exact words
            i += 2 if args[i] in GIT_OPT_ARG else 1
        if i < len(args) and args[i] == "stash":
            return STASH_FIX
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        if sub == "config":
            # writing alias.*, include.* or includeIf.* can hide a stash alias (a substring check on the value is bypassable).
            # git 2.46+ also takes verbs (git config set alias.x v), so skip a verb and check every key, not only the first word.
            pos = [a for k, a in enumerate(rest) if not a.startswith("-") and not (k and rest[k - 1] in GIT_CFG_FILE)]
            verb = pos[0] if pos and pos[0] in GIT_CFG_VERBS else ""
            keys = pos[1:] if verb else pos
            if verb == "edit" or any(a in ("-e", "--edit") for a in rest):
                return GIT_C_FIX
            if verb == "rename-section" or "--rename-section" in rest:
                if any(GIT_CFG_KEY.match(k) for k in keys):
                    return GIT_C_FIX
            elif (verb == "set" or len(keys) >= 2 or any(a in ("--add", "--replace-all") for a in rest)) \
                    and not any(a in GIT_CFG_READ for a in rest) and any(GIT_CFG_KEY.match(k) for k in keys):
                return GIT_C_FIX
        paths = rest
        if sub == "diff":  # allowlist: a secret path is fine only with names-only output and no other option
            ok = any(a in GIT_DIFF_NAMES for a in rest) and all(a in GIT_DIFF_OK for a in rest if a.startswith("-"))
        elif sub in GIT_PLAIN_SUBS:
            paths = [a for k, a in enumerate(rest) if not (k and rest[k - 1] == "-m")]
            # git rm --cached .env un-tracks a secret committed by mistake and prints nothing: allow it.
            allowed = GIT_PLAIN_OPTS | ({"-u"} if sub == "add" else set()) | ({"--cached", "-r"} if sub == "rm" else set())
            ok = all(a in allowed for a in paths if a.startswith("-"))
        else:
            ok = sub in GIT_NO_PRINT
        return None if ok else (SECRET_FIX if any(secret_path(a) for a in paths) else None)
    if cmd == "find" and not any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args):
        return None
    envfile_ok = cmd in ("docker", "docker-compose") and docker_up_form(cmd, args)
    code = bool(INTERP.fullmatch(cmd)) and any(re.fullmatch(r"-\w*[ceEp]\w*", a) for a in args)  # interpreter given inline code (python -c, node -e)
    # Only a program that loads its own config may take --env/--env-file with a secret path: node/python running a script
    # (not inline code), npm/pnpm/yarn run, and the dev tools. Everything else judges the value as a path to read.
    loads_env = (cmd in ENV_LOADERS or re.fullmatch(r"python[\d.]*", cmd)) and not code and (cmd not in ("npm", "pnpm", "yarn") or any(a in ("run", "run-script") for a in args))
    pat = set()  # indices of the pattern word of grep, rg, sed, awk: a regex such as '.*', not a file name
    if cmd in PATTERN_CMDS:
        flagged = [k for k, a in enumerate(args) if a in ("-e", "--regexp", "-f", "--file") or a.startswith("--regexp=")]
        pat = {k + 1 for k in flagged if args[k] in ("-e", "--regexp")}
        if not flagged:
            k = 0
            while k < len(args):
                if args[k] in PATTERN_VALUE_OPTS:
                    k += 2
                elif args[k].startswith("-"):
                    k += 1
                else:
                    pat = {k}
                    break
    names = []  # (index in args, word)
    for k, a in enumerate(args):
        prev = args[k - 1] if k else ""
        if k and (prev in SKIP_VALUE or (prev == "-x" and cmd in ("rsync", "tar")) or (prev == "--env-file" and envfile_ok)
                  or (prev in ENV_OPTS and loads_env)
                  # dotenv only as a wrapper: dotenv -e <file> -- <cmd>, with no -p, list or get (those print values)
                  or (cmd == "dotenv" and prev in ("-e", "-f") and "--" in args
                      # allowlist before --: only -e/-f/-c with their values and --override/-o; anything else (-p, --print, list) is judged
                      and all(a in ("-e", "-f", "-c", "--override", "-o") or (j and args[j - 1] in ("-e", "-f", "-c"))
                              for j, a in enumerate(args[:args.index("--")])))):
            continue
        if re.match(r"--[\w-]+=", a) and a.split("=", 1)[0] in ENV_OPTS and cmd not in ("docker", "docker-compose"):
            if not loads_env:  # --env=.env: the value is the path
                names.append((k, a.split("=", 1)[1]))
            continue
        names.append((k, a))
    if cmd in ("docker", "docker-compose") and not envfile_ok and any(
            a.startswith("--env-file=") and secret_path(a.split("=", 1)[1]) for a in args):
        return SECRET_FIX
    if cmd == "wc" or (cmd == "xargs" and "wc" in args):  # --files0-from=FILE (or an abbreviation): the value after "=" is the file wc reads and echoes
        names += [(k, a.split("=", 1)[1]) for k, a in names if a.startswith("--f") and "=" in a]
    if cmd in COPIERS:
        pos = [a for k, a in names if not a.startswith("-")]
        # -t DIR / --target-directory=DIR (also bundled, -vt DIR) makes every positional a source; with fewer than two
        # positionals the destination cannot be told, so all of them are judged.
        tdir = cmd != "rsync" and cmd != "ditto" and any(
            a == "--target-directory" or a.startswith("--target-directory=") or re.fullmatch(r"-[A-Za-z]*t[A-Za-z]*", a) for a in args)
        if any(secret_path(a) for a in (pos if tdir or len(pos) < 2 else pos[:-1])):
            return SECRET_FIX  # the destination is only written, so cp .env.example .env is fine
    # GNU wc --files0-from FILE (or any abbreviation, --f...) prints FILE's contents as names in its errors
    elif (cmd not in NO_PRINT or cmd == "wc" and any(a.startswith("--f") for a in args)) and \
            cmd not in ("printenv", "export", "set", "security", "aws", "gh") and \
            any(secret_path(a, short_glob=k not in pat,
                            bare=() if k in pat else ("credentials", "config") if cmd in READERS else ("credentials",))
                for k, a in names):
        return SECRET_FIX  # any other tool that names a secret path may print it
    if INTERP.fullmatch(cmd):  # code text that names a secret file prints it as well as cat does
        # a short dot-glob counts unless the literal is the pattern of a regex call (re.match('.*', s), new RegExp('.*'))
        if any(secret_path(m.group(2), short_glob=not re.search(r"(\bre\.\w+|RegExp)\(\s*$", a[:m.start()]))
               for a in args for m in STR_LIT.finditer(a)):
            return SECRET_FIX
    if code:
        lang = next(k for k in ENV_DUMP if cmd.startswith(k))
        src = [a for a in args if not a.startswith("-")]
        if any(ENV_DUMP[lang].search(a) for a in src):
            return ENV_FIX
        if any(RUNNER.search(a) and ENV_CMD_STR.search(a) for a in src):
            return ENV_FIX  # code that runs env, printenv or set through subprocess, system, exec or child_process
    if (re.fullmatch(r"[gmn]?awk", cmd) or (cmd == "busybox" and args[:1] == ["awk"])) and any(ENV_DUMP["awk"].search(a) for a in args):
        return ENV_FIX
    if cmd == "printenv":
        return ENV_FIX
    if cmd == "export":
        return ENV_FIX if (not args and not body) or any(re.fullmatch(r"-\w*p\w*", a) for a in args) else None
    if cmd in ("declare", "typeset"):
        flags = [a for a in args if re.fullmatch(r"[-+]\w+", a)]
        names = [a for a in args if not a.startswith(("-", "+"))]
        # -p prints values; -x with no name prints every exported value; bare declare prints every variable
        if any("p" in f for f in flags) or (any("x" in f for f in flags) and not names) or (not args and not body):
            return ENV_FIX
    if cmd == "compgen" and any(re.fullmatch(r"-\w*e\w*", a) for a in args):
        return ENV_FIX
    if cmd == "ps":
        for k, a in enumerate(args):
            prev = args[k - 1] if k else ""
            # BSD "e" and macOS -E print each process's environment (macOS -e only selects all processes)
            if re.fullmatch(r"-\w*E\w*", a) or (prev not in PS_VALUE_OPTS and re.fullmatch(r"[A-Za-z]*e[A-Za-z]*", a) and not a.startswith("-")):
                return ENV_FIX
    if cmd == "set":
        return ENV_FIX if not args and not body else None
    if cmd == "security":
        if any(a in ("find-generic-password", "find-internet-password") for a in args) and \
           any(re.fullmatch(r"-\w*[wg]\w*", a) for a in args):
            return SECRET_FIX
    if cmd == "aws" and "configure" in args:
        i = args.index("configure")
        if args[i + 1:i + 2] == ["get"] and any(re.search(r"key|secret", a, re.I) for a in args[i + 2:]):
            return SECRET_FIX
    if cmd == "gh" and args[:2] == ["auth", "token"]:
        return SECRET_FIX
    return None


def pipe_state(t, piped):
    """Tracks a cd into the aws config dir (so a bare `credentials` is the AWS file), and denies xargs <printing tool> after a secret name."""
    while t and re.fullmatch(r"\w+=.*", t[0]):
        t = t[1:]
    if not t:
        return None
    if t[0] in ("cd", "pushd"):
        args = [a for a in t[1:] if a == "-" or not a.startswith("-")]
        target = args[-1] if args else "~"
        if target == "-" or re.search(r"[$`]", target):
            AWS_CWD[0] = True  # unresolvable target: a bare credentials or config word may now be the secret file
        else:
            CWD[0] = os.path.realpath(os.path.join(CWD[0], os.path.expanduser(target)))
    elif os.path.basename(t[0]) == "xargs" and piped:
        k = 1
        while k < len(t) and t[k].startswith("-"):
            k += 2 if t[k] in ("-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a") else 1
        if k < len(t) and (os.path.basename(t[k]) not in NO_PRINT or any(a.startswith("--f") for a in t[k + 1:])):
            return SECRET_FIX
    return None


def body_lang(seg):
    """ENV_DUMP key of the interpreter (python, node, ruby, perl, awk) that the command line seg runs, else None."""
    t = words(seg) or []
    while t and (re.fullmatch(r"\w+=.*", t[0]) or os.path.basename(t[0].lstrip("\\")) in PREFIX | {"env"}):
        t = t[1:]
    c = os.path.basename(t[0].lstrip("\\")) if t else ""
    return next((k for k in ENV_DUMP if (INTERP.fullmatch(c) or c in ("awk", "gawk")) and (c.startswith(k) or (k == "awk" and c == "gawk"))), None)


def scan(cmd, depth=0, body=False):
    if os.environ.get("STASH_GUARD_CRASH"):
        raise RuntimeError("injected crash (test only)")
    if depth > 5:
        return SECRET_FIX  # nests too deeply to read
    if depth == 0:
        AWS_CWD[0] = bool(re.search(r"\b(?:cd|pushd)\s+[^;&|\n]*[$`]", cmd))  # a cd target built by the shell (the split sees it as separate segments)
        CWD[0] = START_CWD[0]
    piped = False  # an earlier segment named a secret file: `echo .env | xargs cat` reads it
    prev, interp_seen = "", False
    for seg in split(cmd):
        # A here-document fed to an interpreter is its program text: apply the environment-dump rules as for -c code. The body
        # may not follow the interpreter's own segment (python3 - <<EOF | cat), so any interpreter earlier on the line counts.
        if seg.startswith("\0") and (body_lang(prev) or interp_seen) and any(r.search(seg) for r in ENV_DUMP.values()):
            return ENV_FIX
        if not seg.startswith("\0") and body_lang(seg):
            interp_seen = True
        prev = seg
        # Whatever the command before it is, a body is read for secret paths and stash words: a parser that ends it
        # differently from bash would otherwise hide a real command.
        if seg.startswith(("\0", "\1")):
            r = scan(seg[1:], depth + 1, seg[0] == "\0")
        else:
            r = judge(seg, depth, body)
            if not r and (t := words(seg)):
                r = pipe_state(t, piped)
                piped = piped or any(secret_path(p) for w in t for p in re.split(r"\\[ntr]|\s+", w))
        if r:
            return r
    return None


def main():
    cmd = None
    try:
        payload = json.loads(sys.stdin.read())
        if isinstance(payload.get("cwd"), str) and os.path.isabs(payload["cwd"]):
            START_CWD[0] = payload["cwd"]
        cmd = payload["tool_input"]["command"]
        if not isinstance(cmd, str):
            return
        why = scan(cmd)
        # Second, fail-closed pass: a quote or backslash inside comment text (`# don't`) can make the whole-command
        # parse swallow the lines after it (found in review). Each physical line is also scanned alone.
        if not why and "\n" in cmd and "#" in cmd:
            why = next((r for line in cmd.split("\n") if line.strip() and (r := scan(line))), None)
    except Exception:
        # Fail closed on a crash: no output reads as "no decision" to policy-guard, so the command would run.
        # Same words as policy-guard's DANGER pattern for stash; anything else passes silently.
        if isinstance(cmd, str) and CRASH_DANGER.search(cmd):
            why = "Stash/secret guard crashed while reading a command that names a stash or secret word. Retry it once as written; do not respell it."
        else:
            return
    if why:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": why}}))


if __name__ == "__main__":
    main()
