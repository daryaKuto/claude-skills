---
name: code-council
description: Council review in three modes, accuracy first (it spends tokens rather than be wrong). code mode reviews a diff, PR, branch or files; plan mode reviews a plan, spec or hypothesis before work starts; implementation mode checks that a diff does what its plan says. Four independent Sonnet lenses, one Opus chairman that merges, then batched refuters that try to disprove every finding by a different method (a second blind refuter that must run something for every high or critical finding). External facts go to ONE hyperresearch run at the light tier, only when a finding depends on one and the user agrees. Use when the user asks for a "council" review, a multi-persona review, to "review the plan", "test this hypothesis", "check the implementation against the plan", or invokes /code-council.
---

# Code Council

> **Usually called through `/proofread`.** Follow `~/.claude/skills/proofread/proof-rules.md`
> (proof, verdict words, Sonnet workers, Opus adjudicators, report location). Where this skill
> and those rules differ, the stricter one wins.


A council finds what is wrong or missing in one piece of work, and proves each finding before
you see it. Four reviewers look through different lenses, blind to each other. A chairman
merges their findings. Refuters then try to prove each finding wrong using a different method
from the reviewer's. Only what survives reaches the report, and nothing is silently dropped:
refuted, unverified and never-covered items are listed too.

## Which skill

| The job | Use |
|---|---|
| Find problems in a diff, a plan, or an implementation, in one pass | this skill |
| Check that every stated fact in a document is true, over 2 to 3 loops | `claim-verification-loop` |
| Answer an open question from the web and docs, with nothing to review yet | `hyperresearch` (or `claim-verification-loop`, which calls it first) |
| A plan with more than ~10 load-bearing facts nobody has checked | `claim-verification-loop` first, then a plan-mode council |

## Modes and lenses

| Mode | Target | The four lenses |
|---|---|---|
| `code` | a diff, PR, branch or files | architect, senior engineer (correctness), security, pragmatist |
| `plan` | a plan, spec or hypothesis, before any code | fact checker (the load-bearing facts, max 10), builder (would each step work if written now), risk (what breaks, rollback, 10x scale), pragmatist (needed, simplest, what is missing) |
| `implementation` | the plan, then the diff | plan auditor (every step mapped to diff lines), senior engineer, security, test reviewer (tests fail before and pass after, no mocks, live changes re-read live) |

The builder lens exists because a plan can pass every fact check and still be impossible: a
REVOKE that the next `CREATE FUNCTION` undoes, or a "normalise once" step that runs between two
writes that mutate the object. Only "write the fix now, would it work?" finds those.

## Accuracy first, then cost

One profile only (owner rule 2026-09-26): **spend tokens rather than be wrong.** Every run gets
14-call reviewers, 12-call refuters that may take 6 more calls rather than guess, and a second
blind refuter on every high or critical finding. Cost is cut only where it buys no accuracy.

Measured on a real workflow (2026-09-25, see `claim-verification-loop`, "Token budget"):
starting an agent costs 50k to 100k weight before it does anything; each tool call adds 5k
to 15k; output is about 1%; the prompt cache does not carry a shared prefix between agents.
So the council spends on independence and on checking, and cuts only these:

- **No cross-review stage.** The old council had four agents score each other's findings.
  Those scores were opinions about findings; refuters check the code.
- **Refuters are batched,** up to 5 findings per agent, grouped by file so each file is read
  once. Independence stays where it matters: a refuter never shares a reviewer's context, and
  the second check never sees the first refuter's verdict.
- **The chairman is told not to use tools** and sees the findings, not the target, so it should
  take one call. Nothing enforces that: check its call count in `run-cost.py` (step 10).
- **The chairman runs on Opus 5.5 at high effort** (owner rule 2026-10-06; `CHAIR` in the
  script). It is the one agent whose judgement shapes every finding (merge, dismiss, severity,
  research questions), and a single Opus call does not hit the rate limits that kill an Opus
  fan-out. Every reviewer and refuter stays Sonnet.

| Run (12 retained findings, 3 high) | Agents | Estimated weight |
|---|---|---|
| Old council (4 reviewers, 4 cross-reviewers, chairman, 3 refuters per high, 1 per other) | 27 | 1.6M to 2.7M |
| This council | 9 | 1.0M to 2.6M |

