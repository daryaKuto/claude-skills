---
name: agent-orchestration
description: Use when dispatching subagents, writing a subagent brief, choosing a model for an agent, planning a fan-out (many agents working in parallel), or designing a workflow script that runs agents in stages. Triggers on a fan-out that reports "nothing found" while some agents errored, briefs that make agents re-discover facts you already have, many agents re-querying the same live system, a run whose agent count nobody checked before launch, a fix step that hands one writer a whole review, or a brief that says "be concise".
---

# Agent orchestration

## Overview

One session model thinks. Many cheaper workers do the typing. This skill covers who does what, how to write a brief that does not burn tokens, how to share live facts across agents without paying for them many times, and how to keep a fan-out honest. It is about the run, not the domain. See loop-until-verified for the loop that wraps repeated checks, and prompt-caching for brief order.

## When to use

- You are about to dispatch two or more agents, or write a workflow script.
- A brief is being written and you want the answer back in one read.
- Several agents would query the same database, API or repo.
- A review produced findings and someone must now fix them.

Do NOT use for a single lookup you can do in three tool calls. Do it yourself.

## 1. Who does what

| Role | Model | Does |
|---|---|---|
| Orchestrator (the session) | Strongest available | Decides what to investigate and why. Reads the returned evidence, makes the call, owns the final judgement. |
| Worker (every fan-out agent) | A mid-tier model (for example Sonnet) | One scoped task: search, read, verify, restyle. Returns evidence, not decisions. |
| Adjudicator (one per stage) | Strongest available | Merges, judges or synthesizes other agents' output. Does not search or build. |

Rules:

