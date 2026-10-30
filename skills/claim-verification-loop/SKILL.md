---
name: claim-verification-loop
description: "Engine behind /proofread (start from /proofread unless this engine is named). Verify every claim in a spec, plan, design doc, audit, PR description or set of code claims across 2 to 3 adversarial loops, in any project. Use when a document or investigation is about to drive real changes, when the user says \"verify every claim\", \"question the assumptions\", \"run N loops\", \"is any of this true\", or asks for spec verification or code verification. Pulls the project's current state ONCE into a snapshot (project script, a .claude/verification-sources.json config, or it asks you), has one agent check the snapshot, then fans out Sonnet readers (max 5 at once) that read the file instead of re-querying, and makes loops 2 and 3 cheaper than loop 1. When there are no claims yet (an open research question), it first calls the hyperresearch skill at its light tier and verifies the claims the answer depends on. Accuracy first (it spends tokens rather than be wrong), then cost: batched calls, a pre-launch estimate and a per-run cost report (scripts/run-cost.py)."
---

# Claim verification loop

> **Usually called through `/proofread`.** Follow `~/.claude/skills/proofread/proof-rules.md`
> (proof, verdict words, Sonnet workers, Opus adjudicators, report location). Where this skill
> and those rules differ, the stricter one wins.


A document makes claims; people act on them. This skill checks every claim against the
code and the live system, then does it again with each pass told exactly what the last pass
concluded AND HOW, so it must confirm by a different route or find the error. A loop that
re-runs the same query gets the same answer and proves nothing.

Why it exists (from a real run): a database investigation produced 16 confident findings.
The first adversarial pass refuted 8, every one derived from reading migration files and
source instead of querying production. Passes 2 and 3 then refuted findings from pass 1,
including two proposed fixes that could not work as written.

## When NOT to use this skill

| Situation | Use instead |
|---|---|
| One finding, one independent check | `verify-findings` |
| The same review re-runs on every push and must not re-flag old issues | `track-review-findings` |
| Find problems in a diff, plan or implementation in one pass (four lenses, refuters) | `code-council` or `review-panel` |
| Checking your own session's work before saying "done" | `verification-loop` |
| Designing a loop from scratch (stop condition, damping) | `loop-design-check`, `loop-until-verified` |

A project can add its own overlay skill with its evidence sources and traps (for example a
`myproject-verification-loop` skill). Load the overlay
too when it exists; it wins where it is more specific.

## The two modes

- **Spec mode:** claims in a spec, plan, design doc or audit are checked against what the code
  and the live system do TODAY. A claim true in the repo but false in production is REFUTED
  for a document about production.
