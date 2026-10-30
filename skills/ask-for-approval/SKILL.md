---
name: ask-for-approval
description: Use when an autonomous agent workflow reaches a point only a human can decide, such as approving a plan, choosing merge or discard, signing off on verification, or accepting a scope change, and the workflow runs unattended, spans multiple phases or subagents, or can be paused, restarted, or context-compacted (older conversation turns trimmed to free space) between asking and answering.
---

# Ask for approval

## Overview

A multi-phase agent workflow (plan, build, verify, merge) hits points
only a human can decide. Never read silence, a timeout, an auto-approved
permission check, or a passing test as a "yes". If the process can pause
or restart between question and answer, save the "question is open"
record before showing the question, not after.

## When to use

- The workflow runs unattended, across separate invocations, or through a
  coordinator plus subagents, so no one is guaranteed to be watching.
- The decision is one only a human makes: approve a plan, merge vs.
  discard a branch, sign off that verification really passed, accept a
  scope change mid-task.

Do NOT use this in a live foreground session where the user answers in
real time (just ask them), or for automated checks like tests or a
build; those are CI gates, not human approval gates.

## The pattern

1. Look first for a decision already on record for this same scope and
   result: if a human explicitly answered it before, that answer still
   holds. Restarting the process, switching tools, or trimming old context
   never resets it to unanswered.
2. State the question in the human's terms, with the real choices and
   what each leads to, not internal step names.
3. Persist before you ask: write an "open question" marker to durable
   storage first, only then show the question and stop. If the write
   fails, report that the gate could not be armed instead of asking.
4. Wait for an explicit answer. A timeout, no reply, an auto-approve
   rule, or a green build never counts as approval.
5. On resume, match the reply to the specific marker it answers. A
   generic "continue" counts only for what it directly addresses, never
   for a merge or sign-off it never named. Clear the marker once a real
   answer lands.

Stop condition: the gate closes only on a recorded, matching explicit
answer, or a report that the decision is still blocked, never because
the agent judged the question no longer needed one.

## Quick reference

| Situation | Correct move |
|---|---|
| Same result, nothing material changed | Reuse the earlier explicit answer |
| Timeout or no reply | Still pending, do not proceed |
| Tests pass, build is green | Not a substitute for human sign-off |
| Process might die before persisting | Write the marker first, ask second |

## Common mistakes

- Asking first, writing the marker after: a crash between the two loses
  the record, so a restart proceeds as if nothing was asked.
- Treating a passing automated check as sign-off; it measures the code,
  not whether a human accepted the result.
- Letting a routine "continue" silently approve a specific step, like a
  merge, that the message never named.

## Source

Repo `https://github.com/maxritter/pilot-shell`, file
`pilot/agents/agent-gate-protocol.md`, read at commit
`4d782c8f9940c572d82e918588a9a19e77547cd8`. Licence: NOASSERTION (no OSS
licence declared). Mechanism described in original wording; no sentence or
code copied from the source.