- Fan-outs run as a script (Claude Code's `Workflow` tool, when your setup has it; otherwise send agents by hand in batches of 5), not as ad hoc hand-sent agents. Set the worker model on every agent call in the script, including finders, verifiers and synthesis.
- At most 5 agents at once. Use lanes (5 queues of items, each worked through in order, the 5 queues running in parallel).
- A null, errored or timed-out agent is a failure to re-run. It is never "no findings". Before you believe a zero, check the error count is zero.
- A one-off lookup may use a single agent call, still on the worker model.

Why: a fan-out on the top model hits rate limits and fails silently. In a measured case, every verifier died on a rate limit. The workflow dropped the unverified candidates exactly as if they had been refuted, and reported "no findings survived". Four real bugs sat in the candidates nobody examined. Re-running on workers gave 13 agents, 0 errors and 3 confirmed defects.

The strong model's value is judgement: is the finding real, is the design right, what do we do. Reading a diff or grepping a symbol is worker work.

## 2. The brief contract

The model sets the price per token. The brief sets how many tokens. Paste these four parts into every brief. Do not paraphrase them.

```
1. PRE-LOADED CONTEXT. Do NOT re-derive these. They are given:
     <file:line cites, symbol names, constants, earlier findings you already have>
   Start from these. Do not search for what is stated here.

2. RETURN THE ANSWER, NOT THE EVIDENCE TRAIL.
   Per item: a verdict plus `file:line`. Cite line numbers. Do NOT paste code.

3. READ NARROWLY.
   Use offset and limit. Never read a file over ~300 lines in full.
   If a search returns more than 30 lines, narrow the pattern. Do not page through it.

4. BUDGET: ~15 tool calls.
   If you cannot finish, return what you have plus one line on what is missing.
```

Also:

- Scope the search space: "look ONLY in `src/payments/`". Agents search the whole repo by default.
- One task per agent. Two questions in one brief double the exploring and halve the focus.
- Lower the reasoning effort for mechanical work (extract, rename, re-check a cite). Keep it higher where reasoning is the deliverable.
- The write-up rules (tone, no filler) go into any brief that produces a document.

| Do not write | Write instead |
|---|---|
| "Be concise." / "Don't waste tokens." | A countable rule an agent can check: a line cap, a tool-call budget, "cite, don't paste". |
| "Explore the codebase and tell me about X." | Name the directories and files, and what you already know. |
| "Read `foo.tsx` and summarise it." | "What does `foo.tsx` render in the offline case? Cite lines." |
| The same background question to three agents | Establish it once, pass it down in part 1. |

The test: if an agent's return can go into a plan or review unedited, the brief was right. If it is a wall of quoted source, fix the brief, not the summary.

In a measured case, one review fan-out used hundreds of thousands of subagent tokens across 200 tool calls. Most went to agents re-finding facts the orchestrator already had and pasting files back.

## 3. Snapshot once, verify once, read many

Many agents re-querying one live system waste tokens and give different answers. Pull the facts once into a file, check that file once, and make everyone else read it.

```
Step 0  orchestrator, shell, no agent: run a snapshot script -> <scratch>/state/<UTC stamp>/
Step 1  ONE verifier agent checks the snapshot through a different path than the script
Step 2  the fan-out: every agent reads the snapshot. Nobody else queries the live system.
```

What a snapshot script should do (write it per project, keep it small; `claim-verification-loop/scripts/snapshot.py` in this repo is a working example):

- Read-only by construction: SELECT-only database queries, GET-only HTTP calls, `git grep` and `git show` by ref (never check out).
- Redact secrets and personal data before writing. The output stays in the scratch directory. Never commit it or paste it in a PR or chat.
- Write one JSON file per source, a one-screen `SUMMARY.md`, and a `manifest.json` with status (OK or FAILED), pull time, a checksum and any error per section.
- Exit non-zero if any section failed, and still write the others. A failed section is never "no data".
- Take a `--prev <old snapshot>` option that writes `CHANGES.md`: every JSON path that changed.
- Take a `--sections` option to refresh one source alone.

Outline:

```
pull(source) -> write <out>/<source>.json, record status + sha256 in manifest
for each source: pull, catch error -> manifest FAILED + message
write SUMMARY.md (counts, key lists), CHANGES.md if --prev given
exit 3 if any FAILED
```

Verifier brief (one agent, paste it):

```
You check a live-state snapshot before other agents rely on it. Read-only.
SNAPSHOT: <path>. Read manifest.json and SUMMARY.md first.
1. Every section the task needs is OK. Stop on any FAILED section.
2. Freshness: structure data is valid for the run unless something deployed after
   pulled_at. Fast-changing data (status, counts) older than a few minutes is stale: say so.
3. Each section's checksum matches the manifest.
4. Spot-check through a DIFFERENT path than the script: a few exact counts, one config
   value, one definition.
5. Write VERDICT.json: {"valid": bool, "checked": [], "mismatches": [], "stale_sections": []}.
   Return that JSON only.
BUDGET: ~12 tool calls.
```

If the verdict is not valid, re-run the script (not more agents) and verify again, at most twice. Then stop and tell the user what does not match.

Reader rule (paste into every fan-out brief, inside the stable prefix):

```
LIVE STATE: read it from <snapshot path> (SUMMARY.md is included below; use jq for detail).
Verified at <time>. Do NOT query the live system. Code on disk you may grep directly.
If a fact is missing, write NEEDS-LIVE: <exact query> and move on.
Cite snapshot evidence as <file>:<jq path> (pulled <time>).
```

Collect every NEEDS-LIVE line after the run, answer them in one pull, then re-dispatch only the items that needed them.

A snapshot pays for itself from about 2 readers. Agents that read it need few tool calls, and every call re-reads the agent's whole context, so fewer calls is the main saving.

## 4. Loops 2 and 3 cost less than loop 1

- Re-run the snapshot with `--prev`. Re-dispatch a settled claim only if its evidence path appears in `CHANGES.md`. Otherwise carry the verdict forward.
- Loop N re-dispatches only claims still unverified or plausible, claims whose evidence changed, and claims where you overruled a verdict.
- The loop N brief carries one line per claim from loop N-1: verdict, method, and an "attack differently" note. Never the previous agent's full output.
- Hostile verification is for high and medium findings. Spot-check low ones yourself.
- Cap fix rounds at 3. Whatever the third review still finds, fix yourself or list as open.

## 5. Size the run before you launch

- Count agents first: items x stages x loops. Tell the user the number before any run over about 10 agents, and propose a smaller shape.
- Batch small items. One agent can take several items that share a source.
- Each agent has an entry cost: its first call loads a large system prompt and brief before any work. For small readers that is half their cost. Prefer fewer, fuller lanes (at least 3 claims each) over one agent per claim.
- In a measured case, a plan of one editor, one reviewer and two fix rounds per file came to about 70 agents. It was stopped at 22 for cost. Counting first would have caught it.
- Measure after the run: per-agent calls and cache reads from the transcripts (`claim-verification-loop/scripts/run-cost.py` reports both). Measure before cutting anything.

## 6. Brief order and the prompt cache

Build the shared prefix once as a constant in the script, and put the per-item task last. The prefix holds the four-part contract, hard stops, the reader rule, the snapshot summary and shared facts. No item names, timestamps or counters inside it. Inlining the summary also saves each agent a read call.

Do not count on the cache across parallel agents. In a measured run, agents started before any cache entry existed, so each wrote its own first message fresh even with a byte-identical prefix. Stable-first order costs nothing, so keep it. The saving you can rely on is fewer calls per agent.

## 7. Fix rounds: never one writer with the whole review

"Apply the review's fixes" is three phases, at most 5 agents each.

1. **Read-only first.** Every critical, high or medium finding without a check that ran something (a search, a test, a one-line script, a count; re-reading prose does not count) gets 1 or 2 refuters at the reviewed commit. Unverified rows go to settlers (read-only agents that settle one open point each) that return SETTLED, TEST or STILL UNVERIFIED with a cite. Only findings that hold reach the writer. Log the rest as not applied.
2. **One writer per file**, about 15 to 25 calls. Paste into its brief:
   - Find each spot by quoting nearby text, never by a review line number. Edits shift lines.
   - If a fix needs a choice nobody has made, do not decide it. Add it to the open questions with options, pros and cons and a recommendation.
   - If two fixes conflict, apply neither and report both.
   - Return a list of every decision you made that neither the review nor the user made.
   - A fresh agent will re-review your output with checks you do not see.
3. **Fresh re-review** plus 2 to 5 held-back checks (checks the writer never sees; defined below).

Held-back checks: the orchestrator writes them from the critical findings (for example "run the secret-matching regex against every new secret name") and keeps them out of the writer's brief. A writer that sees the checks tunes to them. A pass on cases it never saw is the real pass.

Why: in a measured case, one writer got 1,100 lines, 33 fixes and 60 calls in one brief. It applied findings no second check had confirmed and made two changes nobody asked for.

## 8. Trap: a subagent's project instructions are frozen

A subagent gets the project instruction file (such as CLAUDE.md) as it stood when the session began. If you rewrite that file mid-session, later agents still see the old text and will verify against it. In a measured case, a file cut from 597 to 109 lines was still quoted at full length, and an agent wrote a claim into a doc that the file no longer made.

- When a dispatch depends on what a doc says now, tell the agent to read it from disk and that its in-context copy may be stale.
- Never accept "file X says Y" from context alone. Require a grep or sed cite taken during the task.
- After a mid-session rewrite, put the new facts in the brief's pre-loaded context.

## 9. Writing a subagent brief

A checklist for the brief itself. Each line has its reason.

- **Stable-first order.** Shared rules and context at the top, the task-specific ask at the bottom. Repeated briefs then share a prefix and can reuse the prompt cache.
- **Paste the four parts, do not paraphrase them.** Pre-loaded context (facts and `file:line` cites you hold), return the answer not the evidence trail, read narrowly (no file over ~300 lines in full), and a budget of ~15 tool calls (if stuck, return what you have plus what is missing). Paste the hard stops and your own writing rules too. Agents do not reliably inherit rules you only mention.
- **Set the model on every call** (the worker model for workers). A default can silently pick the expensive model and hit rate limits.
- **One scoped job per agent.** Keep research (read-only, safe in parallel) apart from writing. When several edits hit one file, use a single writer, so two agents never overwrite each other.
- **Check findings before acting on them.** Anything not yet independently refuted gets a second check first. Apply only confirmed items and report the rest as not applied, with the reason. An unchecked finding can be wrong.
- **Locate edits by a quoted anchor, or apply them bottom-up.** Line numbers drift as edits land.
- **No silent decisions.** A choice the brief did not settle goes back as an open question with options and a recommendation. The worker never decides it.
- **Conflicts: apply neither, report both.** A guess between two fixes hides a real disagreement.
- **Plan the review before dispatch.** The worker never approves its own output. Pick 1 or 2 held-back checks it never sees, and have a fresh agent run them afterwards.
- **Ask for a return you can check.** Per item FIXED, NOT FIXED or UNVERIFIED with `file:line`, plus the self-checks it ran and their output. A bare "done" proves nothing.

## Quick reference

| Question | Answer |
|---|---|
| Who thinks, who types? | Orchestrator thinks, workers type, one adjudicator per stage judges |
| Max agents at once? | 5, using lanes |
| An agent returned null? | Re-run it. Never count it as clean |
| Many agents need live facts? | Snapshot once, verify once, all read the file |
| Loop 2 or 3? | Re-dispatch only unsettled or changed claims |
| Run over about 10 agents? | Tell the user the count and a smaller shape first |
| "Apply the review"? | Refute first, one writer per file, fresh re-review with held-back checks |
| Fix rounds? | At most 3 |

## Common mistakes

| Mistake | Fix |
|---|---|
| Believing "no findings" without checking agent errors | Confirm the error count is zero |
| Letting the top model run the fan-out | Workers on the mid-tier model, one adjudicator on the top |
| "Be concise" in a brief | A line cap, a call budget, "cite, don't paste" |
| Every agent queries the live system | Snapshot, verify, read |
| Re-running every claim in loop 2 | Re-dispatch only changed or unsettled claims |
| Giving the writer the held-back checks | Keep them with the orchestrator |
| Raising the fix-round cap mid-run | Stop at 3 and list what is left |
