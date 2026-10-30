---
name: review-all
description: One command for a full code review. Runs five review skills one after another on the same change (your code-review panel, ponytail-review, pstack blast-radius, pstack thermo-nuclear-code-quality-review, pstack interrogate), then merges them into one ranked, deduplicated report. Report only, changes no code. Use for /review-all, "review everything", "run all the reviews", or "full review".
argument-hint: "[pr-number | pr-url | branch [base-sha] | blank for local changes] [caller: plan-and-build]"
---

# Review all

Runs every review skill installed on this machine against one change and hands back one
report. Each skill looks from a different angle, so their overlap is a signal: a problem two
skills find on their own is more likely real.

**Input**: the skill args: a PR number, a PR URL, `branch` with an optional base commit, or
nothing for local uncommitted changes. A caller skill may add `caller: plan-and-build`; see step 4.

## Rules for the whole run

- **Report only.** No skill in this run edits code, commits or posts to GitHub. Tell each
  skill so when you invoke it. Why: the reviewer never fixes what it reviewed (global
  CLAUDE.md, "Verification"). Fixes come after the user reads the report.
- **One skill at a time.** `code-review` and `interrogate` each fan out several agents. Running
  them together breaks the 5-agents-at-once cap and hits rate limits.
- **A failed skill is not a clean result.** If a skill errors or its agents die, re-run it once.
  If it fails again, list it under "Did not run" in the report. Never read silence as "no
  findings".

## Step 1: pin the target

Work out the target once and pass the same one to every skill, so all five review the same code.

- Args hold a PR number or URL: PR mode. Record the PR number and its head commit
  (`gh pr view <n> --json headRefOid`).
- Args start with `branch`: branch mode, for committed work on a feature branch. If a base sha
  follows, `BASE` is that sha. Otherwise find the default branch
  (`git symbolic-ref --short refs/remotes/origin/HEAD`; exit code 128 means no remote HEAD,
  so fall back to whichever of `main`, `master` exists) and set `BASE=$(git merge-base <default> HEAD)`. No default branch found: ask the
  user for the base. Review `git diff $BASE..HEAD`. No commits since the base: say "Nothing
  to review" and stop.
- Otherwise: local mode. Record `git rev-parse HEAD` and `git diff HEAD --stat` plus untracked
  files from `git status --porcelain`. Nothing changed: say "Nothing to review" and stop.

Every skill writes its own report files to `<scratchpad>/review-all/`, never into the repo.
`code-review` normally writes `.claude/reviews/`; tell it to use the scratch folder instead.
With `caller: plan-and-build`, also tell every skill: "non-interactive: ask no questions,
run no hyperresearch, write only under the scratch folder". After each skill, `git status
--porcelain` must show nothing new; revert anything a skill wrote into the repo and log it.

## Step 2: run the five skills, in this order

Invoke each with the Skill tool. Pass the target from step 1 and the line "report only: do not
edit code, commit or post anywhere".

| # | Skill | What it adds |
|---|---|---|
| 1 | `code-review` | Typecheck, lint, tests and build first, then 8 lens reviewers with refuters. Runs first so a broken build is known before the rest. Answer "no" to its GitHub-posting question; posting happens in step 4. In branch mode, pass "branch review: use `git diff <BASE>..HEAD` in place of `git diff HEAD`; repoRoot is this checkout", because code-review has no branch mode of its own. |
| 2 | `ponytail:ponytail-review` | Logic, safety, load, missing tests, and every line that can be deleted. |
| 3 | `pstack:blast-radius` | What the change breaks outside the diff, proven by running real code. Tell it: single pass, no arena, and run only read-only commands or tests against a local or sandbox stack. |
| 4 | `pstack:thermo-nuclear-code-quality-review` | Strict maintainability: bad abstractions, giant files, condition sprawl. |
| 5 | `pstack:interrogate` | Adversarial reviewers from `~/.claude/pstack-models.md` (`interrogate reviewers` line). Runs last, so it can also challenge what the first four missed. |

After each skill, save its findings to a scratch file (`<scratchpad>/review-all/<n>-<skill>.md`)
before you start the next one. That way the merge reads files, not a long context.

## Step 3: merge into one report

1. Read the five scratch files.
2. Merge duplicates: the same defect at the same `file:line`, or the same root cause, is one
   finding. Keep the clearest wording and list every skill that found it.
3. Severity: map every skill's scale to one: critical, high, medium, low (Critical = critical,
   Important = high, Must fix = high, Minor or Nice to have = low). Use the highest severity
   any skill gave it. A finding that two or more skills
   reached on their own goes up one level (global CLAUDE.md rule).
4. Proof: every finding needs `file:line` plus a command, test or query that shows it. A
   finding without that is labelled UNVERIFIED. Keep it in the report and don't drop it.
5. Conflicts: if one skill flags something and another argues it is fine, keep the finding and
   show both sides in one line.

Load the `unslop` skill, then write the report:

- **Top:** what was reviewed (target and commit), the verdict (ship, fix first, or rethink),
  and what the user must decide.
- **Findings,** most severe first. Each one: the problem in plain words, a concrete example,
  why it matters, the smallest fix (prefer fixes that delete code), and which skills found it.
  Evidence (`file:line`, command and output) goes last, under "How we know".
- **Did not run:** any skill that failed twice, and why.

Write the merged report to `<scratchpad>/review-all/report.md`. The session model does the
merge; if the session is not on Opus, hand the five files to one Opus subagent to merge.
Outside caller mode, if the `ReportFindings` tool is available, report through it instead of
as text.

## Step 4: ask before acting

With `caller: plan-and-build`, skip this step. Return to the caller: the verdict (ship, fix
first, or rethink), the report path, and every critical and high finding, UNVERIFIED ones
included. The caller handles fixes.

Otherwise, end by asking the user:

- which findings to fix (fixes go through a separate review afterwards), and
- in PR mode, whether to post the report to the PR. Post only on a clear yes in this
  conversation.
