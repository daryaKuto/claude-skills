---
name: review-panel
description: Use when several reviewers should check the same change, spec, or document independently, or when the same review must sometimes only report (validate) and sometimes also apply fixes (finalize). Routes to code-council (code mode for code, plan mode for specs and design docs) with your lens list, so the panel gets its refuters, Opus chairman and failure handling.
---

# Review panel

> **Usually called through `/proofread`.** Follow `~/.claude/skills/proofread/proof-rules.md`
> (proof, verdict words, Sonnet workers, Opus adjudicators, report location). Where this skill
> and those rules differ, the stricter one wins.

## Overview

This skill is a thin entry point. It does not run its own reviewers. It runs `code-council`
in code mode, or plan mode for a spec or design doc (`~/.claude/skills/code-council/SKILL.md`), with your lenses, so every finding
goes through code-council's batched refuters, its Opus chairman, and its rule that a dead
agent is re-run once and never read as "no findings".

Skip it for a one-line change, a throwaway prototype, or when a deterministic check already
answers the question.

## The pattern

1. **Lint first.** Run a cheap deterministic check (lint, types, schema, missing fields,
   duplicate IDs, placeholders). It catches objective errors free, before any agent spends
   judgment on them.
2. **Pick lenses.** Always one general lens against the artifact's own acceptance criteria,
   plus lenses the risk calls for (security, data integrity, cross-team). Light for a small
   change, full for a high-risk one. Code-council takes them as its optional `lenses` list
   (`[{ key, label, focus }]`) and replaces its default four.
3. **Run code-council** in code mode (plan mode for a spec or design doc) with that list and the target. Workers stay on Sonnet,
   the chairman on Opus, at most 5 agents at once.
4. **Branch on mode.**
   - **Validate:** report only. Never change the artifact.
   - **Finalize:** apply only the fixes a refuter confirmed. Then re-run the lint and the
     project's checks and read the result back to confirm each fix took effect. Then run
     code-council once more on the fix diff, as a fresh review, so the author does not grade its
     own fix. At most 3 fix rounds, then list what is left. Anything
     REFUTED, UNVERIFIED or needing a human call is listed, not applied.

**Stop condition:** code-council returned its report, every lens has a verdict or is listed
as not run, and in finalize mode the re-run checks passed.

## Common mistakes

- Running reviewers sequentially; a reviewer who sees an earlier opinion is no longer independent.
- Treating an errored or timed-out reviewer as if it found nothing.
- Applying a fix nobody tried to disprove.
- Calling a fix done without re-running the checks.
- Running the full panel on every small change instead of scaling to stakes.

## Source

Adapted from `skills/bmad-architecture/references/reviewer-gate.md` in
`https://github.com/bmad-code-org/BMAD-METHOD` (commit `1b59caa7f96459fda6750c225a9330283e108fd6`;
own words only, see that repo's LICENSE). Kept: check-first order and the finalize-vs-validate split.
