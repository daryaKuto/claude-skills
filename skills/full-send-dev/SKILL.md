---
name: full-send-dev
description: Use only when the owner says "full send" (to dev) for a small, safe change. The agent changes, proves locally, gets a separate review, merges into the project's dev branch, deploys dev from a local script, smoke-tests, and reports a one-line revert. Never tags, never touches main, pre-prod or prod. Needs a "Full send to dev" section in the project's CLAUDE.md; stops without it.
---

# Full send to dev

## Overview
The owner is not watching. You own the change from the first edit to a deployed, smoke-tested dev environment. Local proof is the gate, because CI may be off or only runs after the merge. Dev only: nothing here reaches pre-prod or prod.

## When to use
- The owner says "full send" (or "full send to dev") about one change.
- Not for: a destructive migration (drop, rename, type change; run the project's destructive-migration check), a change that replaces a stateful resource (a database, a bucket, a table), or anything touching pre-prod, prod, main, tags, secrets, auth or billing. Stop and use the normal chunk flow (plan-and-build), where the owner sees it.
- An additive migration (adds a column or table only) is allowed. Name it in the report.

## Project inputs
Read the project's CLAUDE.md section "Full send to dev". It must give: the git remote, the dev branch, the local check commands, the heavy-run wrapper, the dev deploy command, the dev smoke command, the destructive-migration check. If the section or any item is missing, stop and report BLOCKED. Never guess a value, and never use `origin` unless the section names it.

## The steps
1. **Eligibility.** Apply the rules above. After step 2, in the worktree, run the destructive-migration check on any SQL in the diff. A hit, or any "destructive: approved" style marker in the diff, makes the change ineligible. The check may not catch a rename or a column type change, so read every migration in the diff for those too.
2. **Clean up, then branch.** Remove merged, clean checkouts and merged local branches. Check free disk (`df -g /`). `git fetch <remote>`, then cut `feat/<slug>` or `fix/<slug>` from `<remote>/<dev branch>` in its own worktree.
3. **Change and prove it locally.**
   - Reproduce the failure, fix it, watch the same reproduction pass.
   - Add one test that fails before the fix and passes after, against real dependencies. No mocks, no route floods (never loop calls at a database-backed route).
   - Run lint, typecheck, tests and build through the heavy-run wrapper, in the background.
   - UI change: look at it in the browser. Infra change: run the infra checks the project names and the infra diff under the dev profile, from a script file. If the diff replaces a stateful resource, stop and use the chunk flow.
   - Write the proof log `<lane folder or worktree>/full-send-<slug>.log`: one line per check with its result, ending `FS <slug> proof pass <head sha>`. Never merge without that line (a rule you keep, not a tool that refuses), and merge only that sha.
4. **Separate review.** A multi-lens review workflow (fresh reviewers, not the author). Fix findings; at most 3 fix rounds. Round 1 reviews the whole change, middle rounds review only what changed since the last round, the last round reviews everything once more. Reviewers read source and run commands themselves.
5. **PR and merge.** Right before the merge, `git fetch <remote>` and check `git merge-base --is-ancestor <remote>/<dev branch> <head sha>`. If the dev branch moved, merge it into your branch, re-run step 3's checks and write a new proof line: never merge a combination nobody proved. Open a PR into the dev branch on `<remote>` and merge it by plan-and-build step 4 (squash, `--match-head-commit`, landed check, clean-up). Where the dev branch has no PR CI, the proof log line replaces the CI guard ("No PR CI" in that step). If the project's CLAUDE.md says a needed PR is not merged yet, stop here and report BLOCKED.
6. **Deploy dev.** Run the project's dev deploy command from a throwaway checkout of the merged tip, in the background, with the dev profile. The deploy command must take a lock (one dev deploy at a time) and refuse unless the checkout equals the current remote tip. If it does not, stop and report. Then run the dev smoke command.
7. **If CI runs on the push** (check the workflow list, never assume), watch it in the background. A red push run or a red smoke test gets at most one automatic revert: a revert PR into the dev branch (`git revert` of the merge commit, the step 3 checks run on it, its own proof line `FS <slug>-revert proof pass <head sha>`), merged the same way, a redeploy, then report. A second failure: stop and report.
8. **Clean up.** Remove the checkout, the branch, and any Docker containers and volumes you started (`docker compose down -v`, or `docker rm -f -v <ids>`). Never touch another session's.
9. **Report** (format below).

## Hard rules
- Long runs (suites, builds, deploys, CI watches) go out with `run_in_background: true`. Never sleep or poll.
- Heavy runs go through the project's heavy-run wrapper.
- Commands containing guard words (`;`, `&&`, `$`, backticks, here-documents) go in script files, written with Write.
- Never: tag, touch main, deploy pre-prod or prod, force-push, re-run CI on a feature branch, post PR comments unasked, add Claude attribution to a commit or PR, commit `.claude/` or `specs/`.
- Never add a mock, stub or fake to a test.
- If the change alters a plan, spec or decision record, update it and every living artifact that mentions it in the same change.
- Stuck, or a step needs a password or sign-in: stop and report BLOCKED. Do not ask the owner mid-run.

## Report format
Lead with the verdict (deployed and green, or reverted, or BLOCKED), then:
- **What changed:** one or two sentences, plus the PR link and merge commit.
- **Proof:** the commands run and what each returned (cite, do not paste).
- **Deploy and smoke:** the commands and results. If CI ran: its state.
- **Migration:** none, or "additive: <name>. Undo = forward-fix migration" (a reverted commit does not undo a migration that already ran).
- **Review:** rounds used and what was fixed.
- **Revert (one line):** `revert PR into <dev branch> on <remote>, then run <dev deploy command>`.

## Source
Idea of a proof section and an autonomous end-to-end run borrowed from tstack's `full-send` skill (MIT licence). The steps, gates and rules here are our own.
