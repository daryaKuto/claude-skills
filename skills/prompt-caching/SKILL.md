---
name: prompt-caching
description: >-
  Use when writing or reviewing code that calls an LLM API repeatedly with a
  large shared prefix, such as a system prompt, tool schema, long reference
  document, or a subagent dispatch template sent to many workers in one
  session, and repeat latency or per-call token cost matters. Also use when
  someone reports a prompt-cache miss, wants to cut agent-loop token spend, or
  is about to draft several similar subagent briefs in the same run.
metadata:
  origin: adapted
---

# Prompt caching

## Overview

Some LLM APIs cache a block of prompt tokens so a later call skips
reprocessing it: a hit costs a fraction of a normal input token and returns
faster. This only works when the same token sequence opens the request each
time, so put unchanging content first and per-call content last.

## When to use

Several calls in a session share a long fixed prefix (system prompt, tool
definitions, a reference document, a subagent-brief template reused across
dispatches), and someone is cutting cost or latency on that loop.

**Skip it** for a one-off call, a prefix that changes every call (nothing
shared to cache), or before the call is proven to work: get correctness and
a cost/pass-rate baseline first, then add caching.

## The pattern

1. Identify the stable prefix: whatever is byte-identical call to call
   (system prompt, tool schemas, shared document, subagent template).
2. Order the request stable-first: fixed content, then whatever changes this
   call (task specifics, current files, this turn's message) last. One
   differing byte before the cache point breaks the hit for everything after
   it.
3. Mark the boundary: on Claude's API, top-level
   `cache_control: {"type": "ephemeral"}` for automatic mode, or the same
   field on one content block for explicit control (up to 4 breakpoints).
4. Confirm the prefix clears the minimum size (table below); below it,
   caching silently does not apply.
5. Pick a lifetime: 5 minutes (default, refreshed per hit) for a tight loop
   like seconds-apart subagent dispatches, or 1 hour (2x write cost) for
   slower work.
6. Verify from usage numbers, not a feeling: `cache_creation_input_tokens`
   (write), then `cache_read_input_tokens` (hit). Stop condition: later
   calls show a read count near the prefix size. Stuck at 0 means the
   prefix is not byte-identical; find the diff before calling it done.

## Quick reference

| Model family | Minimum cacheable prefix |
|---|---|
| Sonnet | 1,024 tokens |
| Opus / Haiku 4.5 | 4,096 tokens |

| Lifetime | Write cost | Read cost |
|---|---|---|
| 5 min (default) | 1.25x base input | 0.1x base input |
| 1 hour | 2x base input | 0.1x base input |

Breakpoints: 4 explicit, or 1 in automatic mode.

## Common mistakes

- Volatile content (timestamps, request IDs, non-deterministic ordering)
  before the boundary: silently kills every later hit, not just that call.
- Expecting a benefit below the minimum token count: a short system prompt
  never caches, wherever the marker sits.
- Optimizing placement before the call works: get a baseline pass rate and
  cost-per-task first (a pricier model that finishes in fewer turns can
  still cost less overall).
- Judging hits by feel instead of reading the usage fields above.

## Source

- Repo: anthropics/claude-cookbooks, commit a4b0d89061bc65769fea7947c080b3b11d938515
- License: MIT (wording adapted, attribution given per license terms)
- Files read: `misc/prompt_caching.ipynb`, `cost_optimization/cost_optimization.ipynb` (markdown cells only)
- Adapted: generalized the notebooks' `cache_control` placement and pricing
  into a "stable first, volatile last" pattern for any repeated-prefix call,
  including subagent dispatch.