Estimates from the measured per-agent costs (entry cost plus calls), not a measured run of
this design. It can cost as much as the old council: it buys reviewers and refuters that read
callers and run checks, where the old one had 27 agents that mostly read only the diff.
After the first real run, measure it with `run-cost.py` (step 10) and correct this table.
A hyperresearch light run is extra, is not measured yet, and runs outside the workflow, so
`run-cost.py` does not see it: check the session total instead (for example with `/cost`).

## Steps

1. **Target and mode.** From the args (`/code-council <PR#|branch|path> [plan|implementation]`)
   or the request:
   - No argument: `git diff` against the merge-base with the default branch (fall back to
     `git diff HEAD`). Empty diff: say there is nothing to review and stop.
   - A PR: `gh pr diff <N>`. A branch: `git diff <default>...<branch>`. A path: read the files.
   - `plan` mode: the plan file. `implementation` mode: the plan file, then the diff, in one
     string, with a line `=== DIFF ===` between them.
   - More than ~2000 diff lines: ask whether to narrow (a folder, a subset of files). Never
     truncate silently.
2. **Live state (when the review depends on data outside the target: schema, RLS, deployed
   functions, devices, logs).** Look for a project snapshot script first:
   `grep -rlE "snapshot-live-state|live-state snapshot|verification-sources" CLAUDE.md .claude 2>/dev/null; ls .claude/skills/*/scripts/*snapshot* .claude/verification-sources.json 2>/dev/null`
   - **Found:** run it once, verify it the project's way (for example, one
     verifier agent), and pass its `SUMMARY.md` as `args.context`
     and the folder as `args.snapshot`.
   - **Only `.claude/verification-sources.json`:** run
     `python3 ~/.claude/skills/claim-verification-loop/scripts/snapshot.py --out <scratchpad>/state`
     (same verify-once rule).
   - **Not found:** ask the user (AskUserQuestion) whether a script or command pulls the
     current state for what is being reviewed. Options: they give one; review from code only;
     or ONE agent pulls the needed facts into a file first. Never let each reviewer query live
     systems on its own.
   - The review does not depend on live data: skip this step.
3. **Research before the council (plan mode only, and only when the plan's premise is an
   external fact:** a library's behaviour, a vendor limit, a standard). Run the research gate in
   step 7 first, then append the digest to `args.context` so the reviewers see it. Otherwise
   let the reviewers raise research questions; step 7 handles them.
4. **Estimate.** Tell the user in one line: agents (4 reviewers + 1 chairman + one refuter per
   5 retained findings + one second-check refuter per 5 high findings, plus the snapshot
   verifier if step 2 ran) and the estimate from the cost table. This is information, not a
   reason to shrink the run.
5. **Launch:**
   ```
   Workflow({ scriptPath: "<home>/.claude/skills/code-council/scripts/council-workflow.js",
     args: { mode, targetDescription, reviewTarget, repoRoot, context, snapshot,
             projectRules, previous } })
   ```
   `lenses` (optional, `[{ key, label, focus }]`) replaces the mode's four lenses; the
   `/code-review` command uses it to run eight. Severity runs low, medium, high, critical;
   critical and high both get the second check.
   `projectRules`: paste the project's hard stops (for example: no `git stash`, no
   writes, no printing secrets, emails or user ids). `targetFiles` is optional; the script
   reads file names from the diff headers.
   **While it runs, the user's follow-up questions are yours, not the agents'.** Answer them
   in the main thread. Never put them in `args`, never SendMessage them to a workflow agent,
   and do not relaunch the run to include them.
6. **Failures and stray messages first.**
   - `failedAgents` not 0: re-run those agents (resume the run) before anything else. A failed
     agent is not "no findings".
   - `ignoredMessages` not empty: a message that was not the task reached those agents (the
     owner has seen a follow-up question reach every running reviewer, which then answered it
     instead of reviewing). Every agent is told to ignore such text and name it here. Read the
     named agents' findings: if any answer the stray question instead of reviewing the target,
     that run does not count. Relaunch with `args.attempt` raised by 1 (it changes every
     prompt, so nothing comes back from cache) and tell the user why.
