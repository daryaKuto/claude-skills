---
name: track-review-findings
description: Use when the same review, audit, or automated check runs repeatedly against content that keeps changing (a PR re-reviewed on every push, a recurring security scan, a repeated lint or test-quality pass) and unchanged issues get re-flagged as noise on every round, fixed issues vanish from the report with no confirmation they were actually fixed, or a regression that was already reported once slips back in without anyone noticing it returned.
---

# Track review findings

## Overview
When a check repeats against changing content, do not treat each run's output as a fresh list. Give every finding a stable identity, carry a small state record forward, and reconcile: add new findings, leave matched ones alone, resolve missing ones only when a full check just ran, and reopen anything that comes back after being resolved.

## When to use
- A review, audit, or scan repeats on the same evolving target (PR pushes, nightly scans, fix loops).
- Unchanged issues should stay quiet instead of re-alerting every round.
- You need to know what was actually fixed, not just what went undetected this time.

Skip this for a one-shot check that never runs again on the same target, or when there is nowhere durable to store state between runs (see Common mistakes).

## The pattern
1. **Fingerprint, don't diff text.** Derive each finding's ID from stable fields (file path plus a whitespace-normalized, lowercased body), never from exact wording or line numbers. A rewrap or a shifted line must not mint a new ID.
2. **Persist state somewhere durable and visible.** Store `{finding_id, state: ACTIVE|RESOLVED, first_seen, last_seen, resolved_at?, reopened_count}` per finding. With no database, embed it as a hidden, versioned marker inside the artifact people already read (an HTML comment in a PR comment) and parse it back next run.
3. **Reconcile every run:** current-only findings become ACTIVE; matched findings get `last_seen` refreshed, flipping RESOLVED back to ACTIVE with `reopened_count += 1` if they returned; previous-only findings become RESOLVED, but only when this run fully covered the same scope and the target changed (compare head SHAs), otherwise leave them ACTIVE since a partial run proves nothing. Report only what changed state.
4. **Cap what you keep.** Bound stored RESOLVED entries (for example, 20 most recent); never cap ACTIVE ones.
5. **Stop condition:** every current finding is matched or added, every previous finding has an explicit verdict, and the new state is written back to where it was read from.

## Quick reference
- New -> ACTIVE, `first_seen = now`.
- Still present -> keep, refresh `last_seen`.
- Was RESOLVED, reappeared -> ACTIVE, `reopened_count += 1`.
- Missing, full fresh check -> RESOLVED.
- Missing, partial or unchanged check -> leave ACTIVE.
- Unchanged this round -> do not re-report.

## Common mistakes
- Fingerprinting on exact text or line number orphans a finding's history on a harmless rewrap or line shift.
- Marking something resolved without confirming full scope and a changed target; a narrow or failed run then reports false fixes.
- No durable state at all: every run reinvents the list, nothing is ever confirmed resolved.
- Unbounded resolved history drowns the active list over time.

## Source
Repo: https://github.com/The-PR-Agent/pr-agent, commit 1f11725b4d96afbaad8ed956afd074ecf4642426, license MIT.
File read: `pr_agent/algo/review_finding_state.py` (fingerprinting, state marker parse/serialize, `reconcile_review_findings`).
Adapted: generalized pr-agent's per-comment ACTIVE/RESOLVED reconciliation into a project-agnostic pattern. Wording rewritten, not copied, per MIT attribution.
