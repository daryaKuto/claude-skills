---
name: review-before-merge
description: Use when an agent-produced branch is ready to merge and needs a check from someone other than its author; when the only evidence a change works is "tests passed" with no fresh rerun; when a review might run build or test commands in a shared checkout and move someone else's HEAD (the commit a branch currently points to); when a failing test needs to be told apart from one that was already broken before the change; or when nobody can say, from a stored record rather than a guess, exactly which commit was reviewed and who approved the merge.
---

# Review before merge

## Overview

A branch is not ready to merge until a reviewer with fresh context reruns every check from scratch, in an isolated copy of the repo, against a pinned base and head commit. Merging is a separate step with its own stored record.

## When to use (and when NOT)

Use before merging a branch an agent wrote, when the only proof is a green test run, or when review commands might move someone else's HEAD (the commit a branch points to) in a shared checkout.

Skip for docs-only diffs or trivial changes. Not about running several reviewers at once (review-panel) or requesting a review (superpowers's requesting-code-review): this is one review, one branch, before merge.

## The pattern

1. **Pin the scope**: repo, base SHA (where the branch started), head SHA (last commit). A later rebase or force-push must not change what gets reviewed.
2. **Isolate**: add a git worktree (a second copy of the repo, own branch) at head SHA: `git worktree add <path> <head-sha>`. Never `checkout`/`switch` the shared workspace.
3. **Use fresh context**: a different session than the author, ideally a different model.
4. **Rerun everything for real**: build, lint, typecheck, full test suite, in the worktree, against real dependencies, no mocks. For UI, drive the app: golden path plus one edge case, screenshot or log as evidence.
5. **Classify every failure**: signal is touching a changed file; proof is rerunning suite on base SHA in a second worktree. Fails both = pre-existing; fails only head = regression.
6. **Name gaps; back every finding with evidence**: `file:line` plus a reproducing command, or UNVERIFIED.
7. **Report, then stop**: never merge your own review; remove the worktree once saved elsewhere.
8. **Merge separately, later**: record head SHA, review, approver, timestamp. Merge command success is not that record.

**Stop condition:** every changed file has a pass/fail verdict with a command behind it, gaps are named, and any merge has a stored record.

## Quick reference

| Step | Rule |
|---|---|
| Scope | Base + head SHA, pinned |
| Isolation | `git worktree add`, never shared HEAD |
| Reviewer | Fresh context, no mocks |
| Regression | Fails head, passes base (confirm by rerun) |
| Evidence | `file:line` + command, or UNVERIFIED |
| Merge | Separate step, stored record |

## Common mistakes

- Reviewing "the current branch" instead of a pinned SHA: rebase changes what was checked.
- Calling a test a regression from file overlap alone, without rerunning on base.
- Running review commands in the shared checkout, moving someone else's HEAD.
- Skipping "could not verify" instead of naming the gap.
- Treating a merge command's success as the audit record.

## Source

Repo: https://github.com/AnandChowdhary/continuous-claude, commit b9d8ccf9343905d33a1296583114e3326fe102d3, MIT. Read: `README.md`, `continuous_claude.sh` (grepped, reviewer prompt near line 74). Adapted: diff-scoped review, real checks, app walkthrough with screenshots, "could not verify" section, reviewer never commits, review on a different model.

Repo: https://github.com/mikeyobrien/ralph-orchestrator, commit edc2b3268c9bd0c08a12c8193a7ace7ab2789261, MIT. Read: `ralph.reviewer.yml` (413 lines: `scoper` 30-107, `verifier` 108-263, `synthesizer` 337+, plus `core.guardrails`). Adapted: worktree isolation from `scoper`; `verifier`'s technique of correlating failing tests against `git diff <base> --name-only` as a first-pass signal; cleanup from `synthesizer`; evidence rule from `core.guardrails`. Own addition, not in source: rerunning the suite on base to confirm pre-existing failures; source never does this.

Repo: https://github.com/BloopAI/vibe-kanban, commit d5cbb5380fa0b32e98ef9b8d987f63decce4be3a, Apache-2.0. Read: `crates/executors/src/actions/review.rs`, `crates/db/src/models/merge.rs`. Adapted: review context pinned to repo id plus exact base SHA (one entry per repo, multi-repo changes); persisted, typed merge record (direct or PR, commit/PR, target branch, timestamp) as source of truth for "is this merged".
