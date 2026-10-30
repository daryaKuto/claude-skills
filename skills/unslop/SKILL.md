---
name: unslop
description: Use when writing or editing prose a person will read (docs, READMEs, reports, specs, plans, PR descriptions, commit bodies, emails, blog or social posts), when asked to "unslop", "humanize", "de-AI" or "make this sound human", or when text reads generic, puffed up or machine-written.
---

# Unslop

## Overview
Write so a software engineer intern can act on it, and so nobody can tell a
model drafted it. Cut the patterns below, keep the meaning, check once more.

## When to use
- Any text a person will read: docs, reports, specs, plans, PR descriptions,
  commit bodies, code comments, emails, posts.
- Not for code, config or data files.
- For a full audit of a published or high-stakes document, use the
  anti-ai-writing skill (the complete Wikipedia catalog) instead.

## The pattern
1. Name the reader: an intern who can code but does not know this project.
2. Shape the text for its form, following "Writing and tone" in the global
   CLAUDE.md. Technical documents keep their labelled structure (findings,
   options, "How we know"). Do not melt them into flowing prose.
3. Scan for every pattern in the quick reference. Fix each hit: keep the
   meaning, use the plain version.
4. If the text is outward-facing prose (README intro, blog, email, social
   post, landing page), apply Voice. For anything else, skip Voice.
5. Self-audit once: "What still makes this read as AI-generated?" Fix it.
   Then search the text for the em dash character (U+2014): the count must be 0.
Stop after step 5. One pass, not a loop. Do not report the pass; deliver the text.

## Quick reference

Content
- Significance inflation (pivotal moment, testament to, evolving landscape): say what happened.
- Name-dropping outlets without context: pick one, say what it said.
- Trailing -ing clauses (", highlighting...", ", ensuring..."): delete, or make it a real sentence.
- Promotional words (vibrant, seamless, robust, groundbreaking): a specific fact. "Onboarding takes 3 days" beats "seamless onboarding".
- Vague attribution (experts say, research suggests): name the source or cut.
- "Despite challenges, it continues to thrive": give the specific fact.

Language
- AI vocabulary (additionally, crucial, delve, enhance, fostering, garner, interplay, intricate, showcase, tapestry, underscore): plain words.
- Copula avoidance (serves as, stands as, boasts, features): "is", "has".
- "It's not just X, it's Y": state the point.
- Forced groups of three: use the real count.
- Synonym cycling: pick one term and repeat it.
- False ranges ("from X to Y" with no real scale): list the items.

Style
- Em dashes: none. Period, comma, colon or parentheses; "to" for ranges.
- Colons as mid-sentence crutches: fine before a list or example, not as a connector.
- Bold on every term: bold only what the reader must not miss.
- Title Case Headings: sentence case.
- Decorative emoji and curly quotes: remove; straight quotes only.

Communication and filler
- Chatbot phrases (I hope this helps, Certainly!, Let me know if): cut.
- Sycophancy (Great question!) and signposting (Let's dive in): just start.
- Knowledge-cutoff disclaimers: find the source or cut.
- Filler (in order to, due to the fact that, it is important to note): "to", "because", or cut.
- Hedge stacks (could potentially possibly): one word, or commit to a position.
- Summary endings (the future looks bright, in conclusion): end on the last new fact or the decision.

## Voice (outward-facing prose only)
- Have a position. React to facts instead of listing pros and cons neutrally.
- Vary rhythm. Short sentences. Then a longer one that takes its time.
- Be specific: "the scheduler fired 40 times overnight" beats "this is concerning".
  Use only facts from the source text or ones you have checked. Never add a
  feature, number or detail the source does not state; when a fact is missing,
  keep the sentence general or ask.
- Use "I" or "we" when it fits.
- Admit mixed results: "fast but fragile" beats "impressive".

## Common mistakes
| Mistake | Fix |
| --- | --- |
| Turning a report's labelled findings into prose to "sound human" | Voice is for outward-facing prose only. Technical docs keep their structure. |
| Swapping one AI word for another (crucial to vital) | Use the plain word or a specific fact. |
| Removing tells but leaving outward prose voiceless | Apply Voice. |
| Ending with a recap | End on the last new fact. |
| Inventing specifics to sound concrete (features, numbers the source never gave) | Every specific must come from the source or a check. |
| Narrating the pass ("I removed six AI patterns") | Deliver the text only. |

## Source
Adapted from poteto/noodle, `.agents/skills/unslop/SKILL.md` (MIT licence),
commit 82d2921c52370f23f29086de81ccfb600939c037, https://github.com/poteto/noodle.
The pattern list and Voice section are adapted from it. Dropped from the
original: "convert inline-header lists to prose" and "let some mess in", which
clash with structured technical documents. Added: the intern reader, the
technical-versus-outward split, signposting and summary endings. Full catalog:
https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
