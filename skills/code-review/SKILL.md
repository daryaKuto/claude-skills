---
name: code-review
description: Multi-agent code review of local changes or a GitHub PR, in any project. Eight independent Sonnet reviewers (architecture, security, scalability, edge cases, test coverage, failure detection, data integrity and concurrency, UX and accessibility), then refuters that try to disprove every finding by a different method, and a second blind refuter for medium, high and critical findings. Runs typecheck, lint, tests and build first; posts to GitHub only with the user's yes. Accuracy first. Use when the user asks for a code review, a PR review, "review my changes", or invokes /code-review with a PR number, URL or nothing.
argument-hint: [pr-number | pr-url | blank for local review]
---


# Code Review


**Input**: the skill args: a PR number, a PR URL, `--pr`, or nothing for local changes.

A workflow review: eight reviewers, each looking through one lens, blind to each other. A
chairman merges their findings, and refuters try to prove each finding wrong by a different
method before it reaches the report. Medium, high and critical findings get a second refuter that
never sees the first one's verdict. Accuracy-only (owner rule 2026-09-26: spend tokens rather
than be wrong).

It runs on the code-council engine: `~/.claude/skills/code-council/scripts/council-workflow.js`,
with this command's eight lenses in place of the council's four. Read the `code-council` skill
for the research gate, the stray-message guard and the failure handling this command reuses.

## Mode

- The args hold a PR number, PR URL or `--pr`: **PR mode**.
- Otherwise: **local mode** (uncommitted changes).

## Phase 1: gather the target

**Local mode:** `git diff HEAD` plus untracked files (`git status --porcelain`). Nothing
changed: say "Nothing to review" and stop. `repoRoot` is the current checkout.

**PR mode:**

| Input | Action |
|---|---|
| Number (`42`) | the PR number |
| URL (`github.com/.../pull/42`) | extract the number |
| Branch name | `gh pr list --head <branch>` |

```bash
gh pr view <N> --json number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,changedFiles,additions,deletions
gh pr diff <N>
```
PR not found: stop with the error. Reviewers need the full files at the PR head, not only
the hunks, so check the head out into a temporary worktree (the user's checkout is never
touched, and nothing is stashed):
```bash
git fetch origin "pull/<N>/head"
git worktree add --detach "<scratchpad>/pr-<N>" <headRefOid>
```
`repoRoot` is that worktree. Remove it after Phase 8 (`git worktree remove`), and on any early
stop too (the user abandons the review, a step fails): never leave it behind.

A fresh worktree has no installed dependencies (`node_modules`, virtualenvs are gitignored), so
Phase 3 would fail on missing modules, not on the code. Before Phase 3:
- The PR does not change `package.json` or the lockfile: link the main checkout's
  dependencies (`ln -s <main checkout>/node_modules <worktree>/node_modules`).
- It does: `npm ci` in the worktree. Install scripts and tests run the PR's code, so for a PR
  from a fork or an author outside the owner's team, ask the user before installing or testing.

More than ~2000 diff lines or 50 files: ask whether to narrow (source first, then tests, then
config and docs). Never truncate silently.

## Phase 2: context

- **Project rules:** the project's CLAUDE.md hard stops, pasted into `projectRules` (for
  example: no `git stash`, no writes, no printing secrets, emails or user ids).
- **Intent:** the PR description, linked issues, and any plan in `.claude/plans/` for this
  work. If a plan exists, say so: `/code-council <target> implementation` checks the diff
  against the plan, which this command does not.
- **Live state:** when the review depends on data outside the diff (schema, RLS, deployed
  functions, devices, logs), follow `code-council` step 2: run the project's snapshot script
  once and verify it. Reviewers never query live systems themselves.

## Phase 3: validate (cheap checks first)

Run the project's checks before any agent starts, and record pass or fail:

| Project | Commands |
|---|---|
| Node / TypeScript (`package.json`) | `npm run typecheck` (or `npx tsc --noEmit`), `npm run lint`, `npm test`, `npm run build` |
| Rust (`Cargo.toml`) | `cargo clippy -- -D warnings`, `cargo test`, `cargo build` |
| Go (`go.mod`) | `go vet ./...`, `go test ./...`, `go build ./...` |
| Python (`pyproject.toml`, `setup.py`) | `pytest` |

