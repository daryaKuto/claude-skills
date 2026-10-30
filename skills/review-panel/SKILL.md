---
name: review-panel
description: Use when several subagents are about to review the same change, spec, or document and the reviews must be independent, when full review write-ups from multiple reviewers are filling up the coordinator's context, or when the same review step must sometimes only report (validate) and sometimes also apply the obvious fixes (finalize).
---

# Review panel

> **Usually called through `/proofread`.** Follow `~/.claude/skills/proofread/proof-rules.md`
> (proof, verdict words, Sonnet workers, Opus adjudicators, report location). Where this skill
> and those rules differ, the stricter one wins.

## Overview

Run a cheap deterministic check first, then send the artifact to several
reviewer subagents in parallel, each with a different lens (a distinct angle
or persona the reviewer applies). Every reviewer saves its complete write-up
to a separate file and reports back only a short verdict, so the
coordinator's context stays small.

## When to use

Use when an artifact (a diff, a spec, a design doc) needs checking from more
than one angle, reviewers must stay independent, or the gate must sometimes
fix clear issues itself (finalize) and sometimes only report (validate).

Skip it for a one-line change or a throwaway prototype, or when a
deterministic check already answers the question.

## The pattern

1. **Run a deterministic check first.** A lint or static check catches
   objective errors (missing fields, duplicate IDs, placeholders) free,
   before any agent spends judgment time on them.
2. **Pick lenses.** Always include a general reviewer against the
   artifact's own acceptance criteria, plus lenses the risk calls for:
   security, data-integrity, cross-team. Scale to stakes: light for a
   small change, full panel for a high-risk one.
3. **Dispatch every lens as a separate parallel subagent** (Sonnet, at most
   5 at once; batch any extra lenses). Each saves its
   complete review to a separate file in a scratch location (not the
   deliverable folder), then sends back a short verdict, a few top
   findings and the file path, nothing more. The coordinator never loads
   every full review.
4. **Merge the summaries into one tiered list.** One sentence for the
   overall verdict, then critical and high findings in full; roll the
   rest into a tail line ("plus N more, see file"). Tag each finding
   autofix, discuss, defer, or ignore.
5. **Branch on mode.** Finalize applies the autofix findings and surfaces
   only what needs a human call. Validate only reports, never changes the
   artifact.

**Stop condition:** every lens has a verdict or a confirmed error (not a
clean pass), and the merged list exists.

## Quick reference

| Step | Runs as | Returns |
|---|---|---|
| Deterministic check | a script | pass/fail list |
| Panel review | N subagents, max 5 at once | 1 file + verdict each |
| Merge | coordinator | one tiered list |
| Apply | finalize only | autofix fixes |

## Common mistakes

- Running reviewers sequentially instead of in parallel; a reviewer who
  sees an earlier opinion is no longer independent.
- Returning a full write-up instead of a short verdict, undoing the point
  of writing to file.
- Treating an errored or timed-out reviewer as if it found nothing.
- Running the full panel on every small change instead of scaling to
  stakes.

## Source

Repo: `https://github.com/bmad-code-org/BMAD-METHOD`, commit
`1b59caa7f96459fda6750c225a9330283e108fd6`. License: the repo LICENSE file
contains MIT text plus an added trademark notice; GitHub reports
NOASSERTION because of that clause; treated as own-words-only here. File
read: `skills/bmad-architecture/references/reviewer-gate.md`. Adapted:
check-first order, parallel-lens file-write pattern, four-way triage,
finalize-vs-validate split.
