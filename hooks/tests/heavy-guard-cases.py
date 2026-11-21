#!/usr/bin/env python3
"""Cases for heavy-guard.py, lib/pressure.py, lib/mem-check.sh and lib/mem-wait.sh .
Real processes and real temp folders. HOME, LOCK_DIR and HOOKS_STATE point into a scratch folder, so nothing
under your home folder is touched. The pressure level is given as input (PRESSURE_FAKE) or by a tiny script
that prints one line (MEM_CHECK): input data for the gate, not a mock of a dependency of the product.
Exit 0 only if every row passes."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.environ.get("HOOK") or f"{HOOKS}/heavy-guard.py"
LIB = f"{HOOKS}/lib"
# A throwaway "project" with a lock wrapper script. config.json (a temp copy, see main) names it, so rule (a) is on for this folder only.
MAIN = tempfile.mkdtemp(prefix="hg-project-")
os.makedirs(f"{MAIN}/tools")
TAKE_REAL = f"{MAIN}/tools/heavy-lock.sh"
open(TAKE_REAL, "w").write("#!/bin/bash\n")
os.chmod(TAKE_REAL, 0o755)
MEMWAIT_REAL = f"{LIB}/mem-wait.sh"
fails = total = 0


def report(name, ok, got, want):
    global fails, total
    total += 1
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r}, want {want!r}")


def main():
    root = tempfile.mkdtemp(prefix="hg-cases-")
    home = f"{root}/home"
    locks, state = f"{home}/locks", f"{root}/state"
    for d in (home, f"{home}/worktrees/wt-a", locks, state):
        os.makedirs(d, exist_ok=True)
    cfg = f"{root}/config.json"
    json.dump({"heavy_lock_script": TAKE_REAL, "heavy_scope_roots": [MAIN], "lane_dirs": [f"{home}/worktrees"]}, open(cfg, "w"))
    base = {**os.environ, "HOME": home, "LOCK_DIR": locks, "HOOKS_STATE": state, "HEAVY_GUARD_ENFORCE": "1", "CLAUDE_HOOKS_CONFIG": cfg}
    for k in ("PRESSURE_FAKE", "MEM_CHECK", "HEAVY_GUARD_CRASH", "HEAVY_SCOPE_ROOTS"):
        base.pop(k, None)
    plain = f"{root}/plain"  # outside the project and the worktrees
    proj = f"{root}/proj"
    os.makedirs(plain)
    os.makedirs(f"{proj}/app")
    with open(f"{proj}/package.json", "w") as f:
        json.dump({"scripts": {"t": "vitest run", "u": "echo hi", "w": "npm run t", "one": "vitest run src/x.test.ts",
                               "tsc": "tsc -b && echo ok"}}, f)
    with open(f"{proj}/app/package.json", "w") as f:
        json.dump({"scripts": {"t": "jest", "u": "echo hi"}}, f)
    with open(f"{proj}/heavy.sh", "w") as f:
        f.write("#!/bin/bash\n# vitest in a comment is nothing\necho a\nnpx vitest run\n")
    with open(f"{proj}/light.sh", "w") as f:
        f.write("#!/bin/bash\necho a\nls\n")
    with open(f"{proj}/managed.sh", "w") as f:
        f.write("#!/bin/bash\nbash tools/heavy-lock.sh a x\nvitest run\n")
    with open(f"{proj}/late.sh", "w") as f:
        f.write("#!/bin/bash\n" + "echo x\n" * 250 + "vitest run\n")

    def decide(cmd, cwd, **env):
        bg = env.pop("BG", True)  # old rows test rules a and b, so they run in the background (rule e stays quiet)
        e = {**base, **env}
        ti = {"command": cmd, **({"run_in_background": True} if bg else {})}
        p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": ti, "cwd": cwd}),
                           capture_output=True, text=True, timeout=30, env=e)
        if p.returncode:
            return f"EXIT {p.returncode} {p.stderr[-80:]}"
        if not p.stdout.strip():
            return None
        o = json.loads(p.stdout)["hookSpecificOutput"]
        return (o["permissionDecision"], o["permissionDecisionReason"])

    def case(name, cmd, cwd, want, sub="", **env):
        try:
            got = decide(cmd, cwd, **env)
        except Exception as ex:  # a missing hook file lands here: the row fails before the code exists
            got = f"ERROR {str(ex)[:60]}"
        ok = (got is None) if want is None else (isinstance(got, tuple) and got[0] == want and sub in got[1])
        report(name, ok, got if not isinstance(got, tuple) else (got[0], got[1][:70]), want)

    json.dump({"heavy_lock_script": "", "heavy_scope_roots": [MAIN]}, open(f"{root}/empty.json", "w"))
    crit = {"PRESSURE_FAKE": "CRITICAL"}
    ok0 = {"PRESSURE_FAKE": "OK"}
    # 1. every heavy form is refused under CRITICAL, from a folder outside the repo (so only rule b speaks)
    for name, cmd in [
        ("vitest", "vitest run"), ("npx vitest", "npx vitest run"), ("bin vitest", "./node_modules/.bin/vitest"),
        ("any .bin tool", "node_modules/.bin/eslint ."), ("jest", "jest --ci"), ("tsc -b", "tsc -b"),
        ("tsx", "tsx scripts/x.ts"), ("ts-node", "ts-node a.ts"), ("node --test", "node --test"),
        ("npm test", "npm test"), ("npm --prefix test", "npm --prefix app test"), ("npm run build", "npm run build"),
        ("npm ci", "npm ci"), ("compose up", "docker compose up -d"), ("docker-compose up", "docker-compose up"),
        ("docker postgres", "docker run -d -p 5432:5432 postgres:16"), ("docker redis", "docker run --rm redis"),
        ("cdk synth", "cdk synth"), ("xcodebuild", "xcodebuild -scheme x build"), ("eas local", "eas build --local -p ios"),
        ("pg_ctl start", "pg_ctl start -D data"), ("postgres -D", "postgres -D data"),
        ("verify", "./verify"), ("env prefix", "FOO=1 vitest run"),
        ("after cd", "cd app && npm ci"), ("bash -c", "bash -c 'npm test'"), ("nice wrapper", "nice -n 5 vitest run"),
        ("in a pipe", "vitest run | tee out.txt"),
    ]:
        case(f"CRITICAL denies {name}", cmd, plain, "deny", "mem-wait.sh", **crit)
    # 2. not heavy, even under CRITICAL
    for name, cmd in [
        ("single test file", "vitest run src/a.test.ts"), ("single node test", "node --test t/x.test.mjs"),
        ("npm test one file", "npm test -- src/a.spec.ts"), ("tsc noEmit", "tsc --noEmit"), ("ls", "ls -la"),
        ("git status", "git status"), ("echo vitest", "echo vitest"), ("grep vitest", "grep vitest package.json"),
        ("plain docker run", "docker run -d nginx"), ("compose ps", "docker compose ps"),
        ("npm run unknown script", "npm run lint"),
        ("cdk deploy", "cdk deploy"), ("cdk deploy ALLOW_OLD_BASE", "ALLOW_OLD_BASE=1 cdk deploy --all"),
        ("lock wrapper run first", f"bash {TAKE_REAL} a x && vitest run"),
        ("mem-wait run first", f"bash {MEMWAIT_REAL} && vitest run"),
    ]:
        case(f"CRITICAL allows {name}", cmd, plain, None, **crit)
    # 3. package.json and script resolution
    case("npm run t resolves to vitest", "npm run t", proj, "deny", "mem-wait.sh", **crit)
    case("npm run u is light", "npm run u", proj, None, **crit)
    case("npm run w recurses", "npm run w", proj, "deny", "", **crit)
    case("npm run one is a single file", "npm run one", proj, None, **crit)
    case("npm run tsc has tsc -b", "npm run tsc", proj, "deny", "", **crit)
    case("--prefix dir reads that package.json", f"npm --prefix {proj}/app run t", plain, "deny", "", **crit)
    case("--prefix light script", f"npm --prefix {proj}/app run u", plain, None, **crit)
    case("bash script with vitest", "bash heavy.sh", proj, "deny", "", **crit)
    case("bash script light", "bash light.sh", proj, None, **crit)
    case("script that takes the lock itself", "bash managed.sh", proj, None, **crit)
    case("vitest past line 200 not scanned", "bash late.sh", proj, None, **crit)
    # 4. pressure levels
    case("WARN allows", "vitest run", plain, None, PRESSURE_FAKE="WARN")
    case("OK allows", "vitest run", plain, None, PRESSURE_FAKE="OK")
    case("UNKNOWN allows", "vitest run", plain, None, PRESSURE_FAKE="UNKNOWN")
    # 5. inside the repo or a worktree: a lock or the wrapper is needed
    case("repo, no lock", "vitest run", MAIN, "deny", f"{TAKE_REAL} <name> <what>",
         PRESSURE_FAKE="OK")
    case("worktree, no lock", "npm test", f"{home}/worktrees/wt-a", "deny", "heavy-lock.sh", PRESSURE_FAKE="OK")
    case("repo, heavy-lock.sh in the text", f"bash {TAKE_REAL} a verify && vitest run", MAIN, None, PRESSURE_FAKE="OK")
    case("repo, single test file", "vitest run src/a.test.ts", MAIN, None, PRESSURE_FAKE="OK")
    case("repo, light command", "git status", MAIN, None, PRESSURE_FAKE="OK")
    case("repo, HEAVY_LOCK=probe needs the probe lock", "HEAVY_LOCK=probe vitest run", MAIN, "deny", "probe", PRESSURE_FAKE="OK")
    case("empty heavy_lock_script turns rule a off", "vitest run", MAIN, None, PRESSURE_FAKE="OK", CLAUDE_HOOKS_CONFIG=f"{root}/empty.json")
    # 5b. unbalanced quotes are not a crash (finding A); a mere mention of the lock scripts is not taking the lock (finding B)
    case("apostrophe then vitest is still denied", "echo it's done; npx vitest run", plain, "deny", "mem-wait.sh", **crit)
    case("heredoc apostrophe then sleep, foreground", "cat <<EOF\ndon't\nEOF\nsleep 100", plain, "deny", "run_in_background", BG=False)
    case("balanced quotes, light command", "echo \"it's done\"; ls", plain, None, **crit)
    case("mention of heavy-lock.sh does not skip rule b", "echo heavy-lock.sh; npx vitest run", plain, "deny", "mem-wait.sh", **crit)
    case("mention of mem-wait.sh does not skip rule b", "echo mem-wait.sh; npx vitest run", plain, "deny", "mem-wait.sh", **crit)
    case("mention of heavy-lock.sh does not skip rule a", "echo heavy-lock.sh; npx vitest run", MAIN, "deny", "heavy-lock.sh", PRESSURE_FAKE="OK")
    case("heavy command before the lock script still denied", f"npx vitest run && bash {TAKE_REAL} a x", plain, "deny", "mem-wait.sh", **crit)
    case("lock script run in bash -c, then heavy", f"bash -c 'bash {TAKE_REAL} a x && npx vitest run'", plain, None, **crit)
    # round 3 C: only a real run of the real lock script counts (each row is a deny that the old code let through)
    fake = f"{root}/heavy-lock.sh"  # a file of that name that is not the repo script
    open(fake, "w").write("#!/bin/bash\n")
    for name, pre in [
        ("command -v heavy-lock.sh", "command -v heavy-lock.sh && "), ("command -v mem-wait.sh", "command -v mem-wait.sh; "),
        ("bash -n on the script", f"bash -n {TAKE_REAL}; "), ("a same-named file elsewhere", f"bash {fake}; "),
        ("--help on the script", f"bash {TAKE_REAL} --help; "), ("false && take", f"false && bash {TAKE_REAL} a x; "),
        ("time + bare name off PATH", "time heavy-lock.sh a x; "), ("take then || true", f"bash {TAKE_REAL} a x || true; "),
        ("take then ; (runs even when the lock fails)", f"bash {TAKE_REAL} a x; "), ("take in background", f"bash {TAKE_REAL} a x & "),
    ]:
        case(f"CRITICAL still denies: {name}", pre + "npx vitest run", plain, "deny", "mem-wait.sh", **crit)
    case("CRITICAL allows take || exit 3 then heavy", f"bash {TAKE_REAL} a x || exit 3\nnpx vitest run", plain, None, **crit)
    case("CRITICAL allows take on an earlier line", f"bash {TAKE_REAL} a x\nnpx vitest run", plain, None, **crit)
    case("CRITICAL allows time + real path", f"time bash {TAKE_REAL} a x && npx vitest run", plain, None, **crit)
    case("CRITICAL allows cwd-relative script arg", "bash heavy-lock.sh a x && npx vitest run", f"{MAIN}/tools", None, **crit)
    # round 3 D: here-document bodies are text, not commands
    heavy_in_cat = "cat > doc.md <<'EOF'\nit's here\nsleep 100\nEOF"
    case("heredoc body with sleep 100, foreground", heavy_in_cat, plain, None, BG=False, **ok0)
    case("heredoc body with npm test, foreground", "cat > doc.md <<'EOF'\nnpm test\nEOF", plain, None, BG=False, **ok0)
    case("heredoc body with npm test, CRITICAL", "cat > doc.md <<EOF\nnpm test\nEOF", plain, None, **crit)
    case("<<- heredoc body", "cat > d <<-EOF\n\tsleep 100\n\tEOF", plain, None, BG=False, **ok0)
    case("commit message heredoc in $( )", "git commit -m \"$(cat <<'EOF'\nfix: run npm test and sleep 100\nEOF\n)\"", plain, None, BG=False, **ok0)
    case("shift is not a heredoc", "echo $((1<<2))\nsleep 100", plain, "deny", "run_in_background", BG=False, **ok0)
    case("quoted << is not a heredoc", "echo '<<EOF'; sleep 100", plain, "deny", "run_in_background", BG=False, **ok0)
    case("command after the heredoc is still seen", "cat > d <<'EOF'\nx\nEOF\nsleep 100", plain, "deny", "run_in_background", BG=False, **ok0)
    case("bash <<EOF body is a command", "bash <<'EOF'\nsleep 100\nEOF", plain, "deny", "run_in_background", BG=False, **ok0)
    case("| sh heredoc body is a command", "cat <<EOF | sh\nsleep 100\nEOF", plain, "deny", "run_in_background", BG=False, **ok0)
    case("outside, no lock needed", "vitest run", plain, None, PRESSURE_FAKE="OK")
    case("scope roots override", "vitest run", plain, "deny", "heavy-lock.sh", PRESSURE_FAKE="OK", HEAVY_SCOPE_ROOTS=plain)
    # 5b. rule e: a LONG command must run in the background (pressure OK, outside the repo, so only rule e speaks)
    ok = {"PRESSURE_FAKE": "OK"}
    long_cmds = [
        ("vitest suite", "vitest run"), ("npm test", "npm test"), ("npm run build", "npm run build"), ("npm ci", "npm ci"),
        ("compose up", "docker compose up -d"), ("cdk synth", "cdk synth"), ("xcodebuild", "xcodebuild -scheme x build"),
        ("cdk deploy", "cdk deploy --all"), ("npx cdk deploy", "npx cdk deploy"), ("npm run deploy:dev", "npm run deploy:dev"),
        ("docker build", "docker build -t x ."), ("gh run watch", "gh run watch 123"),
        ("gh pr checks --watch", "gh pr checks 5 --watch"), ("aws wait", "aws cloudformation wait stack-create-complete --stack-name x"),
        ("terraform apply", "terraform apply -auto-approve"), ("until loop", "until test -f done; do sleep 5; done"),
        ("while loop", "while pgrep foo; do sleep 2; done"), ("sleep 60", "sleep 60"), ("wrapper script", "bash managed.sh"),
        ("for loop 20 x sleep 2", "for i in {1..20}; do sleep 2; done"), ("for loop unknown count, sleep 10", "for f in $(ls); do sleep 10; done"),
        ("direct ./script", "./managed.sh"), ("bash -c suite", "bash -c 'npm test'"),
    ]
    for name, cmd in long_cmds:
        case(f"rule e denies {name} in the foreground", cmd, proj, "deny", "run_in_background: true", BG=False, **ok)
        case(f"rule e allows {name} in the background", cmd, proj, None, **ok)
    for name, cmd in [
        ("one test file", "vitest run src/a.test.ts"), ("npm test one file", "npm test -- src/a.spec.ts"),
        ("tsc noEmit", "tsc --noEmit"), ("lint", "npm run lint"), ("git status", "git status"), ("gh pr view", "gh pr view 5"),
        ("gh pr list", "gh pr list"), ("sleep 5", "sleep 5"), ("sleep 30", "sleep 30"), ("light script", "bash light.sh"),
        ("echo until sleep", "echo until sleep 99"),
        ("short for loop with sleep 1", "for i in 1 2 3; do echo $i; sleep 1; done"),
        ("for loop of unknown count, sleep 2", "for f in $(ls); do echo $f; sleep 2; done"),
    ]:
        case(f"rule e allows {name} in the foreground", cmd, proj, None, BG=False, **ok)
    case("rule a still wins over e", "vitest run", MAIN, "deny", "heavy-lock.sh", BG=False, **ok)
    case("rule b still wins over e", "vitest run", plain, "deny", "mem-wait.sh", BG=False, **crit)
    os.makedirs(f"{state}/heavy-guard", exist_ok=True)
    open(f"{state}/heavy-guard/NO_BACKGROUND_RULE", "w").close()
    case("off switch disables rule e", "sleep 60", proj, None, BG=False, **ok)
    os.remove(f"{state}/heavy-guard/NO_BACKGROUND_RULE")
    # 6. lock ownership by ancestor pid
    def hold(lock, scope_cmd, cwd, **env):
        """A holder process writes its own pid as the owner of `lock`, then runs the hook as its child."""
        os.makedirs(f"{locks}/{lock}", exist_ok=True)
        code = ("import os,subprocess,sys,json\n"
                f"open('{locks}/{lock}/owner','w').write('a '+str(os.getpid())+' now x '+'{lock}')\n"
                f"p=subprocess.run([sys.executable,'{HOOK}'],input=json.dumps({{'tool_input':{{'command':{scope_cmd!r},'run_in_background':True}},'cwd':{cwd!r}}}),"
                "capture_output=True,text=True)\nsys.stdout.write(p.stdout)\n")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**base, **env}, timeout=30)
        shutil.rmtree(f"{locks}/{lock}", ignore_errors=True)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None

    report("heavy lock held by an ancestor passes", hold("heavy", "vitest run", MAIN, PRESSURE_FAKE="OK") is None,
           hold("heavy", "vitest run", MAIN, PRESSURE_FAKE="OK"), None)
    report("probe lock held by an ancestor passes a probe command", hold("probe", "HEAVY_LOCK=probe vitest run", MAIN, PRESSURE_FAKE="OK") is None,
           hold("probe", "HEAVY_LOCK=probe vitest run", MAIN, PRESSURE_FAKE="OK"), None)
    report("heavy lock does not cover a probe command", hold("heavy", "HEAVY_LOCK=probe vitest run", MAIN, PRESSURE_FAKE="OK") == "deny", "see row", "deny")
    report("ancestor lock still denied under CRITICAL", hold("heavy", "vitest run", MAIN, PRESSURE_FAKE="CRITICAL") == "deny", "see row", "deny")
    other = subprocess.Popen(["sleep", "30"])
    os.makedirs(f"{locks}/heavy", exist_ok=True)
    try:
        with open(f"{locks}/heavy/owner", "w") as f:
            f.write(f"a {other.pid} now x heavy")
        case("lock held by an unrelated live pid denies", "vitest run", MAIN, "deny", "heavy-lock.sh", PRESSURE_FAKE="OK")
        done = subprocess.Popen(["true"])
        done.wait()
        with open(f"{locks}/heavy/owner", "w") as f:
            f.write(f"a {done.pid} now x heavy")
        case("lock held by a dead pid denies", "vitest run", MAIN, "deny", "heavy-lock.sh", PRESSURE_FAKE="OK")
    finally:
        other.terminate()
        other.wait()
        shutil.rmtree(f"{locks}/heavy", ignore_errors=True)
    # 7. fail open
    case("crash allows", "vitest run", MAIN, None, PRESSURE_FAKE="CRITICAL", HEAVY_GUARD_CRASH="1")
    log = f"{state}/heavy-guard/errors.log"
    report("crash is logged with a traceback", os.path.exists(log) and "Traceback" in open(log).read(), os.path.exists(log), True)
    case("garbage stdin allows", "", plain, None)
    # 8. pressure.py through the gate: a real script that prints one line, caching, timeout
    fake = f"{root}/fake-check.sh"
    counter = f"{root}/count"
    with open(fake, "w") as f:
        f.write(f"#!/bin/bash\necho x >> {counter}\necho 'CRITICAL free=9% swap=1.0/2.0G load=1 cores=8 disk=50G top=a:1G'\nexit 2\n")
    slow = f"{root}/slow-check.sh"
    with open(slow, "w") as f:
        f.write("#!/bin/bash\nsleep 6\necho 'OK'\n")
    for p in (fake, slow):
        os.chmod(p, 0o755)
    shutil.rmtree(f"{state}/mem", ignore_errors=True)
    case("real mem-check line CRITICAL denies", "vitest run", plain, "deny", "memory is critical", MEM_CHECK=fake)
    case("second call reads the cache", "vitest run", plain, "deny", "memory is critical", MEM_CHECK=fake)
    n = len(open(counter).read().split()) if os.path.exists(counter) else -1
    report("mem-check ran once for two calls within 15 s", n == 1, n, 1)
    # loop 4, A: CRITICAL caused by low disk (or a fast fall) names free-disk.py, not mem-wait.sh; CRITICAL with plenty of disk keeps the memory text
    for tag, line, want in (("disk under 20 GB", "CRITICAL free=60% swap=0.1/2.0G load=1 cores=8 disk=12G top=a:1G", "free-disk.py --yes --caches-only"),
                            ("fast disk fall", "CRITICAL free=60% swap=0.1/2.0G load=1 cores=8 disk=80G top=a:1G fall=14G/300s", "free-disk.py --yes --caches-only")):
        dfake = f"{root}/disk-check.sh"
        with open(dfake, "w") as f:
            f.write(f"#!/bin/bash\necho '{line}'\nexit 2\n")
        os.chmod(dfake, 0o755)
        shutil.rmtree(f"{state}/mem", ignore_errors=True)
        case(f"CRITICAL from {tag} says to free disk", "vitest run", plain, "deny", want, MEM_CHECK=dfake)
    shutil.rmtree(f"{state}/mem", ignore_errors=True)
    case("CRITICAL from memory with disk=50G keeps the memory text", "vitest run", plain, "deny", "mem-wait.sh", MEM_CHECK=fake)
    shutil.rmtree(f"{state}/mem", ignore_errors=True)
    t = time.time()
    case("mem-check over 2 s is UNKNOWN, gate fails open", "vitest run", plain, None, MEM_CHECK=slow)
    report("timeout answered within 4 s", time.time() - t < 4, round(time.time() - t, 1), "<4")
    shutil.rmtree(f"{state}/mem", ignore_errors=True)
    case("missing mem-check is UNKNOWN, allows", "vitest run", plain, None, MEM_CHECK=f"{root}/nope.sh")
    pr = subprocess.run([sys.executable, "-c", f"import sys;sys.path.insert(0,'{LIB}');import pressure,json;print(json.dumps(pressure.status()))"],
                        capture_output=True, text=True, env={**base, "PRESSURE_FAKE": "WARN"})
    report("pressure.status() shape", pr.returncode == 0 and json.loads(pr.stdout or "{}").get("level") == "WARN", pr.stdout.strip()[:50], "WARN")
    # 9. lib/mem-check.sh: reads limits.json, fall rate
    lim = json.load(open(f"{LIB}/limits.json"))
    report("fall limits", (lim["fall_critical_gb"], lim["fall_window_s"]) == (10, 300), (lim["fall_critical_gb"], lim["fall_window_s"]), (10, 300))

    def mc(limits, samples=None):
        sd = f"{root}/mc-{time.time_ns()}"
        os.makedirs(sd)
        lf = f"{sd}/limits.json"
        json.dump({**lim, **limits}, open(lf, "w"))
        if samples is not None:
            open(f"{sd}/samples", "w").write(samples)
        t0 = time.time()
        p = subprocess.run(["bash", f"{LIB}/mem-check.sh"], capture_output=True, text=True, timeout=20,
                           env={**base, "LIMITS_FILE": lf, "MEM_STATE_DIR": sd})
        return p.returncode, p.stdout.strip(), time.time() - t0

    zero = {"free_critical_pct": 0, "free_warn_pct": 0, "swap_critical_pct": 101, "swap_warn_pct": 101, "disk_block_gb": 0,
            "disk_warn_gb": 0, "fall_critical_gb": 100000}
    rc, line, _ = mc(zero)
    report("mem-check all limits relaxed: OK exit 0", rc == 0 and line.startswith("OK "), (rc, line[:30]), (0, "OK"))
    rc, line, _ = mc({**zero, "free_warn_pct": 101})
    report("mem-check reads limits.json: WARN exit 1", rc == 1 and line.startswith("WARN "), (rc, line[:30]), (1, "WARN"))
    rc, line, _ = mc({**zero, "free_critical_pct": 101})
    report("mem-check reads limits.json: CRITICAL exit 2", rc == 2 and line.startswith("CRITICAL "), (rc, line[:30]), (2, "CRITICAL"))
    rc, line, _ = mc({**zero, "fall_critical_gb": 10}, samples=f"{int(time.time()) - 100} {200 * 1048576}\n")
    report("fall of over 10 GB in 5 min is CRITICAL", rc == 2 and line.startswith("CRITICAL ") and "fall=" in line, (rc, line[:60]), (2, "CRITICAL fall="))
    rc, line, _ = mc({**zero, "fall_critical_gb": 10}, samples=f"{int(time.time()) - 900} {200 * 1048576}\n")
    report("a drop older than 5 min is ignored", rc == 0, (rc, line[:40]), 0)
    rc, line, dt = mc(zero)
    report("mem-check line format", bool(re.match(r"^(OK|WARN|CRITICAL) free=\S+% swap=\S+/\S+G load=\S+ cores=\d+ disk=\d+G top=\S+", line)), line[:90], "format")
    report("mem-check under 1 s", dt < 1.0, round(dt, 2), "<1")
    # 10. mem-wait.sh
    wk = {**base, "MEM_WAIT_POLL": "1", "MEM_WAIT_MAX": "2"}
    ok = f"{root}/ok-check.sh"
    open(ok, "w").write("#!/bin/bash\necho 'OK free=80%'\nexit 0\n")
    os.chmod(ok, 0o755)
    for name, chk, rc_want in (("returns 0 when memory is OK", ok, 0), ("gives up with 1 at the cap", fake, 1)):
        p = subprocess.run(["bash", f"{LIB}/mem-wait.sh"], capture_output=True, text=True, timeout=30, env={**wk, "MEM_CHECK": chk})
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        report(f"mem-wait {name}", p.returncode == rc_want and len(lines) == 1, (p.returncode, len(lines)), (rc_want, 1))
    shutil.rmtree(root, ignore_errors=True)
    print(f"{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)


main()
