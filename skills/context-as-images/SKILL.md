---
name: context-as-images
description: Use when designing, tuning, or debugging an LLM agent pipeline, local proxy, or context-caching layer that resends large, low-precision context (system prompts, tool docs, chat history, logs, file dumps) on every request to a vision-capable model, and token cost from that resend is a concern; also use when deciding whether an image-based compression trick is worth adding, or when such a trick is producing wrong recall of exact values (IDs, hashes, secrets).
---

# Context as images

## Overview

A vision-capable model is billed for an image by its pixel dimensions, not
by how much text is packed inside it. Dense, repetitive text (code, JSON,
logs) can render at roughly 3+ characters per image token, versus about 1
character per text token. Rendering the right content as an image page
instead of text can cut that content's token cost by more than half. It is
a compression trick, not a universal one.

## When to use

Use when a pipeline resends the same bulky, low-precision block every turn
(system prompt, tool docs, old history, log dumps) to a model that reads
images.

Do NOT use when:
- content is sparse prose (near 1 char/token as text): imaging it can cost
  MORE. Check the ratio, do not assume.
- content has byte-exact values the model must recall precisely: hashes,
  IDs, secrets, UUIDs. Image recall of exact strings is lossy (as low as
  0/15 correct on some models, 13/15 on the best). Keep those in text.
- the receiving stage cannot reliably read images (text-only subagent,
  non-vision model, strict API mode).

## The pattern

1. Identify the bulky, low-precision, resent-every-turn block(s); recent
   turns and anything byte-exact are excluded.
2. Pull byte-exact identifiers out first; keep them in accompanying text,
   never inside the rendered image.
3. Check profitability on what remains: image only where its image-token
   cost beats its text-token cost, not as a blanket policy.
4. Render the block to an image page and substitute it for the original
   text.
5. Measure actual input tokens per request, with and without the
   substitution, using a real token counter, not an assumption.
6. Keep a text-only escape hatch for any consumer that cannot read images
   or where exact recall outweighs cost.

Stop condition: ship the substitution for a content type only once step 5
shows a measured net token reduction on real requests; drop it if savings
are flat or negative.

## Quick reference

| Content | Image it? |
|---|---|
| Dense code / JSON / logs, resent every turn | Yes |
| Sparse prose, one-off content | No, verify ratio first |
| Hashes, IDs, secrets, exact values | No, keep as text |
| Old history beyond the last few turns | Often, if dense |
| Recent or active turns | No |

## Common mistakes

- **Imaging without measuring.** Images are not always cheaper for sparse
  prose; measure real tokens first.
- **Imaging exact values.** Vision recall of hashes or IDs is unreliable;
  keep those in text.
- **No escape hatch.** A stage that cannot read images must fall back to
  text, not drop content.

## Source

- Repo: `teamchong/pxpipe`, commit `8ba82b713a1e823bc1c09b7a68e47f63caa7b426`.
- License: MIT. Wording adapted with attribution; no code or prose copied.
- File read: `README.md` (root).
- Adapted: the mechanism of trading text tokens for image tokens on bulky,
  low-precision context, its profitability gate, and its byte-exact-value
  escape hatch, restated in original wording.
