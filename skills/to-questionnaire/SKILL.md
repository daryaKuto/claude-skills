---
name: to-questionnaire
description: Turn a decision you can't fully answer into a questionnaire for someone else to fill in. Use when the answer sits with another person or team (a vendor, another team, a client), or a plan task is BLOCKED on one.
---

## Writing rules (owner rule 2026-10-22)

Every plan, spec, design doc, register, questionnaire or report this skill writes is read by a
person: an intern who can code but does not know this project.
- Load the `unslop` skill before writing, and apply it to every section.
- Be concise. Lead with the decision or result, one idea per sentence. No long narration, no
  history of how you got there, nothing the reader does not need to act.
- Human readable. Name decisions, tasks and questions by what they are, never by an id alone
  or an id range ("R-D98 to R-D102"); an id may follow the title in brackets. Define every
  project term on first use.
- No em dashes.

Turn something the user can't answer alone into a **questionnaire**: a Markdown document they hand to one person to fill in async, or fill out together over a meeting. The recipient holds knowledge the user lacks; the questionnaire pulls it out of them.

**Grill the send, not the subject.** Interview the user only about the _send_, which they can always answer: who it goes to, and what they need back. The questions in the document then target the **gap** between what the recipient knows and what the user needs.


1. **Who is it going to?** Ask, in one exchange, the recipient's role, expertise, and relationship to the user. This fixes the questionnaire's tone and how much context it must carry. Done when you know who the recipient is and what they know that the user doesn't.

2. **What do you need back?** Ask, in one exchange, the specific decisions or facts the user can't resolve alone and needs from this person. Done when you have a concrete list of what the user must walk away able to do or decide.

3. **Write the questionnaire.** Draft questions aimed at the gap from steps 1 to 2, following the Document structure below. Load the unslop skill first: the recipient is outside the project, so define every project term and ID on first use. Write it to `to-questionnaire-<slug>.md` in the active plan folder (`docs/plans/<date>-<slug>/`) if there is one, otherwise in the scratchpad, and report the path. Sending it is the user's job. Done when the file exists and every item the user named in step 2 is covered by a question.

## Document structure

Frame the document as a **discovery questionnaire**: the user lacks context, the recipient holds it. Order questions most-important-first, since async means you may only get one pass, and group them under `##` headings by theme once there are more than a handful. Write it using the template below.

<questionnaire-template>

# <Questionnaire title>

**Purpose:** why this questionnaire exists and the decision riding on it.

**From:** <the user>, **To:** <the recipient>, **How your answers will be used:** <where they go>

## Context

One paragraph orienting a recipient who wasn't in the user's head. Enough to answer well, not a page.

## How to answer

Deadline and rough effort. Partial answers and "I don't know" are useful: flag anything you're unsure of rather than skipping it.

## <Theme heading>

One `##` section per theme. Under each, its questions, most-important-first. Every question is one idea, never compound, with an answer stub directly beneath, and a one-line _why this matters_ only where the question could be misread or invite a throwaway answer.

<question-example>
### What load is the system expected to handle at launch?

_Why this matters: it decides whether we provision for burst traffic now or defer it._

>
</question-example>

## Anything else?

A closing catch-all: anything we didn't ask that we should know?

</questionnaire-template>

## Source
mattpocock/skills, `skills/productivity/to-questionnaire/SKILL.md`, commit
49dd158d1076134a641b33efb035946536778336, MIT. Adapted: unslop and term definitions for an outside reader; written to the
plan folder or scratchpad, not the working directory; the user sends it; model invocation
enabled so the CLAUDE.md stage map can call it.
