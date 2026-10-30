---
name: grow-test-coverage
description: Use when an agent is generating or auto-extending tests for existing code and needs an automatic rule for keeping or discarding each candidate test, rather than the agent's own judgment; when generated tests pass but do not actually exercise the code they claim to cover; when a coverage target (a percentage) must be reached by real, re-measured progress instead of the agent's own claim; or when a test-generation loop needs a concrete stop condition instead of running until the agent decides it is done.
---

# Grow test coverage

## Overview

Coverage is the share of source lines a test suite runs, measured by a coverage tool from a report file, not guessed. Core rule: keep a generated test only if it passes and the real report shows it covered a new line. Otherwise discard it and retry.

## When to use

- An agent proposes candidate tests one at a time and needs a pass or fail rule for each.
- A numeric coverage target exists and progress must be verified, not asserted.
- A generated test might pass while touching nothing new (no real assertion, or a duplicate).

Skip for: grading a whole agent session; a one-time checklist like build, lint, test, security scan (runs once, no rollback); a stack with no coverage tool.

## The pattern

1. **Baseline.** Before generating anything, run the real test command once, parse the real coverage report, record the starting number.
2. **Generate one candidate.** One test at a time, never a batch, so credit is traceable.
3. **Insert and run for real.** Add the candidate, run the same real command. Never substitute a mock runner or mocked coverage tool.
4. **Fail path.** Non-zero exit: discard, restore the file's prior content, log why.
5. **Coverage check.** Passing run: re-parse the real report, compare to the current baseline.
6. **Accept or reject.** Keep only if a previously missed line is now covered. Flat or dropped coverage fails too: discard and restore. On accept, the new number becomes the next baseline.
7. **Stop condition.** Repeat from step 2 until the target is reached or an iteration cap (optionally a time cap) is hit. Hitting the cap is a normal exit, not an error.

This satisfies a no-mocking rule by construction, and composes with fail-before-fix: reproduce the bug first (must fail), then confirm the fix passes and raises coverage.

## Quick reference

| Step | Trigger | Action |
|---|---|---|
| Baseline | before any candidate | run real command, parse real report |
| Fail | exit code != 0 | discard, restore file |
| No gain | exit 0, coverage flat/dropped | discard, restore file |
| Accept | exit 0, coverage rose | keep, baseline = new coverage |
| Stop | target reached OR cap hit | end loop, report final coverage |

## Common mistakes

- Trusting the model's claim a test "should" help, instead of re-parsing the real report.
- Comparing to the original baseline, not the latest accepted one, so a later candidate gets credit for someone else's gain.
- Skipping restore-on-reject, leaving a broken test behind.
- No iteration or time cap, so an unreachable target loops forever.

## Source

Repo github.com/qodo-ai/qodo-cover, commit adcf55baba40e8fbf8a84e68b70d08bef1e2b9c9, license AGPL-3.0 (no permissive grant, wording here is original, nothing copied).
Read: `cover_agent/cover_agent.py`, `cover_agent/unit_test_validator.py`, `cover_agent/coverage_processor.py`, `docs/repo_coverage.md`.
Adapted: generalized a Python CLI tool's control flow into a language-agnostic keep/discard rule, paired with no-mocking and fail-before-fix, neither of which the source states.
