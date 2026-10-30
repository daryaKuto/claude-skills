---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
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

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

## Grilling a plan, spec or document: sweep first

When the thing being grilled is a written plan, spec, design or register (not a fresh idea),
build the **open-question list** before round 1, from every one of these sources:

1. Decisions not yet confirmed by the user: status `proposed`, `open`, "later", "TBD", or a
   recommendation nobody accepted.
2. Every line marked UNVERIFIED, BLOCKED, TODO, "owner decides", "ask", or "?" in the plan's
   files.
3. Assumptions a task or section depends on that no test, code read or live check proves.
4. Open decisions or questions about this plan in any other record that tracks it (a decision
   record, a published artifact, an earlier review or verification report).
5. Calls the agent would otherwise make alone later (order, scope, what to postpone, what
   to cut). A call with a real tradeoff is a question. A pure mechanic with no tradeoff is
   listed under "Calls I will make without asking", so the user can still overrule it.

## Research before round 1 (mandatory)

No question reaches the user until it has been researched. For every item on the list:

1. **Classify it.** A *fact* has one true answer that exists somewhere (what the code does,
   what the database holds, what a setting is, what a doc or record says). A *choice* has
   several valid answers and the user's preference picks one.
2. **Look up every fact** before round 1, with Sonnet agents (at most 5 at once, one scoped
   item each), in this order: the codebase (grep, read by `file:line`), the live database
   and services read-only (the project's rules say how, for example a database MCP or CLI
   on the live project), then the plan's own files, records and published artifacts. A fact
   that was found is written into the plan with how you know it (`file:line`, or the query
   and what it returned). It is never asked.
3. **Research every choice too**, so each option's pros and cons rest on real numbers and
   `file:line` cites, not guesses.
4. **Only two kinds of item reach the user:** a real choice, or a fact that no code, data or
   document can answer (something only a person knows, such as a business preference or
   another team's plan). For the second kind, say what was searched and where, so the user
   sees it was looked for.
5. **A dead or failed research agent** leaves its item unresearched: re-run it. Never turn a
   failed lookup into a question for the user.

Then show the counts before round 1: per source (0s included; "not checked: <why>" for a
source that could not be read), and how many items were settled by research versus how many
are choices for the user. Every question in the rounds carries a **What I checked** line
(the `file:line` or query behind it).

## Rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question, lay out its options with pros and cons, and give your recommended answer and why. Then wait for the user's answers before the next round.

Format a round like so:

```
**Q1. <question title, in plain words>** (<source: e.g. "plan.md:815, UNVERIFIED">)
<what is being decided and why it matters, with a concrete example or real numbers>
**What I checked:** <file:line, query and result, or where it was searched and not found>

| Option | Pros | Cons |
|---|---|---|
| A: <option> (recommended) | <pros> | <cons> |
| B: <option> | <pros> | <cons> |

**Recommended:** A, because <the reason that decides it>.
**Changes if you pick B:** <what in the plan changes>

---

**Q2. ...**
```

The Q number only orders this round. When you refer back to a question, or record its answer
as a decision, use its title and the chosen option ("Store sessions in Postgres"), never
"Q3" or "D-04" alone (owner rule 2026-10-22).

At any point the user may say "go with your recommendations" (or "accept all", or the same in
other words). That accepts your recommendation for EVERY question still open, including
ones in later rounds you have not asked yet: list those remaining questions, one line each
with the recommended option, record them as accepted, and the frontier is empty. Nothing is
left open or "for later" unless the user picked "later" as the answer.

Every question carries a recommendation; a question without one is not ready to ask. If you
truly cannot recommend (the options are equal on everything you can check), say so in the
question and mark it **No recommendation: needs your pick**. "Go with your recommendations"
never covers such a question: ask it again on its own, and never pick it yourself.

Every question gets at least two real options; "do nothing" or "decide later" counts as an
option when it is a real one, with its own pros and cons. Never list an option you would
not actually build. Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. For a written plan the research above happens before round 1. When a fact only turns up later (an answer opens a new branch), dispatch a sub-agent to find it (`model: "sonnet"`, at most 5 at once); don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed, and (for a plan) every item on the open-question list answered or settled by a fact you checked. Then show the list once more, each item with its answer or the fact that settled it, and write the answers into the plan's own files (and any record that tracks it, the way the project says). Do not act on it until the user confirms you have reached a shared understanding.

## Source
mattpocock/skills, `skills/productivity/grilling/SKILL.md`, commit
49dd158d1076134a641b33efb035946536778336, MIT. Adapted: emoji markers replaced
with bold labels (owner's no-decorative-emoji rule); sub-agents pinned to
Sonnet with the 5-at-once cap. Owner additions (2026-10-12): the open-question sweep for
written plans, and pros and cons for every option with the reason for the recommendation.