Run only what applies, in `repoRoot`. Put the results (pass or fail, plus the first error of
each failure, not the full log) at the top of `args.context`, so the test coverage and failure
detection reviewers start from them.

## Phase 4: review workflow

**The eight lenses** (pass as `args.lenses`):

| key | label | focus |
|---|---|---|
| `architecture` | Architect | Module boundaries, layering and dependency direction, coupling, abstraction leaks, fit with the project's conventions (CLAUDE.md, the surrounding code), and what this change makes harder to change later. |
| `security` | Security reviewer | Injection (SQL, command, XSS), authentication and authorization gaps, secrets in code or logs, input validation at every system boundary, SSRF and path traversal, data exposure, database privilege (RLS, grants, SECURITY DEFINER), risky new dependencies. |
| `scalability` | Scalability reviewer | Behaviour at 10x and 100x today's load: algorithmic cost, N+1 queries, unbounded loops, queries, payloads and memory, missing pagination or indexes, per-request fan-out, rate limits, work that should be batched or cached. |
| `edge-cases` | Edge-case hunter | Null, empty, huge and malformed input, off-by-one, time zones and date boundaries, units, unicode, ordering, retries, partial success, first-run and upgrade paths. |
| `tests` | Test coverage reviewer | For every changed behaviour: which test would fail if it broke (name it and what it asserts). Tests that cannot fail. Mocks, stubs and fake servers (flag them: they prove the guess, not the dependency). A bug fix without a test that fails before and passes after. Use the Phase 3 test results. |
| `failure-detection` | Failure detector | Silent failures: swallowed errors, catch-and-continue, fallbacks that hide a failure, null or empty returned as "no data", errors never logged, alerted or shown to the user, retries that mask a persistent fault, missing health signals. |
| `data-integrity` | Data integrity reviewer | Races and concurrent writers, idempotency of retried requests, transactions and partial writes, migrations that can apply halfway, rollback, cache invalidation, state that can drift between two systems. |
| `ux` | UX and accessibility reviewer | From the user's side: can they see what to do next; does every action show loading, success and error; does it work on a phone, with a keyboard and a screen reader (labels, focus, contrast, tap targets); is the copy plain. |

Why the last two: data integrity is where this owner's production incidents came from (partial
migrations, drift between systems), and the global CLAUDE.md judges every front-end change
from the user's side first.

**Drop the `ux` lens** when the diff touches no UI files (`.tsx`, `.jsx`, `.vue`, `.svelte`,
`.css`, `.scss`, `.html`) and say so. Every other lens always runs.

**Estimate, then launch.** Tell the user in one line: 8 reviewers (5 at a time) + 1 chairman +
one refuter per 5 retained findings + one second-check refuter per 5 medium, high or critical findings,
plus the snapshot verifier if Phase 2 pulled live state. A typical run with 12 retained
findings, 3 of them medium, high or critical, is 13 agents, an estimated 1.5M to 3.7M weight (from the
measured per-agent costs in `claim-verification-loop`, not a measured run). The estimate is
information, not a reason to shrink the run.

**Held-back checks.** Before launch, follow code-council step 5 (write 1 or 2 checks to
`heldback.md`, kept out of `args`); after the report, follow its step 11 (one fresh Sonnet
agent runs them, and a failure becomes a finding).

```
Workflow({ scriptPath: "<home>/.claude/skills/code-council/scripts/council-workflow.js",
  args: { mode: "code", lenses, targetDescription, reviewTarget, repoRoot, context, snapshot,
          projectRules, previous } })
```
- `targetDescription`: one line, e.g. "PR #42: rate limiting on /api/upload".
- `reviewTarget`: the diff (plus the contents of untracked files in local mode).
- `targetFiles`: every changed path, including untracked files in local mode. The engine
  otherwise reads paths only from `+++ b/` diff headers, and a new file missing from the list
  can never show up as never-covered.
- `previous`: on a re-review after fixes, the earlier findings, one line each
  (`file:line | summary | verdict`), and review only `git diff <last-reviewed-sha>..HEAD`.

**While it runs**, answer the user's follow-up questions yourself in the main thread. Never put
them in `args` and never send them to a workflow agent.

**When it returns**, handle in this order (details in `code-council` steps 6 to 8):
1. `failedAgents` not 0: resume the run to re-run those agents. A failed agent is not "no
   findings".
