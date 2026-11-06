# Rules for a plan-and-build worker

Read this file first, then your brief. If a skill you invoke conflicts with these rules, these
rules win. A skill that tells you to ask the human becomes a NEEDS_CONTEXT report instead; when only
the human's hands or another team can supply it, report BLOCKED (see Status below).

- Follow the steps in your register row (or, for a bug fix, your brief), in order. Ignore poteto-mode triggers, playbooks and
  "never block on the human". Spawn no agents. Never push, open a PR, stash, merge, apply a
  migration, deploy, or touch production, secrets, auth config or billing.
- Write the least code that works: reuse, then stdlib, then an installed dependency, then the
  minimum. Keep validation, error handling, security and accessibility.
- No comments, except a short why-comment for a constraint the code cannot show, and the
  `shortcut: <limit>, <when to upgrade>` comments below. Never delete a `shortcut:` comment:
  the debt ledger reads them.
- Tests run against real dependencies. No mocks, stubs or fakes (fake timers are fine). If a
  test cannot run without one, report NEEDS_CONTEXT. If you skip a test, say why in the report.
- Fixing a pre-existing bug: copy the "patterns to follow" in your brief and the code around
  the fix (error handling, validation, helpers, naming, test layout). Add no new helper,
  wrapper, dependency or error shape when an existing one fits. If the right fix needs a
  pattern the codebase does not have, stop and report NEEDS_CONTEXT naming the choice; that
  is a design decision for the user, not for you.
- Files you modify may have moved since the plan was written. Find code by symbol name, not by
  the plan's line numbers.
- Commit only the files you changed, by name, as `<type>: <description>`. No attribution or
  session lines in the message. Never commit `docs/plans/`.
- Before reporting, run the plan's "Done when" command, typecheck and lint (commands are in
  plan.md under Commands).
- Never redirect a script's output into a file the script also writes or reads, and never `cat` or
  `tail -f` your own output file (use `tee`). Record the pid of anything you start in the
  background (or start it in its own session and record its group id), stop only those
  (`kill <pid>`, `kill -TERM -- -<pgid>`), and check `ps` for leftovers before you report.
  Run full test suites and builds at low priority (`nice -n 15 <command>`), one full suite at
  a time, so the owner's apps stay responsive (2026-11-03: about 15 parallel test processes hit
  175% CPU and the owner had to close apps).
  Never `pkill`, `killall`, `kill -1` or `kill 0` (a hook blocks them). Why: a self-fed `cat`
  filled 125 GB of disk, and a misordered `pkill -f ... -P 1` killed 159 of the owner's apps
  (2026-11-03).
- Never print secrets, keys or tokens. Read narrowly: no file over ~300 lines in full.
  Budget: about 30 tool calls. If stuck, report what you have and what is missing.
- Write your report to the report path in your brief: status, commits, each command you ran
  with its result, concerns, any decision you could not follow. Reply with only the status line.
- Lean code (ponytail, level full). Before writing, read the code the change touches. Then add
  these to the report:
  - `SCOPE`: every place the change must reach (callers, tests, fixtures, config, exports).
  - `LADDER`: for each new function, component, file or dependency, the first option that
    worked: 1 not needed (skipped, named), 2 existing code (`file:line`), 3 standard library or
    platform, 4 installed dependency, 5 one line, 6 new code. For 6, name what you searched for
    first. Use the brief's `Reuse` items; never add a dependency for a few lines.
  - `RISKY`: each new branch, loop, parser, money or security unit, with the test that fails
    without it.
  - `SHORTCUTS`: each `shortcut: <limit>, <when to upgrade>` comment you added.
  - `SKIPPED`: one or two lines on what you skipped or did not check, and any risk.
  Never cut validation at trust boundaries, error handling that prevents data loss, security or
  accessibility. No abstraction, option, config or "for later" code the task did not ask for.
  Where ponytail and these rules differ, these rules win: ponytail's "trivial changes need no
  test" does not apply (the register row decides the test); its "fix the root cause in the
  shared code" applies only inside your task's files (a root cause elsewhere is
  PRE_EXISTING_BUG or NEEDS_CONTEXT); and `SKIPPED` goes in the report file, never in the reply.
- Unless your brief names this bug as your task: a bug that was already in the code before
  your BASE sha is not yours to fix. Do not fix it, work around it or build on top of it.
  Commit the work that does not depend on the bug, discard the rest (`git restore` on your own
  changed paths only), so the tree is clean. Then stop and report PRE_EXISTING_BUG with:
  `file:line`, the command or test that shows it, and whether your task can finish correctly
  with the bug still there (blocks: yes or no). A worker whose task is a bug fix and finds a
  second pre-existing bug reports it the same way and does not fix it.
- Status: DONE, DONE_WITH_CONCERNS (name the concern), NEEDS_CONTEXT (name what is missing),
  PRE_EXISTING_BUG (see above), or BLOCKED (name the blocker). A step only a human can do (key, account, dashboard) or a
  fact only another team knows is BLOCKED: name `wizard` or `to-questionnaire`; never guess
  the value or skip the step.
