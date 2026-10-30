---
name: trim-context
description: Use when a transcript, tool-call history, or set of notes has grown too large to keep in full and needs to be cut down before continuing, handing off to another agent, or writing a digest, especially when an exact file path, error message, command, or constraint inside it must not be lost to a paraphrase.
---

# Trim context

## Overview

When content is too large to keep whole, decide per unit whether to keep it
verbatim, truncate it with a note, or drop it, instead of asking a model to
paraphrase everything into a summary. A summary can silently lose the one
exact detail that mattered; a keep, truncate or drop decision never rewrites
what it keeps.

## When to use

- Compacting your own working context or a long tool-call history.
- Writing a handoff document for another agent or a later session.
- Building a research digest that must stay faithful to its sources.
- Any time "cut this down" would otherwise mean "summarize this."

**Do NOT use** when the content already fits, or the goal is genuine
re-explanation for a fresh human reader (a report, a README): that needs
real prose, not unit-by-unit pruning.

## The pattern

1. **Pin what must not move:** the task or goal, the newest N turns,
   anything already referenced ahead. Leave these untouched.
2. **Judge each remaining unit alone** (one tool call, log entry, or
   paragraph): matters as-is, matters only as a fact, or now dead weight.
3. **Degrade in stages, cheapest first, stop once it fits:** truncate plus
   a one-line note beats paraphrasing; collapsing a run of low-value units
   into one placeholder line beats deleting them silently; only drop a unit
   once truncation alone did not fit. Re-measure after each stage.
4. **Stop condition:** stop degrading the moment it fits, even with stages
   left. If it still does not fit after the last stage, say so instead of
   quietly paraphrasing what remains.

## Quick reference

| Stage | What happens | When |
|---|---|---|
| Keep verbatim | No change | Pinned, or still fully needed |
| Truncate + note | Keep first N chars, note what was cut | Partly needed, or reproducible |
| Collapse a run | Several low-value units become one line | Old units, none matter alone |
| Drop | Removed entirely | Confirmed not needed, even as a fact |
| Paraphrase | Never, for kept content | N/A |

## Common mistakes

- Summarizing everything uniformly instead of judging each unit on its own,
  smoothing away the one detail that mattered.
- Truncating without a note of what was cut and roughly how much, so a
  later reader cannot tell there was ever more.
- Dropping one half of a paired call and result (or a question and its
  answer), leaving the other orphaned.
- Re-trying a degrade stage that already proved insufficient instead of
  moving to the next one and re-measuring.

## Source

- Repo: `https://github.com/tamaratran/fast-jev-compaction`, commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`.
- License: MIT.
- File read: `README.md` ("What and why", "How it works").
- Adapted: the per-unit keep/truncate/drop decision with staged,
  cheapest-first degradation, generalized past the source project's Claude
  Code compaction plugin to any oversized transcript, handoff note, or
  digest. Written independently; no wording or code copied from the source.
