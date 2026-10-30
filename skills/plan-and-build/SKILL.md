---
name: plan-and-build
description: One command to plan and then implement work of any size. "plan" mode writes a design doc, a plan split into PR-sized chunks, and a decision register that tells each implementing agent which skills to invoke for every step of every task. "go" mode builds one chunk at a time on a plan branch, with fresh Sonnet implementers, a separate reviewer per task, a comment pass and design check per feature, /review-all per chunk, then a PR merged into the plan branch. Ends with a PR from the plan branch to the default branch for the owner to merge. Use for /plan-and-build, "plan this", "build the plan", or any multi-file change the user wants planned before code.
argument-hint: verify <plan file> | plan <idea, ticket or plan file> | go [plan dir]
---

# Plan and build

- `/plan-and-build verify <plan file>` checks an existing plan against the code and live state
  and stops. It is `/proofread` in plan mode, writing `verification.md` into a new plan folder.
- `/plan-and-build plan <idea>` writes the plan folder and stops. Given an existing plan file,
  it runs verify first (or reuses a `verification.md` from the last 7 days) and plans the
  tasks that are STILL NEEDED or CHANGED. UNVERIFIED and BLOCKED tasks are carried into the
  plan flagged, with their settling command or blocker, and get no chunk until settled. The
  orchestrator offers a `to-questionnaire` for a person or team blocker, or a `wizard` for an
  account, key or dashboard step. Plan mode asks their questions (recipient and what is
  needed back; the wizard's stage list) in its step 9 stop message and writes the file into
  the plan folder after the user answers, never with guessed answers. The user sends the
  questionnaire and runs the wizard; agents never run a wizard.
- `/plan-and-build go` builds the newest unfinished plan (or the plan dir given). A plan
  never reaches `go` with an open question: plan mode settles every one before it stops
  (see "Open-question sweep").
- `/plan-and-build release` runs the plan's `release.md` after the owner merged `plan/<slug>`
  into the default branch (see "Mode: release").

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

This skill replaces poteto-mode's routing for the run. pstack and ponytail skills run only
where this file or the register says.

Reference files in this folder: `worker-rules.md`, `reviewer-rules.md`,
`register-template.md`.

## Shape of a plan

- **Plan** `<slug>`: the whole goal, such as "migrate to AWS". Branch `plan/<slug>`.
- **Chunk** `C<n>`: one PR into `plan/<slug>`. At most about 400 changed lines and 3
  features. Branch `plan/<slug>-c<n>`, cut from the latest `plan/<slug>`. (Not
  `plan/<slug>/c<n>`: git cannot hold a branch and a branch folder with the same name.)
- **Feature** `F<n>`: a slice the user could see or demo, inside a chunk.
- **Task** `T<n>`: the smallest unit a reviewer could reject while approving its neighbour.
- IDs are unique across the plan and never change once go starts.
- **IDs are keys, not names** (owner rule 2026-10-22). They stay in log lines, file and
  branch names, and the first column of a table. Everywhere a person reads (`design.md`,
  `plan.md`, `register.md` prose, reports, PR text, the central plans page), name the thing
  by what it is. A decision's title is what was decided ("Store sessions in
  Postgres, not Redis"), not its topic ("Session store"). Cite it by that title, never
  by id alone, and never as a range ("R-D98 to R-D102" means nothing to an outside dev;
  list the decisions by title). An id may follow a title in brackets when a reader must
  find the row; it never replaces it. Check before saving any of those files:
  `grep -nE '\b[A-Z]{1,3}-?[A-Z]?[0-9]+[a-z]?\b' <file>`: every hit outside a key column,
  log line or path must sit next to its title.
- A plan with one chunk skips the plan branch: its chunk branch is `feat/<slug>` and its PR
  targets the default branch, which only the user merges.

## Branches and release: one merge, one release (owner rule 2026-10-12)

Never break these, and never plan around them. A plan or task that needs an exception stops
and asks the owner (grilling format); it is never planned in silently.

1. **Every chunk PR targets `plan/<slug>`. No chunk, task or "small first PR" ever targets the
   default branch** (`main`). Not even a few lines that "must land first". If later work needs
   it in production first, that need is solved by release order (rule 3), not by an early merge.
2. **Nothing reaches production during the build.** No edge function or app deploy, no
   migration applied to production, no production config, secret or data change, from any
   branch. Chunks are proven on preview branches and CI only. A chunk's CI must therefore see
   every earlier chunk's schema: the plan's CI applies all plan migrations not yet in
   production to its throwaway database.
3. **One release at the end, rehearsed first.** The plan's last task writes `release.md`: a
   runbook of every production step in a safe order (for example migration 1, deploy,
   migration 2), each with the exact command and the live re-check that proves it landed.
   Every step that runs a SQL file or deploys a function is rehearsed during the build: run on
   the project's rehearsal branch (for example a database preview branch, never production) and
   logged with
   the project's rehearsal log (a small script you write, see the README), for example
   `python3 .claude/hooks/rehearsal.py log <plan dir> sql-file <path> --branch <ref> -- <test>`
   (or `function <name>` in place of `sql-file <path>`). The script runs the test itself and
   writes the line only if it exits 0, with a hash of the file or function as it is then.
   `release.md` names the rehearsal line for each step, or says "not rehearsed: owner
   approves" for steps that cannot be rehearsed (secrets, dashboard settings).
   After the owner merges `plan/<slug>` into the default branch, **agents run the runbook**
   ("Mode: release", owner rule, 2026-10-12). A rehearsed step whose file or function is
   unchanged runs without a prompt: the project's hooks check the hash and that the plan's
   final PR is merged. An unrehearsed or edited step asks the owner. Nothing reaches
   production before that merge.
4. **The owner merges exactly one PR into the default branch:** `plan/<slug>`, at the end.
   Agents merge chunk PRs into `plan/<slug>` after review, per go mode.

## Roles

The global CLAUDE.md applies in full. This adds what is specific here.

- **Orchestrator** (the session model): plans, dispatches, reads short replies, logs progress,
  and runs git and gh commands that a step names. It never edits code or tests.
- **Workers** (implementers, explorers, panel runners) and **reviewers**: fresh subagents,
  `model: "sonnet"`, `subagent_type: "pstack:effort-high"` (if that agent type is not
  available, for example pstack was installed mid-session, use `general-purpose` and say so
  in progress.md). Not `pstack:poteto-agent`: it
  loads poteto-mode, whose playbooks open PRs and spawn agents. Every dispatch is one line:
  "Read `<rules file>`, then `<brief path>`." Workers get `worker-rules.md`, reviewers get
  `reviewer-rules.md`.
- **Adjudicators** run on Opus as `~/.claude/pstack-models.md` sets: pstack's arena
  cross-judge pool, how explainer, why synthesizer and "judgment" roles, plus the merge step of
  `/review-all`, and the adjudicator of every pre-existing bug fix. Reviewers are not
  adjudicators; they stay on Sonnet.
- **Every review is a Workflow, never one reviewer agent** (owner rule 2026-10-25). This
  overrides every "a fresh reviewer" in this file: the plan review (plan step 8), each task
  review and fix-round review, the comment audit and design check of the feature gate, the
  chunk deep review and its fix-round review, and the final review. Each one runs with the
  Workflow tool: lens reviewers (one per angle: correctness and tests, security, blast
  radius, lean code, plan conformance and adversarial; pick the lenses that fit), refuters
  that use a different method from the finder, a blind check for every critical or high
  finding, and one Opus adjudicator that writes the review file the step names. At most 5
  agents in each stage; when there is more work than 5 agents, give each a bigger share and
  budget, never a sixth agent. Workers and refuters run on Sonnet. Reviewers still get
  `reviewer-rules.md` in their brief. Every chunk gets this review after it is implemented,
  and again after each of its fix rounds, before the PR. Why: one reviewer sees from one
  angle; the owner wants findings cross-checked before they reach them.
- **A dead, timed-out or empty agent is "not done" or "not reviewed"**, never clean.
  Re-dispatch once, then stop and ask.
- **The user owns:** any choice between two reasonable designs, and anything touching
  production data, schema changes, migrations, deploys, secrets, auth or billing. These stop
  the run with the question asked in the `grilling` format: options with pros and cons for
  each, the recommendation, and why. Every other "stop and ask" in this file asks the same
  way. A step only the user can do (new key, account,
  dashboard setting) also stops it; the orchestrator offers a `wizard` script for the user to run. The orchestrator decides alone only order and
  mechanics with no design tradeoff, and logs each as `Ruling: <what> because <why>`.
- **Live changes.** Workers write migration files and config, never apply them. Production
  changes wait for the release (see "Branches and release"). In "Mode: release" agents run
  rehearsed steps after the owner's merge; every other production change stays the owner's.
  After any release step, re-read the live object by name and definition before moving on.

## The plan folder

`docs/plans/<YYYY-MM-DD>-<slug>/`, never committed:

| File | Holds |
|---|---|
| `design.md` | Existing code (from `pstack:how`), problem, goal, the architect sketch (usage, types, signatures), rationale, out of scope, and the design interrogation answers. |
| `plan.md` | Commands, global constraints, review focus, then chunks, features and tasks. |
| `register.md` | Decisions, and per task the steps and skills to run. Built from `register-template.md`. |
| `amendments.md` | Optional. Owner changes made after plan mode; wins over `plan.md` where they conflict. |
| `progress.md` | The run log. Every state change is one line, so a restarted run resumes from it. |
| `briefs/`, `reports/`, `diffs/` | Every brief sent, every report and review written, every diff reviewed. |

## Open-question sweep

No question in a plan may reach `go` unasked (owner rule 2026-10-12). The sweep is the
`grilling` skill's "sweep first" section, run on the plan folder, with these sources:

1. `register.md` decisions that are not `accepted` (`proposed`, `open`, "later").
2. Every UNVERIFIED, BLOCKED, TODO or "owner decides" line in `plan.md`, `design.md` and
   `register.md`, and every UNVERIFIED or BLOCKED task carried in from `verification.md`.
3. Assumptions a task depends on that no test or check in the plan proves (two chunks not
   touching the same files, a setting's value, a tool's behaviour).
4. Open decisions and open questions about this plan in the project's central plans artifact
   and in every artifact under "Artifacts to keep in step".
5. Calls the orchestrator would otherwise log as `Ruling:` during go. A call with a real
   tradeoff becomes a question. Pure mechanics are listed under "Calls I will make without
   asking".
6. Design interrogation gaps: a subject in `design.md` missing any of the seven answers, an
   answer with no "How we know", or an answer that is a choice nobody has settled.

Research first, always: run the `grilling` skill's "Research before round 1" on every item
before asking anything. Each item is a fact or a choice; every fact is looked up in the
codebase, the live database and services (read-only, as the project's rules say), and the
plan's records, then written into the plan with how you know it, and never asked. Choices
are researched too, so their pros and cons cite real code and numbers. The user is asked
only real choices, and facts no code, data or document can answer (saying what was
searched). Then show the counts (per source, 0s included; settled by research versus asked)
and settle every item still open in exactly one of two ways. There is no third: no item stays `proposed`, open or "later".

- **The user answers it.** Ask it in `grilling` rounds: options as A/B/C with pros and cons
  of each, the recommendation and why, and what changes in the plan if the user picks
  another option. Status: `accepted <date>: <option>`.
- **The user accepts the recommendations.** At any point (before round 1 or mid-way), "go
  with your recommendations", "accept all" or the same in other words accepts the
  recommendation for EVERY item still open. Before recording it, list those items, one line
  each with the recommended option, so the user sees what they accepted. Status:
  `accepted <date>: <option> (owner accepted all recommendations)`.

"Later" is a valid option only when the user picks it: it is then a decision with its own
date and trigger, not an open item. After the last item, show the full list with each answer,
write every answer into `register.md` and the central plans artifact, and log
`SWEEP clean <date> plan-sha=<shasum of plan.md>` in `progress.md`.

## Design interrogation

Owner rule 2026-10-12: before any build starts, the plan must answer, for every design choice,
why we chose it over the alternatives, what a malicious user can do, which data structure it
uses and why, and where it fails. These are asked and answered in plan mode, never left for
the build, and written down where the next engineer will read them.

**Subjects.** Every decision in the architect sketch and the register; every new or changed
data structure (table, column, index, type, JSON shape, queue, cache, in-memory collection);
every trust boundary a task touches (user input, auth, RLS, an edge function, a webhook, a
device message); every external call (database, API, device, email). One subject can be a
whole chunk only when the chunk is one decision.

**The seven questions**, all answered for every subject that they apply to (say "does not
apply, because ..." otherwise; a blank is never allowed):

1. **Why X and not Y?** The alternatives considered (at least two real ones, "do nothing"
   counts when it is real), and the reason each lost, with numbers or `file:line`.
2. **What does a malicious user do?** Someone with a valid account, someone with none, and a
   device or client sending crafted data: what they try (forged ids, other users' rows,
   replay, oversized or malformed input, flooding), what stops each, and where that check
   lives (`file:line`, RLS policy, constraint). "The UI does not allow it" is not a defence.
3. **Which data structure, and why?** Its shape (columns and types, keys, indexes, JSON
   fields), why this shape over the alternatives, how it is read and written (the queries),
   and how big it gets at 10x and 100x today's rows.
4. **Where does this fail?** Each way it can break (dependency down, timeout, bad data,
   partial write, empty or first-run state, clock or time-zone edge), what the user sees
   then, and how we find out (log, alert, test). A failure nobody would notice is a finding.
5. **What happens at scale?** The cost at 10x and 100x today's load: queries per request,
   rows scanned, payload size, rate limits. Global constitution rule 4: build for scale.
6. **What happens when it runs twice or at the same time?** Retries, double clicks, two
   devices, two cron runs: is it idempotent, which lock or constraint makes it so.
7. **How do we know it works, and how do we undo it?** The test that proves it against real
   dependencies (named in the task's `Tests`), and the rollback if it breaks in production
   (a reverse migration, a flag, a redeploy of the previous version).

**Research first.** As in the sweep: each answer is a fact or a choice. Facts are looked up
in the code, the live system (read-only) and the plan's records by Sonnet workers (at most 5
at once, one subject each, brief pre-loaded with the design and the questions), and written
with how we know. A dead or failed worker's subject is re-run, never marked answered. A
choice (two defensible answers, such as accepting a known abuse case or adding a rate limit)
becomes a register decision and goes to the owner in the sweep, with options, pros and cons
and a recommendation. A question nobody can answer from code, data or documents also goes
to the owner, saying what was searched.

**Where the answers go.** All three, in the same change:
- `design.md`, section "Design interrogation": one block per subject, a row per question:
  `Question | Answer | How we know | Decision`. The answer is plain words an intern can act
  on, with real numbers.
- `register.md`: each decision row's "Why not the alternatives", "Abuse case" and "Fails
  when" columns, copied from the matching subject.
- The project's central plans artifact (named in its CLAUDE.md): the same
  answers under the plan's decisions. Re-render, publish and read back.

**Done when** every subject has all seven answers (or "does not apply, because ..."), every
fact answer has a "How we know", every choice is a register decision, and the plan reviewer
(step 8) found no vague or missing answer. Log `INTERROGATION clean <date> subjects=<n>` in
`progress.md`. Plan mode does not stop without it, and go mode checks it (Start, step 2).

## Mode: plan

1. **Set up.** Find every published artifact that already mentions this plan or spec (global
   CLAUDE.md, "plans are tracked in published artifacts"; the project's CLAUDE.md lists its
   living ones). Note them in `register.md` under "Artifacts to keep in step". Then create the folder. Run `p=$(git rev-parse --git-path info/exclude); mkdir -p
   "$(dirname "$p")"; echo 'docs/plans/' >> "$p"` before writing any plan file.
2. **Ground.** If the input is an existing plan, the grounding is its `verification.md` (run
   verify first if there is none); skip `pstack:how` and run `pstack:architect` in step 4 only
   for tasks whose design no settled decision fixes. Otherwise run `pstack:how` on the code the
   change touches. Save its answer under
   "Existing code" in `design.md`. Ask the user the questions that block the design now, as `grilling` rounds (numbered,
   options with pros and cons, a recommendation and why, worded so "yes" accepts it). Every
   other open question waits for the sweep in step 9; none is dropped.
3. **Size it.** At most 3 files, one feature, and no schema, auth, billing or public API:
   propose the **small path** and wait for a one-word yes. Small path: skip step 4 (write a
   short sketch in `design.md` yourself) and the reviewer agent in step 8. The small path still
   runs step 6 (design interrogation); its answers can be short, never skipped.
4. **Design.** Run `pstack:architect` Phases A and B only, using the "Existing code" section
   as Phase A's grounding and exactly the runners on the `architect runners` line of `~/.claude/pstack-models.md`.
   Stop at the synthesized sketch: Phases C, D and E write code. Save it to `design.md`.
5. **Plan.** Write `plan.md`:
   - **Commands:** typecheck, lint, test, and the command that starts the test stack (local
     Supabase, test database, sandbox). Missing ones are listed for the user at step 9.
   - **Global constraints:** project-wide requirements, exact values copied verbatim.
   - **Review focus:** the 5 likeliest ways this breaks that no test covers yet. Each gets a
     test in the task that owns that code.
   - **Chunks** in merge order, each with an estimate of changed lines. Split any chunk over
     about 400 lines or 3 features. Each chunk must leave `plan/<slug>` working on its own.
     Every chunk targets `plan/<slug>` and none touches production ("Branches and release").
   - **Release:** the last task writes `release.md`, the ordered production runbook (rule 3 of
     "Branches and release"). A plan that deploys or applies anything before the final merge
     is wrong; fix the plan, or stop and ask the owner.
   - **Tasks**, each with `Files` (create, modify, test), `Interfaces` (Consumes and Produces
     with exact signatures, or a pointer into design.md), `Tests` (cases against real
     dependencies), and `Done when` (exact command and expected output). Write every task in
     full; no "same as T3".
6. **Interrogate the design.** Run "Design interrogation" (above) on `design.md` and
   `plan.md`, and write its answers into `design.md`. Every question it leaves as a choice
   becomes a decision row in step 7.
7. **Register.** Build `register.md` from `register-template.md`. Each design choice the user
   has not confirmed is a decision row with status `proposed` until step 9 settles it. Each
   row carries its interrogation answers (why not the alternatives, abuse case, where it
   fails), copied from `design.md`. One
   routing row per task, with numbered steps built from the routing guide.
8. **Review the plan.** A review Workflow (brief: `briefs/plan-review.md`, review:
   `reports/plan-review-<k>.md`) checks completeness against the request, design alignment,
   chunk and task size, buildability, commands, a routing row per task, and the design
   interrogation: every subject answered all seven questions, every fact answer cites how we
   know, and no answer is vague ("handled", "should be fine", "TBD"). Fix blockers and
   re-review once. Cap: 2 rounds, then list what is left for the user.
9. **Add it to the central plans page and stop.** The markdown files stay the working
   source. Never publish a separate page for one plan: add the plan (its decisions, chunks,
   tasks and progress, and the design interrogation answers) to the project's central plans
   artifact, the way the project's
   CLAUDE.md says. Record a summary, not a copy: what
   the plan does and why, its status, one line per chunk and task, each decision with its
   chosen option and a one-line why. No code, logs or progress history, and no internal ids
   (T3, C2, F1, D12) in the prose: say what each thing is. The full detail stays in the
   plan folder (owner rule 2026-10-19). If the project names none, ask the
   user which page is the central one before publishing anything. Read it back, then write
   its link into `register.md`. If publishing fails, say so and go on; the files are the
   source of truth. Tell the user, in plain words:
   the goal, the chunks (one line each, as the PRs they will see), missing commands or test
   stack, and the page link. Then run the **open-question sweep** (above) until it logs
   `SWEEP clean`: every `proposed` decision and every other open item is answered by the user
   or accepted with all recommendations. Republish the central plans page with the answers
   and read it back. The plan is not finished, and plan mode does not stop, while any item
   is open. Then say what to type: `/plan-and-build go`.

## Mode: go

### Start

1. Find the plan: the dir given, else the newest folder under `docs/plans/` whose
   `progress.md` has no `END` line.
2. Check that `progress.md` logs `INTERROGATION clean` and then `SWEEP clean <date>
   plan-sha=<shasum>` with the current `plan.md` shasum, and that no register decision is
   anything but `accepted` or `superseded`. If any check fails (an older plan, or the plan
   changed since), run the **design interrogation** and then the **open-question sweep** now,
   with the same two ways to settle each item, before step 3. No build starts without both.
3. If `progress.md` has a `RUN` line, go to "Resume". Otherwise:
   - `git status --porcelain` must be empty, else stop and ask.
   - A remote is required for chunk PRs (`git remote get-url origin`). None: stop and ask.
   - Start the test stack with the plan's command and check it answers. If it cannot start,
     stop and ask; never fall back to mocks.
   - Log `RUN started <date> plan-sha=<shasum of plan.md> default=<default branch>`.
   - Unless the plan has one chunk: `git switch <default> && git pull --ff-only && git switch
     -c plan/<slug>`, log `PLAN-BRANCH created <sha>`, then `git push -u origin plan/<slug>`
     and log `PLAN-BRANCH pushed`.

### For each chunk C<n>

1. `git switch plan/<slug> && git pull --ff-only`, then switch to `plan/<slug>-c<n>` if
   `git rev-parse --verify --quiet refs/heads/plan/<slug>-c<n>` finds it, else create it with
   `git switch -c`. Any git error stops the run; never hide it.
   Log `C<n> BASE=<HEAD sha>` unless the line exists.
2. Build each feature in the chunk (below).
3. **Deep review.** Run the chunk review as a Workflow (Roles, "Every review is a Workflow"),
   covering the `/review-all` angles; `/review-all branch <C<n> BASE> caller: plan-and-build`
   is the same review when its skills run as workflow lenses. Copy its
   report to `reports/C<n>-review.md` and log `C<n> review <verdict> open=<count of critical
   and high, not counting `pre-existing`>`. `pre-existing` findings go to the Pre-existing bug
   flow with scope C<n>, before this step's fix worker. `/review-all` does not apply
   reviewer-rules.md, so the orchestrator labels a finding `pre-existing` itself when its
   `file:line` is unchanged since C<n> BASE (`git diff <C<n> BASE> -- <file>` shows no change
   at that line). Its other critical and high findings,
   UNVERIFIED ones included, go to
   one fresh worker (`briefs/C<n>-fix.md`), then a review Workflow on the fix diff, then the
   task checks. Log `C<n> fix done open=<count still open>` (log `open=0` with no fix when the
   review found none). If any stay open, or the verdict is "rethink", stop and ask. Medium and
   low findings go to Postponed. Every `fix now` bug for C<n> must be logged complete before
   the merge; `planned` bugs do not block it.
3a. **Need and simplicity review** (owner rule 2026-10-25, every chunk). After the deep review
   in step 3, run a second Workflow that attacks one question from 5 angles: "do we need
   this, and is it simple enough to be maintained?". The reader is the one intern-level
   developer who maintains it after the build. The script is
   `scripts/need-simplicity-review.js` (copy it into the scratchpad and run it by
   `scriptPath`; args `{title, repo, planDir, branch, base, head, intent, alsoInScope, checks}`;
   `planDir` is the plan folder holding plan.md, amendments.md and register.md, `checks` lists
   the checks already green at `head`).
   The 5 angles are:
   - necessity: trace every piece to a planned chunk, a decision or a real risk;
   - deletion test: remove each guard in a /tmp copy, and see what breaks and which other
     layer already blocks it;
   - change cost: make 4 realistic future changes and count the files touched;
   - duplication and layering: count every rule written in more than one place;
   - complexity and standard-tool alternatives: a library, linter or platform feature that
     already does a hand-written part.

   Defenders argue each finding back by a different method, high findings get a blind
   check, and one Opus judge writes `reports/C<n>-need-simplicity.md`. The report has a keep,
   simplify or delete table and the lines the confirmed changes would delete.
   Run it after the deep review, never alongside it, so no stage passes 5 agents.
   Confirmed delete and simplify findings join the step 3 fix worker's brief. A finding
   whose change would lose real protection not enforced elsewhere is a decision for the
   owner, asked in the grilling format. Log `C<n> need-simplicity <verdict> delete=<lines>`.
4. **PR and merge.** Each sub-step is skipped if its log line exists.
   1. `git push -u origin plan/<slug>-c<n>`. Log `C<n> pushed`.
   2. Look for an existing PR: `gh pr list --head plan/<slug>-c<n> --state all --json
      number,state,url`. None: `gh pr create --base plan/<slug> --head plan/<slug>-c<n>`
      (load `unslop`; body: what changed, why, how it was tested, the review summary, what
      the final PR's reviewer should check). Log `C<n> PR <number> <url>`.
   3. Merge only if the log shows `C<n> fix done open=0`, every `C<n> bug <k> fix-now` has a
      matching `C<n>-bug-<k> complete` line, and the PR number is the one logged
      for this chunk. Never merge any other PR. If the repo has `scripts/ci/pr-checks-green.sh`
      (a guard that exits non-zero unless every CI check on the PR passed), run it from the checkout with the PR number and
      merge only on exit 0; log its output line. If `gh pr view <number> --json state` is not
      MERGED, run `gh pr merge <number> --squash --delete-branch --match-head-commit <head sha
      the guard checked>`, so a push after the check cannot be merged unchecked.
   4. Check it landed: `gh pr view <number> --json state,mergeCommit` shows MERGED, then
      `git fetch origin && git merge-base --is-ancestor <mergeCommit sha> origin/plan/<slug>`
      exits 0. Log `C<n> merged <url>`.
   For a one-chunk plan: steps 1 and 2 with branch `feat/<slug>` and `--base <default>`, and
   no merge.
5. Update the central plans page (read it first in a new session) with the progress so far
   (replace the step's status line, do not append a log; same short, id-free rules as step 9 of plan mode),
   and every other artifact listed under "Artifacts to keep in step" with what this chunk changed
   (a step done, a decision taken, a PR merged). Read each one back after publishing.
6. Send the owner a progress update covering the whole chunk ("Progress updates for the
   owner", below). Log `C<n> update sent`.

### For each feature F<n> in the chunk

Log `F<n> BASE=<HEAD sha>` unless the line exists. Then each task, one at a time:

1. Log `T<n> started BASE=<HEAD sha>` unless it exists; on resume, reuse that BASE.
2. Write `briefs/T<n>.md` as pointers, not copies: the plan.md section for T<n>, design.md,
   the register's Decisions table and T<n>'s routing row, the reports of tasks it consumes,
   the BASE sha, and the report path `reports/T<n>.md`.
3. Dispatch a worker. Log `T<n> dispatch <k>`.
4. NEEDS_CONTEXT or BLOCKED: a blocker that needs the user's hands or another team's answer
   stops the task; the orchestrator (never the worker) offers a `wizard` or `to-questionnaire`. Otherwise add context or split
   the task and re-dispatch; cap 2
   re-dispatches (counted from `T<n> dispatch` lines only), then ask. DONE_WITH_CONCERNS: a concern that breaks
   an `accepted` decision or needs a user-owned decision stops the run; other concerns go to
   the reviewer.
   PRE_EXISTING_BUG: run the "Pre-existing bug flow" (below) with scope T<n>.
5. **Check the claim.** HEAD differs from the base (BASE, or FIXBASE in a fix round), the tree
   is clean, and `git diff --name-only <base>..HEAD` has no `docs/plans/`. A verify-only task
   with no code change says so in its plan entry and skips the HEAD check. Any failure is a
   re-dispatch with the failure named.
6. Save `git diff BASE..HEAD` to `diffs/T<n>.diff`. Run a review Workflow with the brief,
   report and diff paths and review path `reports/T<n>-review-0.md`.
7. **Fix loop.** A fail, or a critical or high finding that is not `pre-existing`, starts
   round k (a fail whose only findings are `pre-existing` counts as a pass): log `T<n> fix <k>
   FIXBASE=<HEAD sha> findings=<review path>`, dispatch a fresh worker with the brief plus the
   review path, run step 5, save `diffs/T<n>-fix-<k>.diff`, and run a review Workflow on it
   (review `reports/T<n>-review-<k>.md`). Log `T<n> fix <k> done`. Medium and low go to
   Postponed. `pre-existing` findings of any severity go to the Pre-existing bug flow with
   scope T<n>, never to a fix round or Postponed. Cap: 3 rounds, counted from the log, then ask. Never switch models on your own.
8. Log `T<n> complete`. Then run any `fix next` bug fixes for T<n> before the next task.

**Feature gate, after the feature's last task:** any finding below labelled `pre-existing`
goes to the Pre-existing bug flow with scope F<n>, never to a fix worker or Postponed.

1. **Comment pass** (pstack's `no-comments`, split so no worker spawns an agent):
   1. Dispatch `subagent_type: "pstack:comment-sicko"` (if pstack is not installed, a
      `general-purpose` agent with the same brief and the rule "delete comments that only
      restate the code; keep ones that explain why"), `model: "sonnet"`, with: "Scope:
      `git diff <F<n> BASE>..HEAD`. Do not run /how or /why; when unsure, keep the comment and
      list it as a skip." Its edits stay uncommitted. Log `F<n> comments edited`.
   2. A review Workflow audits the uncommitted diff (review `reports/F<n>-comments.md`) and
      runs typecheck and lint. It lists: code or out-of-scope edits to revert, comments to
      restore (about something we cannot change), and accepted `MUST KILL` flags (comments the pass marked for deletion). A deleted
      comment that warned about a trap in our own code is restored unless a flag fix removes
      that trap. This overrides `no-comments`, because the global CLAUDE.md never lets a trap
      comment disappear while the trap is still there.
   3. Empty list and checks pass: commit the comment files by name as `refactor: remove noise
      comments in F<n>`. Otherwise a fresh worker (`briefs/F<n>-comments.md`) applies the list,
      fixes accepted flags within the feature, and commits; then the fix loop rules apply.
      Unfixable flags go to Postponed. Log `F<n> comments done`.
   4. comment-sicko returns nothing usable twice: revert its edits, log it, continue.
2. **Design and bloat check.** A review Workflow compares `git diff <F<n> BASE>..HEAD` with
   `design.md` and the review focus, and lists code in this feature that duplicates other code
   or could be deleted (review `reports/F<n>-design.md`). Critical and high go to a fresh
   worker (`briefs/F<n>-fix.md`) and the fix loop rules, review Workflow included. The check
   itself does not re-run. Medium and low go to Postponed. Log `F<n> complete`.
3. Send the owner a progress update (below). Log `F<n> update sent`.

### Pre-existing bug flow

A bug that was already in the code before the scope's BASE. Scope S is the task (T<n>), the
feature gate (F<n>) or the chunk review (C<n>) that found it. Bug number k is the count of
`S bug <k> found` lines plus 1. Each step is skipped if its log line exists.

1. **Record.** Log `S bug <k> found <file:line>`. A fourth bug in one scope stops and asks
   (3 per scope at most). A PRE_EXISTING_BUG from a bug-fix task's worker, or a `pre-existing` finding from
   its reviewer or adjudicator, stops and asks; bugs never nest. The paused worker has already committed only work that does not depend
   on the bug (worker rules), so the tree is clean.
2. **Investigate.** Log `S bug <k> investigate <r>` (r counts dispatches). This step is done
   only when `cause=` or `not-a-bug` is logged; an `investigate` line alone means re-dispatch.
   Dispatch one fresh read-only investigator
   (`model: "sonnet"`, load `superpowers:systematic-debugging`, change nothing) with the
   report and the bug's `file:line`. It returns:
   - the root cause as `file:line`, plus a reproducing command or test;
   - a severity: critical, high, medium or low;
   - a relevance to S: **blocks** (S cannot finish correctly, or its tests pass only because
     of the bug), **in path** (S changes the same files but can finish correctly) or
     **unrelated**;
   - **patterns to follow**: 2 or 3 `file:line` examples of how this codebase already does
     what the fix needs (error handling, validation, the helper or query style, naming, test
     layout), from the same module first;
   - or **not a bug**, with the evidence (expected behaviour, a misread).

   Log `S bug <k> cause=<file:line>`. Not a bug: log `S bug <k> not-a-bug`, then continue as
   step 6 says, with the investigator's report as context, and stop here. No answer after 2 investigate lines: ask.
3. **Triage** by relevance and severity together:

   | Relevance | critical | high | medium or low |
   |---|---|---|---|
   | blocks | fix now | fix now | fix now |
   | in path | fix now | fix now | fix next |
   | unrelated | fix now | plan | plan |

   - **Fix now** pauses S until the fix is adjudicated.
   - **Fix next** lets the task finish, then runs the fix straight after `T<n> complete`,
     before the next task. For a feature or chunk scope, fix next is fix now.
   - **Plan** records the bug only in the register's "Pre-existing bugs" table, status
     `planned`, with root cause, test idea and Done when. plan.md is never edited during go,
     so the plan-sha checks still hold; the next `/plan-and-build plan` turns planned bugs
     into tasks.

   Every bug goes in that table. Log `S bug <k> <fix-now|fix-next|planned> <relevance>
   <severity>`; for a feature or chunk scope, log `fix-now`, never `fix-next`. Fix next and
   plan do not wait: continue as step 6 says straight away. A fix that touches production data, schema, auth, secrets or billing stops
   the run and asks the user.
4. **Fix task S-bug-k.** The orchestrator writes `briefs/S-bug-<k>.md`: "Your task is this
   pre-existing bug", the investigator's report path, the reproducing command, the patterns
   to follow, Files (the root-cause files and the test file), Done when (the reproducing
   command and the new test pass, plus typecheck and lint), the routing steps of the
   routing guide's "New behaviour or bug fix" row (failing test first with `pstack:tdd`), and the
   report path `reports/S-bug-<k>.md`. Then it runs the per-task steps 1 and 3 to 7 for
   `S-bug-<k>` (fresh worker, step 5 checks, review Workflow, fix rounds).
5. **Adjudicate.** After the review Workflow passes, dispatch one fresh adjudicator:
   `model: "opus"`, `subagent_type: "pstack:effort-xhigh"`, given `reviewer-rules.md` (its
   adjudicator section applies), the
   brief, the investigator's report, every `diffs/S-bug-<k>*.diff`, every review, and a
   scratchpad path (a new folder in the session's scratchpad directory). Review
   `reports/S-bug-<k>-adjudication.md`. It changes nothing in the live checkout: to run
   anything at the fix's base it uses `git worktree add --detach <scratchpad path> <base>`,
   installs dependencies there the way plan.md's Commands say, and removes that worktree
   after. It checks each point itself, with a command it ran or
   `file:line`, never from the earlier reports:
   - the diff changes the root cause `file:line`, not a symptom further down;
   - the reproducing command fails at the base and passes at HEAD;
   - the new test fails at the base and passes at HEAD, against real dependencies;
   - every caller of each changed function (grep them) still behaves correctly, and their
     tests, typecheck and lint pass;
   - the same bug pattern elsewhere in the code is fixed or listed;
   - the fix follows the patterns to follow and the code around it: no new helper, wrapper,
     dependency, error shape, naming style or test style where an existing one fits. Each
     drift is a high finding with the existing pattern's `file:line`;
   - no new critical or high problem, and no finding from earlier reviews dropped.

   Verdict pass or fail. Log `S bug <k> adjudicated <pass|fail> round <r>`. Fail: its findings
   start a fix round under step 7's rules, then the adjudicator runs again on the new diff.
   Cap 2 adjudication rounds, then ask.
6. **Resume.** Runs after `S-bug-<k> complete` for fix now (log it after the adjudicator's
   pass), or straight after triage for fix next, plan and not a bug.
   - Task scope, found by the worker: re-dispatch T<n> from the current HEAD and log
     `T<n> resume-after-bug <k>`. This line is not a `T<n> dispatch` line, so it does not
     count toward the re-dispatch cap; the 3-bug cap bounds it.
   - Task scope, found by the task's reviewer: re-run the review Workflow on T<n> at the current
     HEAD (next review number); no worker re-dispatch.
   - Feature or chunk scope: continue at the step that was paused (the feature gate check, or
     chunk step 3's fix worker and `open=` count). Comment pass and design check do not
     re-run.

   Every later reviewer of S (task reviewers, the feature checks, the chunk review) gets the
   `S-bug-<k>` commits listed as already adjudicated, to be skipped in its review.

### Progress updates for the owner

The owner reads these between other work and never sees task IDs, so each update must make
sense on one read with no plan open. Send one after every feature (step 3 of the feature
gate), after every chunk, merged or not (log `C<n> update sent`), and every time the run
stops to ask.
Skip any update whose log line exists. Load `unslop` first. Write it in chat, in this order:

1. **Where we are:** the plan's name and the part of it this was, in plain words ("the
   sign-up flow, second of four parts"), plus how much of the plan is done.
2. **What was done:** what now works that did not before, from the user's side where there
   is one. Name files only when the owner needs to look at them.
3. **Why:** the problem this solves, in one or two sentences.
4. **Options and the choice:** for each decision this work relied on (the register's
   Decisions rows it used and every `Ruling:` line logged during it): the options considered,
   which was chosen, and why the others lost. Take this from the register, never from memory.
5. **Found along the way:** pre-existing bugs (what was wrong, and fixed or planned), review
   findings that were fixed, anything postponed.
6. **Next:** what the build does next, and anything the owner must decide or do.

Never use internal IDs or labels: no task, feature, chunk or decision numbers (T4, F2, C1,
D-03), no BASE, FIXBASE, sha or log-line names. Say what the thing is instead ("the password
reset step", "the choice of how to store sessions"). Keep it under about 250 words; leave out
a section that has nothing in it.

### End

1. When every chunk is merged: run `/review-all branch` (interactive) on `plan/<slug>`
   against the default branch, to catch problems between chunks.
2. Open the PR with `gh pr create --base <default> --head plan/<slug>` (or reuse it, found
   with `gh pr list --head plan/<slug>`). Do not merge it. This is the only PR into the
   default branch in the whole run. Its body links `release.md` and says: merge first, then
   type `/plan-and-build release` and the agents run the runbook.
3. Log `END <PR url>`. Update the central plans page and every artifact under "Artifacts to keep
   in step", and read each back.
4. **Report**, after loading `unslop`. Verdict first (ready to merge, or what blocks it). Then
   "You decide": the final PR, the final review's open findings, anything that did not run.
   Then the chunk PR links, "Calls I made without asking" (every `Ruling:` line), "Pre-existing
   bugs" (root cause, fixed or planned), and "Postponed". Plain words only; no internal labels like FIXBASE or MUST KILL.

## Mode: release

Runs `release.md` after the owner merged the plan (owner option A, 2026-10-12). The merge is
the owner's yes to the release; the rehearsal log is the proof each step works.

1. **Check the merge.** `gh pr view <END url> --json state,baseRefName` says MERGED into the
   default branch. Not merged: stop and say so; nothing runs.
2. **Check every step before running any.** For each step, run
   `python3 .claude/hooks/rehearsal.py check sql-file <path>` (or `function <name>`) from the
   main checkout, on the merged default branch. List the steps that are not unlocked (never
   rehearsed, or the file changed since its rehearsal) and the "not rehearsed: owner
   approves" steps, and ask the owner about those in one grilling round before step 3.
   Never re-rehearse or edit a file to make it pass the check.
3. **Run the steps in the runbook's order**, one at a time. Log `REL <n> started` and
   `REL <n> done` in `progress.md`. A rehearsed step runs without a prompt; any other step
   waits for the owner's yes from step 2 (or the prompt the hooks raise).
4. **Re-check each step live before the next** (global CLAUDE.md, "Changes to live systems"):
   re-read the object by name and definition (the migration in the ledger and its effect,
   the deployed function's version and a smoke call). A failed or partial step stops the
   release: report what landed, what did not, and the runbook's rollback for that step, and
   ask. Never improvise a fix on production.
5. **End.** Log `RELEASED <date>`, update the central plans page and every artifact under
   "Artifacts to keep in step" (read each back), and report: each step, its live proof, and
   anything left for the owner.

### Resume

Read `progress.md` top to bottom. Every logged step is done; continue at the first step not
logged. Reuse logged BASE and FIXBASE shas and the logged counts for every cap. Then check:

- `plan.md`'s shasum differs from the RUN line: stop and ask. New tasks get new IDs; old IDs
  keep their meaning.
- The tree is dirty: if every dirty file is in the current task's `Files` list, recommend
  discarding them (`git restore` and `git clean` on those paths only) and re-dispatching the
  task, and wait for a yes. Otherwise show `git status` and ask.
- HEAD is not where the log implies: show `git log <base>..HEAD --oneline` and ask.
- An adjudicator worktree is left from a crash: `git worktree list` shows one under the
  scratchpad. Remove it with `git worktree remove --force <path>`, then `git worktree prune`.

One go run per checkout. Run a second plan in its own git worktree.