7. **Research gate.** If the result has `stage: "needs-research"`, the chairman found findings
   that depend on external facts (up to 5 merged questions). Ask the user once
   (AskUserQuestion), listing the questions and the findings that depend on them:
   - **Run light research (recommended):** one hyperresearch
     run, about 30 to 40 minutes. Check it is installed first (`claim-verification-loop`,
     Phase 0a, has the check and the first-run side effects). Call
     `Skill(skill: "hyperresearch", args: "<all questions, numbered>. Use the light tier, inference_depth=surface.")`
     Never run the full tier unless the user names it.
   - **Skip:** those findings are verified for their code part only and the external part stays
     UNVERIFIED.
   Turn the report into a digest of at most ~40 lines: per question, the answer in one line,
   the source URL, and how sure the report is. Then resume the same run with every other arg
   byte-identical, so the reviewers and the chairman come back from cache:
   `Workflow({ scriptPath, args: { ...sameArgs, research: "<digest>" }, resumeFromRunId: "<run id>" })`
   (or `researchDecision: "skip"`).
8. **Re-check before reporting.** You are the orchestrator and own the verdict. Personally
   re-check every item in `orchestratorMustRecheck`: every SPLIT, every high or critical finding CONFIRMED
   or REFUTED, and every finding whose refuter disagreed on severity. Re-run the one command or
   read the one path that decides it. This catches a real error most runs.
9. **Report,** compactly and intern-readable:
   - `failedAgents` first if it is not 0: the council did not fully run.
   - Confirmed findings by severity: the problem in plain words, file:line, the evidence and
     method, the fix, and whether the fix was tested.
   - PARTLY findings with what is true instead (`trueValue`).
   - UNVERIFIED findings with what would settle them (`unblock`), and any `needsLive` queries
     (answer them in one live pull if the user wants).
   - One line each: how many were refuted, how many the chairman dismissed, and `notVerified`
     (more than 25 findings). Offer the detail; do not dump it.
   - `neverCovered`: target files no reviewer examined. Unexamined is not the same as fine;
     offer a council on just those files.
10. **Cost.** `python3 ~/.claude/skills/claim-verification-loop/scripts/run-cost.py latest`
    (per-agent calls and weight). Report the total in one line. Do not claim a saving you did
    not measure.
11. **Re-runs (review, fix, review again).** Review only the diff since the commit the last
    council saw (`git diff <last-reviewed-sha>..HEAD`). Pass the earlier findings as
    `args.previous`, one line each (`file:line | summary | verdict`); reviewers will not
    re-raise one whose lines did not change. Re-run the snapshot with its diff option (for example
    `--prev`) and pass only what changed. A re-run should cost less than the first run.

## Failure modes

| Symptom | What happened | Guard |
|---|---|---|
| Short findings list | Agents died (rate limit, error) | `failedAgents` must be 0; every agent but the one chairman is Sonnet, max 5 at once |
| A real bug dropped as "refuted" | The refuter defaulted to refuted when unsure | Refuters return UNVERIFIED when unsure; high REFUTED findings are re-checked in step 8 |
| Refuter agrees with every finding | Same method as the reviewer, same answer | Refuters must use a different method; the second check must run something |
| Findings cite a web page nobody read | A reviewer guessed about a library | Reviewers cannot search the web; external facts go through the research gate |
| Resume re-ran the whole council | An arg other than `research` changed | Keep every other arg byte-identical when resuming |
| Reviewers answered the user's follow-up question instead of reviewing | A mid-run message reached the running agents | Agents are told to ignore it and list it in `ignoredMessages`; the orchestrator answers the user itself and relaunches with `attempt` + 1 if the run was affected (step 6) |
| Plan passes review, fails in the first hour | Only facts were checked | The builder lens asks "would this step work if written now" |

## Provenance

Started as karpathy/llm-council's three stages (independent review, anonymised cross-review,
chairman) plus an adversarial verification loop. Rewritten 2026-09-26 to
match `claim-verification-loop`: the cross-review stage was cut (four agents of opinion, no
code checks), refuters were batched and given a different method and an UNVERIFIED verdict,
plan and implementation modes were added, and external facts go through one hyperresearch run.
2026-10-06: the chairman moved from Sonnet to Opus 5.5 at high effort (owner rule).
