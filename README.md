# Claude Code skills for planning, building and verifying software

These are the Claude Code skills and the global `CLAUDE.md` I use every day to build software
with agents. They are opinionated about one thing above all: nobody grades their own work.
Every plan, finding and fix gets checked by a separate agent with a fresh context, and every
claim needs proof (a `file:line`, a command and its output) before it reaches you.

A skill is a folder with a `SKILL.md` that Claude Code loads when the task matches its
description, or when you type `/<skill-name>`. You can read more in the
[Claude Code skills docs](https://docs.claude.com/en/docs/claude-code/skills).

## Install

```bash
git clone https://github.com/daryaKuto/claude-skills.git
mkdir -p ~/.claude/skills
cp -R claude-skills/skills/* ~/.claude/skills/
```

Then restart Claude Code. Skills in `~/.claude/skills/` work in every project. To use a skill
in one project only, copy it to that project's `.claude/skills/` instead.

The `CLAUDE.md` here is my global steering file. Do not copy it over yours blindly. Read it,
keep the rules you agree with, and edit the "Who I am" section. It goes in `~/.claude/CLAUDE.md`.

### Recommended: install pstack

I recommend installing pstack alongside these skills. `plan-and-build`, `review-all` and
`investigate` use its architect, TDD and review skills for their design, test and review
steps, and my `CLAUDE.md` routes build work through its `poteto-mode`. pstack is
[Lauren Tan's skill stack](https://github.com/cursor/plugins/tree/main/pstack), ported to
Claude Code by [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude)
(MIT). Install it from inside Claude Code:

```
/plugin marketplace add michael-denyer/pstack-claude
/plugin install pstack@pstack-claude
```

Then copy `pstack-models.md` to `~/.claude/pstack-models.md`. It is the model settings file
my `CLAUDE.md` imports: it runs pstack's workers on Sonnet and its judges on Opus. If you skip
pstack, delete the last line of `CLAUDE.md`.

Several skills build on other people's skills. Install those too (see
[Skills these depend on](#skills-these-depend-on)), or the skills still run but skip the steps
that call them.

## Which skill when

You rarely need to name a skill. Describe the job and Claude picks one. The table maps the
kind of thing you would say to the skill that handles it. A similar map is in `CLAUDE.md`, so
Claude follows it too.

| You want to... | Say something like | Skill |
| --- | --- | --- |
| Pressure-test an idea or plan before building | "grill me on this", "poke holes", "help me decide" | `grilling` |
| Plan a feature or migration, then build it | "plan this", then "go" | `plan-and-build` |
| Answer a question about your code or system | "investigate why X", "look into X", "research X" | `investigate` |
| Check a plan, spec, report or claim before acting on it | "verify this plan", "is this right?" | `proofread` |
| Review a change | "review my changes", "review PR 42" | `code-review` |
| Run every reviewer at once | "full review" | `review-all` |
| Decide if a branch can merge | "ready to merge?" | `review-before-merge` |
| Get an answer from another person or team | "ask the backend team about X" | `to-questionnaire` |
| Do a manual step only you can do (dashboard, keys) | "rotate the API key", "set up the account" | `wizard` |
| See where a long session stands | "where are we?", "status" | `whatnow` |
| Brief subagents or plan a fan-out | "dispatch agents for this", "write the agent prompts" | `agent-orchestration` |

## The skills

### Planning

- **`grilling`**: asks you one hard question at a time about a plan or decision until every
  open choice is settled. Each question comes with options, pros and cons and a recommendation.
  It looks things up in the code before it asks, so it never asks what the code can answer. Use
  it before you plan anything big.
- **`plan-and-build`**: the main build loop, in three modes.
  - `/plan-and-build plan <goal>` writes a design doc, a plan split into PR-sized chunks, and a
    decision register that tells each worker which skills to use for each step.
  - `/plan-and-build go` builds one chunk at a time on a `plan/<slug>` branch. Each task gets a
    fresh implementer and a separate reviewer, each chunk gets a full review and a "do we need
    this, and is it simple enough?" review, then a PR into the plan branch. After each merge it
    re-runs the checks on the merged branch and logs a cost line; every 3 merged chunks get one
    more review of their combined diff; and 2 or 3 held-back checks, written at the start and
    kept away from every worker, run at the end.
  - `/plan-and-build release` runs the release runbook after you merge.

  It never merges into your default branch. That last PR is yours. The release step refers to
  a "rehearsal log": a small script you write for your project that runs a migration or deploy
  on a staging copy and records a hash of what passed. Without one, every production step asks
  you first.
- **`to-questionnaire`**: turns a question only someone else can answer into a short
  questionnaire you can send them, with the context they need and the options you see.
- **`wizard`**: writes an interactive bash script that walks you through steps only a human
  can do (clicking through a cloud console, creating credentials). You run it, not Claude.

### Research and investigation

- **`investigate`**: for questions ("why does X happen?", "how does Y work?"). It fans out
  parallel agents in a Workflow, tries to disprove every finding, and when it finds a real bug in
  your code it sends fresh agents to fix it, then checks the fix. One extra "contrarian" agent
  argues the opposite answer, and findings past the top 3 per agent are listed as unverified
  instead of dropped. It stops and asks before
  touching production data, secrets, auth or billing.

### Verification

- **`proofread`**: the one entry point for "is this true?". Give it a plan, spec, report, PR
  description, a single finding, or a diff plus its plan, and it routes to the right engine
  below. Report only: it changes nothing it checks.
- **`claim-verification-loop`**: pulls every claim out of a document and checks each one over
  two or three adversarial loops. It snapshots your live system once (database, API, git) so the
  checking agents read a file instead of re-querying, which cut tool calls by more than half when
  I measured it.
- **`verify-findings`**: checks one finding (a bug, root cause or vulnerability) before anyone
  acts on it, looking for false positives and false negatives.
- **`loop-until-verified`**: rules for any loop that repeats until checks pass: a hard cap,
  checks that must actually run, progress kept in a file, and a few checks held back for the end.
- **`ask-for-approval`**: how a workflow stops and asks you a yes or no question, so it never
  treats silence or a timeout as approval.

### Code review

- **`code-review`**: eight independent reviewers (architecture, security, scalability, edge
  cases, tests, failure detection, data integrity, UX and accessibility), then refuters who try
  to disprove each finding by a different method. Medium, high and critical findings get a
  second, blind refuter that must run something. Runs typecheck, lint, tests and build first.
  Posts to GitHub only after you say yes.
- **`code-council`**: four reviewers and one chairman who merges their findings. Three modes:
  review code, review a plan before work starts, or check that a diff does what its plan says.
  Before it starts you set aside 1 or 2 held-back checks that no reviewer sees; a fresh agent
  runs them after the report.
- **`review-all`**: runs five review skills on the same change, sends the findings from the
  four that do not refute their own to refuters, and merges everything into one ranked,
  deduplicated report.
- **`review-panel`**: several reviewers with roles you choose check the same change, spec or
  document. It runs `code-council` with your list of roles, so it gets the same refuters and
  chairman; its finalize mode applies only confirmed fixes and has them reviewed again.
- **`review-before-merge`**: a diff-scoped review that answers "can this branch merge?".
- **`track-review-findings`**: keeps review findings stable across pushes, so a re-review marks
  old findings resolved instead of raising them again.
- **`grow-test-coverage`**: adds tests in small steps and keeps only tests that run, pass and
  raise coverage.

### Orchestration and context

- **`agent-orchestration`**: how to dispatch subagents: a cheaper worker model (for example Sonnet) and a stronger judge (for example Opus), at most
  5 at once, a four-part brief, snapshot live state once and let many agents read it, size the
  run before you launch it, and never count a dead agent as a clean result.
- **`whatnow`**: a short status of a long session: what is done, what is running (agents and
  workflows included), and what is next.
- **`prompt-caching`**: how to order prompts and subagent briefs so repeated calls reuse the
  prompt cache.
- **`trim-context`**: how to shorten a long log or context without losing the exact details you
  need later.
- **`context-as-images`**: when sending bulky context as images saves tokens, and when it does not.
- **`unslop`**: writing rules for anything a person will read. Removes the patterns that make
  text read as machine-written. Most other skills load it before they write a report.

### The `CLAUDE.md`

It holds the rules nothing else would trigger in time:

- **Orchestration**: the main model decides; workers are Sonnet subagents with one scoped task
  each; at most 5 at once; a dead agent is not a "no findings" result.
- **Verification**: the agent that did the work never approves it. Every finding needs proof.
- **Testing**: no mocks. Tests run against real dependencies (a local stack, a test database,
  a provider sandbox).
- **Hard stops**: never `git stash`, never push to main, never deploy or apply a migration
  without a yes in the conversation.
- **Writing**: everything is written so a new teammate who can code, but does not know the
  project, can act on it.

Some rules mention "the project's CLAUDE.md". I keep a second `CLAUDE.md` in each repo with
that project's facts, commands and hard stops. The skills read it when it exists.

Two things in `CLAUDE.md` and `plan-and-build` are mine and you supply your own, or delete
the lines:

- **A central plans page.** I keep every plan in one published page (a Claude Artifact) so
  I can track them all in one place. The rules about updating it name it in the project's
  `CLAUDE.md`. Without one, plans stay as markdown in `docs/plans/`.
- **`rehearsal.py`.** A per-project script that runs a migration or deploy on a staging copy
  and logs a hash of what passed. It is not in this repo because mine is tied to my database.
  Without it, every production step asks you first.

The dates and "owner rule" notes in the files mark when a rule was added and why. They are
history, not instructions; leave them or cut them.

## Skills these depend on

These skills are not mine. The skills above call them for specific steps. Install the ones you
want from their authors.

| Pack | Used for | Where to get it |
| --- | --- | --- |
| superpowers (Jesse Vincent) | `superpowers:systematic-debugging`, `superpowers:brainstorming` | [obra/superpowers](https://github.com/obra/superpowers), or the `superpowers` plugin in `/plugin` (claude-plugins-official) |
| pstack | `pstack:architect`, `pstack:tdd`, `pstack:interrogate`, `pstack:blast-radius`, `pstack:thermo-nuclear-code-quality-review`, `pstack:how`, `pstack:deslop`, `pstack:poteto-mode`, `pstack:comment-sicko`, `pstack:no-comments`, the `pstack:effort-*` agents, `pstack:principle-subtract-before-you-add`, `pstack:typescript-best-practices` | [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude), recommended (see [Install](#recommended-install-pstack)) |
| ponytail | `ponytail:ponytail-review` (in `review-all`) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) |
| hyperresearch | external research in `investigate`, `claim-verification-loop`, `code-council` | [jordan-gibbs/hyperresearch](https://github.com/jordan-gibbs/hyperresearch) |
| Everything Claude Code | `security-review`, `verification-loop`, `iterative-retrieval`, `loop-design-check`, `santa-method`, `frontend-a11y`, `postgres-patterns`, `make-interfaces-feel-better` (suggested by `plan-and-build`'s register) | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) |
| Anthropic skills | `anthropic-skills:anti-ai-writing`, `skill-creator` | [anthropics/skills](https://github.com/anthropics/skills) |
| Supabase | `supabase:supabase-postgres-best-practices` (only for Postgres work) | [supabase/agent-skills](https://github.com/supabase/agent-skills) |

The scripted fan-outs (the `.js` files under each skill's `scripts/`) run through Claude Code's `Workflow` tool, which needs
your opt-in (say "use a workflow").

## Credits

Several skills started from other people's work. Each skill built on someone else's work has a "Source"
section in its `SKILL.md` with the repo, the commit read and the license; that is the full list. In short:

| Skill | Built on |
| --- | --- |
| `grilling`, `to-questionnaire`, `wizard` | [mattpocock/skills](https://github.com/mattpocock/skills) (MIT). `wizard/template.sh` is unchanged from it |
| `unslop` | [poteto/noodle](https://github.com/poteto/noodle) (MIT) |
| `verify-findings` | [trailofbits/skills](https://github.com/trailofbits/skills), `fp-check` plugin (CC-BY-SA-4.0), and [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) |
| `loop-until-verified` | [mikeyobrien/ralph-orchestrator](https://github.com/mikeyobrien/ralph-orchestrator), [Th0rgal/open-ralph-wiggum](https://github.com/Th0rgal/open-ralph-wiggum), [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) and [BloopAI/vibe-kanban](https://github.com/BloopAI/vibe-kanban) (Apache-2.0) |
| `ask-for-approval` | ideas from [maxritter/qualitylayer](https://github.com/maxritter/qualitylayer) (formerly pilot-shell) (no license stated; wording is original) |
| `review-before-merge` | [AnandChowdhary/continuous-claude](https://github.com/AnandChowdhary/continuous-claude), ralph-orchestrator (MIT) and vibe-kanban (Apache-2.0) |
| `review-panel` | [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) (MIT text plus a trademark notice) |
| `track-review-findings` | [The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent) (MIT) |
| `grow-test-coverage` | ideas from [qodo-ai/qodo-cover](https://github.com/qodo-ai/qodo-cover) (AGPL-3.0; nothing copied, wording is original) |
| `prompt-caching` | [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks) (MIT) |
| `trim-context` | [tamaratran/fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction) (MIT) |
| `context-as-images` | [teamchong/pxpipe](https://github.com/teamchong/pxpipe) (MIT) |
| `code-council` | the idea of the three stages in [karpathy/llm-council](https://github.com/karpathy/llm-council) (no license stated; no text or code copied) |
| `claim-verification-loop` | borrows from hyperresearch (above) |

## License

MIT (see `LICENSE`), except `skills/verify-findings/`, which is CC-BY-SA-4.0 because it is
adapted from a CC-BY-SA source. Files adapted from other MIT projects keep their original
attribution in their "Source" section.
