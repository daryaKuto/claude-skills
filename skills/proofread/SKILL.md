---
name: proofread
description: "The one entry point for checking whether something is true before anyone acts on it. Proofreads a plan, spec, design doc, audit, report, PR description, a published artifact, a single finding or root cause, a plan's readiness to build, a diff against its plan, or a code change, by routing it to the right engine (claim-verification-loop, verify-findings, code-council, code-review) under one shared set of proof rules. Use for /proofread, \"proofread the plan\", \"verify this plan\", \"is this plan still correct\", \"fact-check the audit\", \"verify this finding\", \"does this diff do what the plan says\", or before a document drives real changes. Report only: it changes nothing it checks (the one exception, with the owner's yes, is adding verdicts to the project's decision record)."
argument-hint: <file, artifact link, PR number, branch, or a claim in quotes> [plan | claims | finding | buildable | implements | code] [tasks=9.15,9.31] [non-interactive]
---

# Proofread

One command for "is this true?". It picks a mode from what it is given, runs the engine that
does that job best, and holds every engine to `proof-rules.md` in this folder. Read that file
first, every run.

## Writing rules (owner rule 2026-10-22)

Every plan, spec, design doc, register, questionnaire or report this skill writes is read by a
person: an intern who can code but does not know this project.
- Load the `unslop` skill before writing, and apply it to every section.
- Be concise. Lead with the decision or result, one idea per sentence. No long narration, no
  history of how you got there, nothing the reader does not need to act.
- Human readable. Name decisions, tasks and questions by what they are, never by an id alone
  or an id range ("R-D98 to R-D102"); an id may follow the title in brackets. Define every
  project term on first use.
- No em dashes.

It never edits the thing it checks. Fixes are a separate step, done by someone else and checked
again. To gate a finished deliverable with a fix loop, use `santa-method` instead; to review a
spec and auto-apply clear fixes, use `review-panel` in finalize mode.

## Pick the mode

The mode named in the args wins. Otherwise take the first row that matches:

1. **Code target.**
   - An open PR (number or URL), or no args with uncommitted changes: `code` with
     `code-review`. A merged PR (`gh pr view <n> --json state` says MERGED): `code`, merged-PR
     rule.
   - A branch or commit range together with a plan path: `implements`.
   - A branch alone: if it has an open PR (`gh pr list --head <branch>`), `code` with
     `code-review` on that PR; otherwise `code` with `code-council` code mode.
   - A commit range alone, a source file or a code directory: `code` with `code-council`
     code mode.
2. **Document.** A prose file, a `/plan-and-build` folder, or a claude.ai artifact link (read
   it with the Artifact tool, `action: "read"`). With tasks: `plan`. Without: `claims`.
3. **One statement** (no question mark) in quotes, or one item from a report: `finding`. An
   unquoted statement falls to row 5. "Was the behaviour this
   diff deletes kept or dropped on purpose?" is a `finding` on that diff.
4. **A question** (ends in "?", quoted or not) with no document: `claims`; the claim loop's
   Phase 0a researches it first with hyperresearch. Not installed: check the question as one
   claim in `finding` mode and say so in the report.
5. **Anything else** (blank args with a clean tree, a non-code directory, a web page): ask the
   owner one question: what should be checked, and against what.

`buildable` (is the plan sized, ordered and routed well enough to build?) runs only when asked
by name: it goes to `code-council` plan mode, after `plan` mode has checked the facts.

## Questions this skill may ask

Only these, each with its `non-interactive` default (ask nothing, take the default, list the
question under Open questions in the report):

| Question | Default |
|---|---|
| Step 5: what to check, against what | stop; write a report that names the blocker |
| Which systems to snapshot (no snapshot script) | repo only; every live claim UNVERIFIED |
| A task subset, or the go-ahead for a run over the cost gate | run the whole plan, in parts, with every loop the engine calls for; report the cost |
| Narrow a large diff (code-review or code-council, over about 2000 lines or 50 files) | the folders the PR description names, else the top folders by changed lines up to 2000 lines; the rest listed as not reviewed |
| code-council's research gate or missing-snapshot ask | skip research; review repo-only and say so |
| Run a live write that is the only proof of a finding | do not run it; UNVERIFIED with the command |
| Write verdicts into the project's decision record | do not write it; list the rows it would add |

