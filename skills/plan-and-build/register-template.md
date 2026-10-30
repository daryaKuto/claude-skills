# Register template and routing guide

The orchestrator copies the template below into `register.md` in plan mode and fills it in.

```markdown
# Decision register: <plan name>

Artifact page: <filled in after the page is published>
Plan: plan.md · Design: design.md · Progress: progress.md
Worker rules: ~/.claude/skills/plan-and-build/worker-rules.md (read before your task)

## How to read this register (for implementing agents)

1. Find your task's row in "Task routing". Do its steps in order. Where a step names a skill,
   invoke that skill with the Skill tool for that step.
2. Follow every decision marked `accepted`. If the code forces you to break one, stop and
   report DONE_WITH_CONCERNS with the reason. Never change a decision yourself.
3. "Your commit range" means the BASE sha in your brief up to HEAD.
4. Someone else reviews your work. Report exactly what you ran and what it returned.

## Decisions

The Decision column is the decision's name everywhere: what was decided, as a short title
("Store sessions in Postgres, not Redis"), not the topic ("Session store"). Other files
cite a decision by this title, never by its ID alone or as an ID range (owner rule
2026-10-22, SKILL.md "Shape of a plan").

| ID | Decision | Options considered | Chosen and why | Why not the alternatives | Abuse case | Fails when | Evidence | Status |
|---|---|---|---|---|---|---|---|---|
| D-01 | <what was decided, as a title> | A: ... / B: ... | B, because ... | A loses because ... (numbers or file:line) | what a malicious user tries and what stops it, or "does not apply, because ..." | how it breaks, what the user sees, how we find out | file:line or command | accepted <date>: <option> / superseded by "<title of the newer decision>" (`proposed` only while plan mode is still asking) |

The last three answer columns come from `design.md` "Design interrogation" (SKILL.md). A row
with any of them blank is not ready for `go`.

## Task routing

| Task | Chunk / feature | Type | Steps, in order |
|---|---|---|---|
| T1 Add the sign-up form | C1 Sign-up / F1 New user can register | new behaviour | 1. Read the files in the brief. 2. Write the failing test: `pstack:tdd`. 3. Make it pass with the least code. 4. Run Done when, typecheck, lint. 5. Clean your commit range: `pstack:deslop`. 6. Commit and report. |

## Pre-existing bugs

Bugs found during the build that were already in the code. Each has a root cause from an
investigator, never only a symptom. Fixed ones name their task; the rest become plan tasks.

| Bug | Found in | Root cause (`file:line`) | Relevance (blocks, in path, unrelated) | Severity | Triage (fix now, fix next, plan) | Test idea and Done when | Fixed by / planned as |
|---|---|---|---|---|---|---|---|

## Postponed

Findings below "high" and shortcuts, to fix later.

| From | Finding | Where | Why postponed |
|---|---|---|---|
```

## Routing guide: task type to steps

Build each row's steps from these. Every row starts with "Read the files in the brief" and
ends with "Run Done when, typecheck, lint", then "`pstack:deslop` on your commit range (never
remove validation or error handling)", then "Commit and report".

| Task type | Steps in the middle |
|---|---|
| New behaviour or bug fix | Failing test first with `pstack:tdd`, against real dependencies. Then the least code that passes it |
| Bug whose cause is unknown | `superpowers:systematic-debugging` to find the cause, then `pstack:tdd` |
| New module, or a signature other files call | Fill in the sketch from design.md. Do not re-run `pstack:architect` |
| Changes a shared signature or public API | `pstack:blast-radius` before editing: single pass, no arena, read-only commands or local tests only |
| Refactor, behaviour must not change | `pstack:principle-subtract-before-you-add`, then pin behaviour with tests before reshaping |
| Database schema or migration | `supabase:supabase-postgres-best-practices` (Supabase) or `postgres-patterns`. Write the migration file only; applying it is the user's call |
| Auth, sessions, permissions, secrets, user input | `security-review` |
| UI component or screen | `frontend-a11y`, then `make-interfaces-feel-better` |
| TypeScript files | `pstack:typescript-best-practices` (its mock advice is overridden by worker rules) |
| Contested design inside the task | Report NEEDS_CONTEXT. The orchestrator takes it to the user |
| Docs, comments, PR text | `unslop` |

Fix briefs (task fix rounds, feature fixes, chunk fixes) reuse the task's row, or for
feature and chunk fixes: "Read the brief, `pstack:tdd` if behaviour changes, least code,
checks, `pstack:deslop`, commit and report".