2. `ignoredMessages` not empty: if any named agent answered a stray message instead of
   reviewing, relaunch with `args.attempt` raised by 1.
3. `stage: "needs-research"`: ask the user. Yes: run hyperresearch at the light tier once and
   resume with `args.research`. No: resume with `args.researchDecision = "skip"` (a resume
   without either one stops at the same gate again). Keep every other arg identical.
4. Re-check every item in `orchestratorMustRecheck` yourself (every SPLIT, every critical or
   high CONFIRMED or REFUTED, every severity disagreement) by re-running the one command or
   reading the one path that decides it.

## Phase 5: decide

Count only findings that are CONFIRMED or PARTLY after your re-check.

| Condition | Decision |
|---|---|
| No critical or high, validation passes, no critical or high left UNVERIFIED | **APPROVE** |
| Only medium or low, validation passes | **APPROVE** with comments |
| Any high, any validation failure, or a critical or high still UNVERIFIED | **REQUEST CHANGES** |
| Any critical | **BLOCK**: must fix before merge |

A critical or high finding nobody could settle is not a pass: check it yourself or report it
as blocking until someone does. Draft PR: always **COMMENT**. `--approve` or
`--request-changes` in the args overrides the decision but every finding is still reported.
Local mode: CRITICAL or HIGH means "do not commit yet".

## Phase 6: report artifact

Write `.claude/reviews/pr-<N>-review.md` (local mode: `.claude/reviews/local-<date>-review.md`),
for an intern reader (load `unslop` first). Only if `git check-ignore -q .claude/reviews/x`
succeeds: otherwise write it to the session scratchpad, so a review never lands in a tracked
file (global hard stop: never commit `.claude/`).

```markdown
# PR review: #<N>, <title>

Reviewed <date> | Author <author> | <head> into <base> | Decision: APPROVE, REQUEST CHANGES or BLOCK

## Summary
<one or two sentences: the verdict and the one thing that decides it>

## Findings
### Critical / ### High / ### Medium / ### Low
Each: the problem in plain words, file:line, the evidence and how it was checked, the fix,
and whether the fix was tested. Say which lenses raised it.

## Not settled
UNVERIFIED findings with what would settle them; `neverCovered` files no reviewer examined.

## Validation
| Check | Result |  (type check, lint, tests, build: pass, fail or skipped)

## Dismissed
One line: how many the refuters refuted, how many the chairman dismissed. Detail on request.
```

## Phase 7: publish (PR mode, only with the user's yes)

Posting a review is public and acts in the user's name. Show the user the decision and the
review body, and ask (AskUserQuestion) before running any of:
```bash
gh pr review <N> --comment --body "<summary>"
gh pr review <N> --request-changes --body "<summary with required fixes>"
gh pr review <N> --approve --body "<summary>"
```
For inline comments, one review with all of them:
```bash
gh api "repos/{owner}/{repo}/pulls/<N>/reviews" -f event="COMMENT" -f body="<summary>" \
  -f commit_id="<headRefOid>" --input comments.json   # [{"path": "file", "line": N, "body": "..."}]
```
Never approve because checks are green or because nobody answered: approval needs the user's
yes in this conversation.

## Phase 8: output

```
PR #<N>: <title>
Decision: <APPROVE | REQUEST CHANGES | BLOCK | COMMENT>
Issues: <c> critical, <h> high, <m> medium, <l> low (after refuters and your re-check)
Not settled: <u> unverified, <n> files never covered
Validation: <pass>/<total> checks passed
Agents: <agents> (failed: <failedAgents>), cost: <weight from run-cost.py>
Review: .claude/reviews/pr-<N>-review.md | GitHub: <URL or "not posted">
Next: <what the user must do or decide>
```
Cost: `python3 ~/.claude/skills/claim-verification-loop/scripts/run-cost.py latest`.
Remove the PR worktree.

## Edge cases

- **No `gh` CLI:** local mode only; say so.
- **Diverged branches:** suggest `git fetch origin && git rebase origin/<base>` before the review.
- **Docs or config only:** the same eight lenses still run; most will return no findings
  quickly. Do not skip the review for being small.
- **The workflow script is missing** (a machine without the code-council skill): stop and say
  so. Do not fall back to a single-agent review without telling the user.