**Cost gate.** Before any Workflow launch, say the agent count and a token estimate (the claim
loop's pre-launch estimate). Over about 3M tokens for the whole run, wait for the owner's yes.
The gate only pauses for that yes; it never shrinks the run (the claim loop's own rule: the
estimate is information). Loops follow the engine: 2 to 3, never more.

## Where files go

One rule for every mode, and it overrides the report location an engine names. The folder
is the plan folder the caller names; otherwise `docs/plans/<today>-<slug>/`, where today is the
local date and slug is the document's file name without extension and without a leading date,
the artifact's title, the PR or branch name, or the claim's first four words, in kebab case. If
a `docs/plans/*-<slug>/` folder from the last 7 days exists, reuse it. Before writing, run
`git check-ignore -q <folder>`. If it is not ignored and `git ls-files docs/plans` prints
nothing, append `docs/plans/` to the file `git rev-parse --git-path info/exclude` prints. If
git tracks files there, use `.claude/reviews/<today>-<slug>/` when that is ignored, else the
session scratchpad. Outside a git repo, use the scratchpad. In the folder: the report
`<mode>.md` (`verification.md` for plan mode), one claim register `claim-register.md` shared by all
parts of a run, and `workflow-args-p<part>-loop<N>.json`, written before each Workflow launch so
a failed launch can be re-run from the file.

## Before any mode: project add-on

```bash
grep -rlE "snapshot-live-state|verification-sources|state snapshot" CLAUDE.md .claude 2>/dev/null
ls -d .claude/skills/*verification-loop* .claude/skills/*proof-and-analysis* .claude/skills/*decision-record* 2>/dev/null
```

- The first grep is the claim loop's Phase 1b grep. A snapshot script it finds runs once per
  run (not per part), with the arguments its owner skill gives. A
  `.claude/verification-sources.json` lists the systems instead. Neither: ask which systems to
  snapshot.
- A project verification skill (for example `myproject-verification-loop`): load it for its worked
  adjudication cases and its live-versus-repo rules. The stricter rule wins.
- A project proof-recipe skill (for example `myproject-proof-toolkit`): `finding` mode
  uses its recipes as the method for each condition.
- A project planning format (for example `myproject-decision-record`): after the owner says yes,
  the orchestrator writes the verdicts there as research evidence, then renders and republishes
  it as the project's CLAUDE.md says. This is the one write outside the report folder.
- An earlier claim register for the same document (a file in `docs/plans/` or `.claude/plans/`
  that names the document and holds `id | verdict | method` lines; a `/plan-and-build`
  decision register does not count): add each earlier verdict to its claim's `docEvidence` as
  "earlier verdict: <verdict> by <method> (a lead)". The engine reads `previous` only from loop
  2 on, so loop 1 must get the leads this way.

## Mode: claims

A claude.ai artifact the owner cannot edit comes back from the Artifact tool as a summary,
not the page: its claims are leads only; ask for the file (non-interactive: say so under Open
questions). An artifact that cannot be read at all gives a report with every claim UNVERIFIED.
The plan-mode cap applies here too: over 60 claims, run in parts.

Run `claim-verification-loop` on the document, all its phases, as written: the register,
internal consistency, snapshot once, readers and adversaries through its `verify-workflow.js`
(its Phase 2 says how to call it), the adjudication of disputes, annotation of the register,
its loop rules, and its cost report (`scripts/run-cost.py`). Use its spec mode for a document
checked against code and live state, and its code mode when the document's claims are about
code behaviour (a PR description, a code audit).

## Mode: plan

For a plan that will drive work. `/plan-and-build verify` calls this mode.

1. **Turn each task into claims** in the register, one fact per id. Ids use the plan's task
   number with dots as underscores (task 9.15 is `T9_15`), in numeric order:
   - `T9_15.open`: "the work this task describes is absent on `<ref>` and live". `<ref>` is
     `origin/main` after `git fetch`, unless the plan names another. CONFIRMED means the work
     still has to be done; REFUTED means it is already there. For a task that is a decision,
     an agreement or an account step (no code to find), write `T9_15.open: n/a` and say why.
   - `T9_15.p<k>`: each premise the task rests on ("X still accepts any key"). A decision,
     research item or review finding the task cites by id (D53, Q77) is a premise too, or is
     listed under the task as "not checked".
   - `T9_15.c<k>`: each `file:line` the task cites. `T9_15.n<k>`: each count or name it states.
   - `H<k>`: the plan's headline facts (summary counts, names, status table).

   **Cap:** at most 6 claims per task (the ones that decide its status first) and about 12
   per lane. A plan over 60 claims runs in parts of up to 5 lanes each, one Workflow call per
   part, in sequence; or the owner names a task subset (`tasks=9.15,9.31`). Non-interactive
   default: run in parts. Say the part count and agent count before starting.
2. **Lanes:** cluster the claims by evidence system into at most 5 lanes per Workflow call.
   A lane never mixes evidence systems. With more systems than 5, the extra systems go into
   the next part, never into a mixed lane. Headline facts join the lane whose system holds
   their evidence. Each lane has `decisive` (the one check that could flip the lane's frame,
   done first; claim loop Phase 1) and `liveAllowed` (`''` or the exact read-only live
   commands it may run).
3. **Run the claim loop** as in `claims` mode, on that register. Two lists come back for
   the adjudicator (proof-rules.md, Adjudicators), one command per claim: `challenged` (an
   adversary disagrees: the claim is DISPUTED until settled) and `orchestratorMustRecheck`
   (every REFUTED and PARTLY claim: re-check it before it changes a task). At most 20 per loop;
   the rest carry to the next loop as they are, and after the last loop an unchecked one
   counts as UNVERIFIED for status. A confirmation the engine lists under
   `weakConfirmations` counts as UNVERIFIED for status.
4. **Task status:** go down this list and take the first row that matches. One status per task.

   | Order | Status | Rule |
   |---|---|---|
   | 1 | DONE | `T.open` is REFUTED |
   | 2 | OBSOLETE | a premise is REFUTED or PARTLY in a way that removes the task's reason (the bug it fixes is gone because the code was deleted); log the reason as a ruling |
   | 3 | BLOCKED | the plan text says the task waits on a person, account or other team before any code |
   | 4 | UNVERIFIED | `T.open` is UNVERIFIED, DISPUTED or weak, or a premise that decides whether the task is needed is: give the settling command |
   | 5 | CHANGED | `T.open` is PARTLY (say what part remains), or any premise, cite, count or name is REFUTED or PARTLY (say what is true) |
   | 6 | STILL NEEDED | `T.open` is CONFIRMED or n/a, and no row above matched |

   A claim that does not decide the status and stays UNVERIFIED is listed under the task, with
   its settling command; it does not change the status. Add a rough size of each remaining task:
   the lines likely to change in the cited files.
5. **Write `verification.md`:** Verdict, Task status, Plan errors (what it says against what is
   true), Open questions, Cost, How we know, in that order.

Workflow args for one part of a plan run (the engine's header lists every field):

```json
{ "mode": "spec", "document": "docs/plans/<date>-<slug>/plan.md: tasks 3 to 8",
  "registerPath": "docs/plans/<date>-<slug>/claim-register.md", "repoRoot": "<abs path>",
  "snapshot": "<snapshot folder>", "summary": "<its SUMMARY.md text>",
  "verifierChecks": "one count through the database MCP, not the script",
  "projectRules": "<the project's hard stops, pasted>", "loop": 1, "previous": "",
  "lanes": [{ "key": "database", "decisive": "snapshot tables match live",
              "liveAllowed": "", "claims": [{ "id": "T3.open", "text": "...", "docEvidence": "plan:120" }] }] }
```

## Mode: finding

Run `verify-findings` on the single claim, reading code on `origin/main` after `git fetch`
unless the claim names another ref. The orchestrator splits it into conditions and rates the
finding's severity. One
Sonnet worker per condition (at most 5) checks it with its own method, using the project's
proof recipes where they fit. A high or critical finding also gets one blind refuter with a
different method. Combine with strict AND. A dismissal needs as much proof as a confirmation.
If the finding came from a review, the agent that raised it does not check it.

If the only behavioural proof would write to a live system (a command to a device, a row in
production): do not run it. Use the project's preview branch or sandbox when one exists.
Otherwise the condition is UNVERIFIED with the exact command, and the owner is asked whether
to run it (non-interactive: Open questions).

## Mode: implements

Run `code-council` implementation mode with the diff or branch and the plan path. It reports
where the change does or does not do what the plan says.

## Mode: buildable

Run `code-council` plan mode on the plan. It answers whether the plan can be built as written:
tasks sized and ordered, files and tests named, decisions settled. Run `plan` mode first so it
reviews true facts.

## Mode: code

- **Open PR or local uncommitted changes:** `code-review`, report-only; answer "no" to its
  GitHub-posting question. Its "narrow this large PR?" question is allowed; non-interactive
  default: review the folders the PR description names and list the rest as not reviewed.
- **Merged PR:** review what it changed with `code-council` code mode, and report findings
  only: a merge decision means nothing after the merge. Get the diff from
  `gh pr view <n> --json mergeCommit,commits`: for a merge or squash commit,
  `git diff <mergeCommit>^1 <mergeCommit>`; for a rebase merge, the range from the parent of
  the first PR commit to the last one on the default branch.
- **Branch without a PR, commit range, files or a directory:** `code-council` code mode.
- **Deleted behaviour:** when the diff removes functions, branches, checks or tests, run
  `verify-findings`' deleted-code check on the 20 largest removed pieces inside the reviewed
  scope: was each kept elsewhere or dropped on purpose? List the rest as not checked.

For the full five-skill review the owner runs `/review-all`.

## After the run

- Find every published artifact that mentions what was checked (global CLAUDE.md, "plans are
  tracked in published artifacts") and list, in the report, each statement in them that the
  verdicts contradict. Proofread never edits them; the owner or the build flow does.
- Tell the owner: the verdict, what they must decide, and where the report is.
- In the report and the message, name every claim, task and decision by what it says, not
  by its register id (`T9_15.p2`, `D53`). The id may follow in brackets so the row can be
  found (owner rule 2026-10-22).
- Do not fix anything. Fixes go through the normal build flow and get checked again.