- **Code mode:** claims about code behaviour ("X handles null", "this path is covered by a
  test", "the fix closes the race") are checked against the lines that produce the behaviour,
  the tests and what they assert, and the diff. "Looks right" is not a verdict.

## The shape

```
Phase 0  Build the register          one file, one line per claim, sorted by ACTION
Phase 1  Internal consistency        free: the register against itself, before any tool
Phase 1b Snapshot once, check once   script pulls state; ONE agent checks it
Phase 2  Fan out                     Workflow script, Sonnet readers, max 5 at once
Phase 3  Orchestrator adjudicates    re-check the verdicts that would change what ships
Phase 4  Annotate in place           verdict + METHOD + what the next loop does differently
Phase 5  Loops 2 and 3               re-dispatch only what is unsettled or changed
```

## Accuracy first, then token cost

One profile only (owner rule 2026-09-26): **spend tokens rather than be wrong.** Every run is
what used to be the accuracy profile. Cut tokens only where it costs no accuracy: batched
calls, one snapshot instead of every agent querying live, settled claims carried forward. Measured on a real 6-agent run (2026-09-25),
`weight` = input-token equivalents (cache read 0.1x, cache write 1.25x, output 5x):

| Where the tokens go | Size | So |
|---|---|---|
| **Starting an agent**: its first call writes ~42k tokens to cache (~80k if the system prompt is not cached yet) | 50k to 100k weight per agent, before it does anything | **Fewer agents is the biggest lever.** Readers cost 82k to 137k weight each, and most of that was entry cost |
| **Each tool call** re-reads the agent's whole context | ~5k to 8k weight per call | Batch reads; stop when every claim has a verdict |
| **The snapshot verifier** (20 calls in that run) | 335k weight, 37% of the run | Cap it at ~8 calls, batch its spot checks |
| Output tokens | ~1% | Not worth optimising |
| Shared brief prefix across agents | 0 reuse measured | Do not count on the prompt cache between agents |

**More agents, or deeper agents?** Deeper, unless you need independence. From the same run:
an extra agent costs ~50k to 100k weight just to start; an extra tool call costs ~5k to 15k
(it grows as the context grows); thinking is output, ~1% of the run. So one extra agent buys
roughly 8 to 15 more calls for an agent that already exists. Spend on a new agent only for
(a) independence: an adversary must not share the reader's context or reasoning, which is the
whole point of the check; (b) a different evidence system, so one agent is not split across
two; (c) wall-clock time when claims are truly parallel. Otherwise raise `readerCalls` (to ~12)
and keep effort high. Past ~15 calls an agent's context is large enough that each call costs
more than a fresh, narrowly briefed agent would: split the lane instead.

**Rules, in order of impact:**
1. **At most 5 agents per stage, at most 5 running at once** (owner rule 2026-09-25): up to 5
   readers and up to 5 adversaries per loop, loop 1 included; the snapshot verifier is always 1.
   Within that cap, use the fewest agents that keep evidence sources apart: at least 3 claims
   per reader, 1 or 2 lanes for under 8 claims. One lane per evidence SOURCE, not per claim.
2. **Fresh snapshot check every run.** ~8 calls, spot checks batched into 1 or 2 queries. Never
   reuse an old `VERDICT.json`.
3. **14 batched calls per reader,** and up to 6 more rather than give an unchecked verdict: one
   grep with several `-e` patterns across all cited files, one `sed -n` with several ranges, one
   `jq` for several fields.
4. **One adversary per reader lane, every loop, every lane** (up to 5), confirmed lanes
   included: a wrong CONFIRMED ships a bug.
5. **Loops 2 and 3 re-dispatch only unsettled or changed claims** (Phase 5). If loop 2
   produced only confirmations, skip loop 3 and say so.
6. **Estimate before launch:** weight ~= 150k x readers + 300k (snapshot verifier, if run)
   + 150k x adversaries. Tell the user the estimate as information. Do not shrink the run to
   save tokens.
7. **Measure after every loop:** `python3 ~/.claude/skills/claim-verification-loop/scripts/run-cost.py latest`
   prints per-agent calls, cache reads and writes, and weight. Record the total in the register.
   Later loops cost less because settled claims are carried forward (Phase 5), never because
   checks were cut.

## Phase 0a: no claims yet? Research first (open questions)

When the user brings a QUESTION rather than a document with claims ("which library should we
use", "how does X handle Y", "what changed in Z"), there is nothing to verify yet. Produce the
claims with the research skill, then verify the ones that matter.

1. **Check it is installed.** Prefer the global skill `/hyperresearch` (file
   `~/.claude/skills/hyperresearch/SKILL.md`, from `hyperresearch install --global`). Fall back
   to the plugin `/hyperresearch:deep-research` only if the global skill is missing: the plugin
   runs `hyperresearch install .`, which also adds a PreToolUse hook and 16 agents to the
   project's `.claude/`. Both need the CLI: `command -v hyperresearch` must print a path.
   Source: github.com/jordan-gibbs/hyperresearch (MIT, a Claude Code research harness with
   cite-checking, an independence audit of sources and adversarial critics).
   Missing: stop and tell the user. Installing runs third-party code, so the user does it:
   `uv tool install hyperresearch` (or `pipx install hyperresearch`; Homebrew Python refuses a
   plain pip install), then `hyperresearch install --global`.
   Never install it yourself, and never fall back to letting every agent search the web on its own.
   **First run in a project writes files there** (`hyperresearch init`): a `.hyperresearch/`
   vault, a `research/` folder, 16 step skills in `.claude/skills/`, and a marked block appended
   to the project's `CLAUDE.md`. Before the first run, tell the user and check the project's
   `.gitignore` covers `.hyperresearch/` and `research/`; after it, show them the CLAUDE.md block
   so they can keep or delete it.
   **Models:** 9 of its 16 agents are pinned to Opus. The light tier calls two of them, one at a
   time (polish auditor, readability recommender), and fans out 3 to 5 Sonnet fetchers per wave,
   so it stays within the 5-at-once cap. The full tier fans out 10 to 12 fetchers at once plus
   Opus critics: say so before starting one.
2. **Run it at the light tier by default** (owner decision 2026-09-25; the full tier runs only when the user names it). Put
   the directive in the prompt, since an explicit directive overrides its auto-routing:
   `/hyperresearch <question>. Use the light tier, inference_depth=surface.`
   The `full` tier (55 to 80 sources, 1.5 to 2.5 h) and `premier` (100 to 130 sources) run only
   when the user asks for them by name; say the time and source count before starting one.
3. **Turn the report into the register.** Take only the statements the user's decision
   depends on (usually 5 to 15), one fact per id, each with its cited source as `docEvidence`.
   Everything else in the report stays context, not a claim.
4. **Verify them with this skill** (spec mode, `document` = the report). hyperresearch already
   checked that each citation supports its sentence; this loop checks the claims against the
   project's code and live state, and attacks them with different-method adversaries. A claim
   whose only support is one web source gets `methodStrength: "doc"` and lands in
   `weakConfirmations` until a second, independent source or a live check backs it.

## Phase 0: the register

A file the loops read from disk and rewrite. One line per claim with an id, the claim, and a
**provenance line** (what was checked, by what method: "verified pg_indexes" and "verified by
reading the migration" look alike in a summary and are worth very different amounts). Sort by
action, not severity: Ship now, Ship soon, Do not do (proposed then refuted, recorded so
nobody proposes it again), Open decisions, Still to verify, Already landed.

## Phase 1: internal consistency (free, do it first)

Contradictions between sections, counts that do not match their contents, an item whose body
refutes its title, stale cross-references, wrong nouns (a column called a table). Fix these
before dispatching, or agents waste calls resolving them.

**Then split every compound claim into single facts.** This is the biggest accuracy lever.
A claim that bundles facts ("11 users, all known; 4 calls from one phone in one city"; three
unrelated sentences under one id) gets checked in part and waved through, or blurred into
PARTLY. Give each fact its own id (R7 becomes R7a, R7b, R7c) and its own line in the register.
Pass them as `claims: [{ id, text, docEvidence }]` so the script shows one fact per line.

**Name each lane's decisive check:** the one question whose answer could change the frame for
every claim in that lane ("these line numbers came from the repo but the bug runs in
production: download the deployed source and diff"). The reader does it first.

## Phase 1b: snapshot once, check once

Every reader asking the database, the API and git the same questions is where the tokens go:
each tool call re-reads the agent's whole context. Measured (2026-09-25, on a real project):
readers working from a checked snapshot averaged 5.2 calls and 0.38 M cache-read tokens,
against 12.9 calls and 1.23 M for verifiers that queried live themselves.

**Find the project's state source, in this order:**
1. A project snapshot script named in the project's CLAUDE.md or skills
   (`grep -rlE "snapshot-live-state|verification-sources|state snapshot" CLAUDE.md .claude 2>/dev/null`).
   Run it.
2. `.claude/verification-sources.json` in the project: run the generic harness
   `python3 ~/.claude/skills/claim-verification-loop/scripts/snapshot.py --out <scratchpad>/state`
   (config format is in the script's header: a list of named read-only commands).
3. Neither exists: **ask the user before any agent touches a live system**. "Is there a
   script or command that pulls the current state for what we are verifying (database,
   deployed services, devices, logs)?" Offer: (a) they name one; (b) you draft a
   `.claude/verification-sources.json` with them from what the repo uses (git, the DB CLI,
   the test command, the deploy CLI), they approve each command, then run the harness;
   (c) code-only: no snapshot, readers use the repo only. Never let every reader query
   live systems on its own.

Then ONE Sonnet verifier checks the snapshot through a DIFFERENT path than the command that
produced it (another client, the MCP instead of the CLI), checks sha256 against the
manifest, and writes `VERDICT.json`. Invalid: re-run the snapshot, not more agents, at most
twice, then stop and tell the user. The Workflow script below does this step.

Never put PII (user emails, IPs, locations) in a snapshot; summarise to counts. Snapshots
stay in the scratchpad: never commit them.

## One profile: accuracy

There is no budget profile (removed 2026-09-26, owner: "I'd rather waste tokens than be
wrong"). Every run: 14-call readers that may take 6 more, a fresh snapshot check, an adversary
on every lane, and the orchestrator re-checks every REFUTED and PARTLY verdict itself.
Approximate weight for 5 lanes: ~1.8M (5 readers + 5 adversaries + verifier).

## Phase 2: fan out

Run `scripts/verify-workflow.js` with the Workflow tool:

```
Workflow({ scriptPath: "<home>/.claude/skills/claim-verification-loop/scripts/verify-workflow.js",
           args: { mode, document, repoRoot, snapshot, summary, verifierChecks,
                   projectRules, loop, previous, registerPath, attempt,
                   lanes: [{ key, decisive, liveAllowed, claims: [{ id, text, docEvidence }] }] } })
```

- Every `agent()` runs on Sonnet (the orchestrator judges, workers read). At most 5 agents per
  stage (readers, adversaries) and at most 5 running at once, via fixed lanes. A `null` agent result is a failure to re-run, never "no findings": check
  `failed` in the result before trusting a short list.
- **Every verdict carries its own test.** Readers return, per claim: `verdict`, `method`,
  `methodStrength` (live, deployed, repo, doc, none), `evidence`, `falsifier` (what evidence
  would have proved the claim wrong) and `falsifierChecked` (whether they looked for it), plus
  `trueValue` on REFUTED or PARTLY (what is true instead). A CONFIRMED with an unchecked
  falsifier, or backed only by a doc, comes back in `weakConfirmations`: treat it as
  unconfirmed and re-attack it next loop.
- **Lanes:** one per evidence source (database, web surface, one code area), at least 3 claims
  each, at most 5 lanes (the script refuses more). Cluster claims that one query answers;
  never put claims from different systems in one lane.
- **liveAllowed:** only for a claim the snapshot cannot hold (a deployed artifact's source, a
  test run). Name the exact command.
- Readers return `NEEDS-LIVE: <query>` for missing facts. Answer them in ONE pull
  (`snapshot.py --only <source>` or one agent), then re-dispatch only those claims.
- The brief is stable-first (rules, snapshot summary, previous verdicts, then the lane's
  claims). Measured: workflow agents do NOT share that prefix through the prompt cache (each
  writes its own first message; parallel agents start before a cache entry exists), so the
  order costs nothing but saves nothing; the saving is fewer calls per agent.

**Evidence order** (state it in every brief): live query > deployed artifact > repo working
tree > committed dump > docs. A snapshot its verifier marked valid counts as a live query for
that run. A doc or skill is a pointer, never evidence.

## Phase 3: the orchestrator adjudicates

Re-run yourself every claim the script lists in `orchestratorMustRecheck` (every REFUTED and
PARTLY), every `challenged` id, and the verdicts that would change
what ships. Three calls you will
actually make:
- **Scope drift:** the reader refuted something the document never claimed. Reject it, say why.
- **Right conclusion, wrong reason:** record both; a true conclusion attached to a false reason
  is lost the next time someone checks the reason.
- **Right refutation, wrong replacement:** falsifying is half the job; say what is true instead.
  (Real case: a reader refuted "prod may not serve main's HTML" because the analytics script
  was not in the live HTML; checking the live JS bundle showed the script IS served, which
  turned a dismissed finding back into a live one.)

## Phase 4: annotate in place

Under each claim, in the register file:
```
C<n> <claim>
   <VERDICT> | <method actually used> | L<n+1>: <what to do differently, or "settled">
```
Verdicts: CONFIRMED, REFUTED, PARTLY, UNVERIFIED (blocked by tooling: attack the blocker
differently next loop), UNVERIFIABLE (no allowed source can ever answer: stop cycling it),
NEVER COVERED (nobody looked: top priority next loop). Unexamined is not the same as fine.

## Phase 5: loops 2 and 3 (cheaper than loop 1)

- Re-run the snapshot with `--prev <loop 1 snapshot>`; `CHANGES.md` lists what moved. A
  settled claim is carried forward, not re-dispatched, unless its evidence is in `CHANGES.md`.
- Re-dispatch only: NEVER COVERED, UNVERIFIED, PARTLY, claims confirmed by one weak method
  (re-derive by a different route), and claims you overruled in Phase 3.
- `previous` in the args gets one line per claim (verdict, method, "attack differently"),
  never the previous agent's full output.
- Adversaries (up to 5, one per reader lane by default, any loop): each attacks a group of
  lanes' verdicts and must name the DIFFERENT method it used (another tool, data source or
  angle); re-running the reader's own check proves nothing. Adversary 1 is also the
  **completeness critic**: it reads the register (`registerPath`) and lists in `neverCovered`
  every claim or part of a claim no verdict covers. Those are the top priority next loop.
- **Loop 3 tests the fixes.** For each proposed fix ask "if I wrote this right now, would it
  work?" Real cases: a `REVOKE EXECUTE` that a default ACL re-grants on the next
  `CREATE FUNCTION`; "normalise once before line N" when the object is mutated between the
  two write sites. Neither is findable by checking facts.

## Stopping

Stop when a full pass leaves no unresolved actionable claim. Do not manufacture findings to
fill a loop, and do not call the result clean because the loop count ran out: list what is
still UNVERIFIED and why.

## Failure modes

| Symptom | What happened | Guard |
|---|---|---|
| "Nothing survived verification" | Agents died on a rate limit; dropped ones read as refuted | Sonnet workers, max 5, `failed` must be empty |
| Loop 2 agrees with everything | Same method, same answer | Annotate METHOD; brief loop 2 to use another |
| A number "reproduces exactly" | Only under an unstated scope | State the scope in the register or withdraw it |
| An agent quotes a doc that changed today | Its injected copy is frozen at session start | Tell agents to read docs from disk |
| Agents answered the user's follow-up question instead of verifying | A mid-run message reached the running agents | Agents ignore it and list it in `ignoredMessages`. The orchestrator answers the user in the main thread, never forwards the question to agents or puts it in args, and relaunches with `args.attempt` + 1 (busts the cache) if any lane answered it |
| One wrong shared number in every brief | A planner estimate or stale doc went into the shared context | Snapshot with exact queries; the verifier spot-checks it |
| The register grows and nothing ships | Verification became the deliverable | Ship the independent "Ship now" items during the loops |
