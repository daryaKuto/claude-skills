---
name: loop-until-verified
description: Use when building or running an autonomous agent loop that revises work over iterations, a coding loop, a Ralph-style loop (an agent that re-runs itself against a state file until an external check passes), a revise-and-retry loop graded against a rubric, or a job that can be retried after failing or being interrupted. Triggers on an agent that keeps declaring itself "done" while checks still fail, a loop with no iteration cap or cost cap, a loop that cannot be redirected mid-run without restarting it, a retry that overwrites or silently drops leftover changes from a failed attempt, or work that only proves itself on the cases it was tuned against.
---

# Loop until verified

## Overview

A loop step is done when an external check says so, not the agent. Bound it with a hard iteration cap plus a time or cost cap for long runs, and let it exit only on a check it cannot game. This skill covers what wraps a grading loop: caps, the anti-gaming exit, state and steering files, retry safety. See santa-method (Phase 2 to 4) for the loop itself, proofread (claim-verification-loop underneath) for repeated checks over a claim register.

## When to use

- An agent loop runs several iterations with no stated stop.
- The agent doing the work would otherwise also judge when it is finished.
- The loop can fail or be interrupted and someone retries it.
- The loop runs unattended long enough to need mid-run redirection.

Do NOT use for a one-shot task, or a call a human reviews right after. This does not judge whether the goal itself is right, only whether the checks passed.

## The pattern

1. **Set caps before starting.** `max_iterations` (default 5 to 10), plus a time or cost cap for long runs. No stop condition besides a pass.
2. **Make the exit an external check.** Named commands exiting zero, a checklist fully ticked, or a rubric graded by a separate grader decide, never the agent's own claim. Reject a check that always passes.
3. **Every failing gate hands back the exact next fix**, not "try again": name the item and the command to rerun.
4. **Keep progress in a state file**, re-read every iteration, one change per iteration, saved before the next.
5. **Add an optional steering file.** Read it once per iteration, splice it in, then clear it. Never block on it.
6. **On retry**: name the run, check the tree for leftover changes, require an explicit keep-or-discard decision. A cancelled retry is its own outcome, not an error. Skip only for a genuinely idempotent call (same result whether run once or twice, no stacking side effect).
7. **After a pass, run held-back cases** the loop never saw, graded the same way. A failure returns to step 3.
8. **Stop condition:** every gate passes, including held-back cases, or the cap is hit. At the cap, escalate with what fails. Never raise the cap mid-run.

## Quick reference

| Question | Answer |
|---|---|
| Who decides "done"? | An external check, never the agent |
| What stops a runaway loop? | An iteration cap plus a time or cost cap |
| Where does progress live? | A state file, re-read each iteration |
| How is a loop redirected? | A steering file, read then cleared |
| What does a retry need? | Run identity, a leftover-change check, keep-or-discard |
| What proves it generalizes? | Held-back cases run after the check passes |

## Common mistakes

- No cap, or "iterate until it's good": never stops.
- The agent's own summary substituting for running the check.
- A gate that always exits zero: hides failure behind green.
- An "on_fail" message saying "fix it" instead of the exact command.
- A minimum-iteration floor with no ceiling: still runs forever.
- Raising the cap mid-run instead of escalating: unbounded by another name.

## Source

- https://github.com/mikeyobrien/ralph-orchestrator, commit `edc2b3268c9bd0c08a12c8193a7ace7ab2789261`, MIT. File: `ralph.yml` (`backpressure.gates`, `core.guardrails`). Adapted: gate-plus-on_fail-plus-anti-placeholder (steps 2 to 3), generalized from its Rust fmt/clippy/test trio.
- https://github.com/Th0rgal/open-ralph-wiggum, commit `7559f267b227d74d82776048697615536c2a6b2a`, MIT. Files: `ralph.ts`, `completion.ts` (`tasksMarkdownAllComplete`, `checkTerminalPromise`, `containsPromiseTag`). Adapted: parser-veto (step 2) and read-inject-clear steering (step 5), generalized beyond this repo's file names.
- https://github.com/alirezarezvani/claude-skills, commit `19392f7a08264ed00486a251f5b2098321771f94`, MIT. File: `agent-launcher/skills/grade-iterate/SKILL.md`. Adapted: the held-back-case check after a pass (step 7).
- https://github.com/BloopAI/vibe-kanban, commit `d5cbb5380fa0b32e98ef9b8d987f63decce4be3a`, Apache-2.0. File: `packages/web-core/src/shared/hooks/useRetryProcess.ts`. Adapted: confirm-then-retry with keep-or-discard and a non-error cancel (step 6).
- The iteration-cap-plus-cost/time-cap pairing (steps 1, 8; the open-ralph-wiggum draft above used a floor with no ceiling) and the santa-method/verification-loop cross-references are this skill's own additions.
