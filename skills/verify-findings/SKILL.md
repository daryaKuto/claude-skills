---
name: verify-findings
description: Engine behind /proofread (start from /proofread unless this engine is named). Use when a review, audit, or investigation has produced a finding (a bug, vulnerability, root cause, or claim) that someone is about to act on, and the finding came from one pass of reasoning with no independent check; when a single agent or reviewer is about to mark something "confirmed" based on its own analysis; when a report lists findings with no file:line evidence per finding; when a finding could be a false positive or a false negative; when a change ships with a spec, ticket, or PR description that makes checkable claims; or when a diff deletes or replaces meaningful code and nobody has confirmed the old behavior was re-implemented or dropped on purpose.
---

# Verify findings

> **Usually called through `/proofread`.** Follow `~/.claude/skills/proofread/proof-rules.md`
> (proof, verdict words, Sonnet workers, Opus adjudicators, report location). Where this skill
> and those rules differ, the stricter one wins.

## Overview
A finding, or a claim in a spec, is not true because it sounds plausible. Split it into conditions that must all hold, prove or disprove each alone with evidence, and combine with a strict AND.

## When to use
Use after a review, audit, or root-cause pass produces a finding that will change code, block a merge, or drive a decision: one pass with no separate check, a spec with checkable claims, or a diff removing meaningful code.

Skip the finding-generation pass itself, hunting or brainstorming: a search, not a check. Skip low-stakes, reversible claims; skip claims with nothing written; skip deletions when the diff only adds code.

## The pattern
1. State the claim: what is broken, where (file:line), and what would make it matter.
2. List the conditions that must all hold, each checkable alone: trigger reachable, bad state possible, nothing blocking it, and it matters.
3. Check each condition alone. Each condition goes to its own Sonnet worker, never the agent that produced the finding, under proofread's proof rules. Record evidence: a file:line or a command's output. Do not skip one because earlier ones passed.
4. Ask before the verdict: proof, or a pattern that looks wrong? A dismissal needs proof equal to a confirmation's.
5. Combine: CONFIRMED if every condition passed, REJECTED if any failed, UNVERIFIED if one could not be checked. Never round UNVERIFIED up to a pass.
6. Also check the two claims people forget, even on a careful review:
   - **The change's own description.** Treat the spec or PR description as a claim to disprove, not evidence. Read the code, not a comment that repeats it. Verdict: true or falsified, with the file:line that settles it.
   - **Every deleted or replaced code chunk** (skip renames and whitespace-only edits). Treat it as lost behavior until proven otherwise: did it hold logic or a promise other code relied on, and was that re-established or retired on purpose? If neither, that is a finding: rate confidence, since intent is inferred.
7. Stop condition: every condition has a pass, fail, or UNVERIFIED verdict, and the verdict follows only from combining them.

## Quick reference
| Step | Question |
|---|---|
| Decompose | What must all be true? |
| Check | True alone, with evidence? |
| Self-check | Proof, or a pattern? |
| Combine | AND: one fail kills it, one gap is UNVERIFIED |
| Claims | Code match the spec? |
| Deletions | Re-implemented, or dropped on purpose? |

## Common mistakes
- Treating checks as a vote, not a strict AND.
- Reusing the finding pass to also confirm it.
- Giving a dismissal less evidence than a confirmation.
- Accepting an echoing comment as proof of a claim.
- Flagging a rename or whitespace edit as a deletion finding.

## Source
Repo: https://github.com/trailofbits/skills, commit 32e34f8173796e3566a51aee877dc96bc5191f64.
License: CC-BY-SA-4.0 (share-alike). Own wording; this note is the attribution.
Files read: plugins/fp-check/README.md, plugins/fp-check/agents/exploitability-verifier.md, plugins/fp-check/skills/fp-check/references/standard-verification.md, plugins/fp-check/skills/fp-check/references/gate-reviews.md.
Adapted: fp-check's six-gate review and self-check, generalized into a decompose-and-AND-gate pattern.

Repo: https://github.com/bmad-code-org/BMAD-METHOD, commit 1b59caa7f96459fda6750c225a9330283e108fd6.
License: LICENSE file is MIT text plus an added trademark notice; GitHub's detector reports NOASSERTION. Treated as unclear: own words only, nothing copied verbatim.
Files read: skills/bmad-build-auto/references/claims-check.md, skills/bmad-build-auto/references/deletion-check.md.
Adapted: the claim-as-testimony framing and deletion-regression check, generalized away from BMAD's "Edge Case Hunter" agent and its JSON schema.

Skill author's own addition, from neither source: the three-way CONFIRMED / REJECTED / UNVERIFIED verdict, and merging both patterns into one skill.
