# Proof rules (shared by every proofread mode and engine)

Every verification skill on this machine follows these rules. When an engine's own text is
looser, these win; when it is stricter, keep the stricter rule.

## What counts as proof

- **Code facts:** `file:line` you opened in this run, on the ref the document is about (usually
  `origin/main`), never a stale working tree.
- **Live facts:** a command or query you ran in this run, with its output, or a cite into a
  verified snapshot (`<file>:<jq path> (pulled <time>)`). The live system outranks the repo,
  docs and earlier turns (global CLAUDE.md constitution 2 and 3).
- **Behaviour:** a test or command that fails without the claimed behaviour. Reading the code
  is a claim about behaviour, not proof of it.
- A cite handed to you in a brief or a previous loop is a lead until you open it.
- No proof: the verdict is UNVERIFIED, with the reason and the exact command that would settle
  it. UNVERIFIED is never rounded up to a pass, and never dropped from the report.

## Verdict words

One vocabulary across engines. Map an engine's words onto it in every report.

| Verdict | Means | Engine words that map here |
|---|---|---|
| CONFIRMED | proved true by a stated method | CONFIRMED |
| REFUTED | proved false; the report says what is true instead | REFUTED, REJECTED |
| PARTLY | some conditions hold, some do not; each part has its own verdict | PARTLY |
| UNVERIFIED | could not be checked; reason and settling command given | UNVERIFIED, UNVERIFIABLE, PLAUSIBLE, NEVER COVERED (a claim no check reached: top priority next loop) |
| DISPUTED | two checks disagree (an adversary's challenge, or a re-check that reaches a different verdict); the adjudicator settles it with one command before reporting | SPLIT (code-council), a claim-loop `challenged` entry |

`code-review`'s APPROVE, COMMENT, REQUEST CHANGES and BLOCK are decisions about a PR, not claim verdicts; report them as they are. A claim the claim loop lists under `weakConfirmations` (confirmed by one weak method) is reported as CONFIRMED (weak) and counts as UNVERIFIED wherever a status depends on it.

For a plan's tasks, each task also gets one status: DONE, OBSOLETE, BLOCKED, UNVERIFIED,
CHANGED or STILL NEEDED. The rules and their order live only in `SKILL.md`, Mode: plan.

## Who does what

- **Workers** (readers, lanes, finders, refuters): fresh subagents, `model: "sonnet"`, one
  scoped job each, at most 5 running at once. Every brief carries the global four: the facts
  already known (do not re-derive them), return verdicts with `file:line` and no pasted code,
  read narrowly (no file over about 300 lines in full), and a budget of about 15 tool calls
  (an engine may give its readers more, as the claim loop does; its number wins). A dead, timed-out or empty agent is "not
  checked", never "clean": re-run it once, then report it as not run.
- **Adjudicators** (anything that merges or judges other agents' output: a chairman, the merge
  of lanes, the final verdict on a disputed finding): the session model when it is Opus.
  Otherwise one Opus subagent gets the disputed items, each as: the claim, both verdicts with
  their methods, and "settle it with one command and say which method you used".
- **Nobody verifies their own claim.** The author of a document, finding or fix never runs its
  check or its skeptic pass.
- **Refuters use a different method** from the agent that found or confirmed the claim
  (another tool, data source or test). A refuter that is unsure returns UNVERIFIED, not
  REFUTED. Every high or critical finding gets a second, blind refuter.

## Cost and stopping

- Pull live state once per run into a snapshot, have one agent check it, and have every other
  agent read the file. Agents that need a missing fact write `NEEDS-LIVE: <query>`; the
  orchestrator answers them all in one pull.
- Loops follow the engine's own loop and stopping rules (the claim loop runs 2 to 3, with its
  loop-3 fix test). Never more than 3. Loop N re-checks only UNVERIFIED, PARTLY, DISPUTED,
  claims confirmed by one weak method, and claims whose evidence changed. Each re-check gets one line from the
  previous loop (verdict, method, "attack differently").
- Say the agent count before a run over 10 agents. End every run with the engine's cost
  report where it has one (the claim loop's `scripts/run-cost.py`).
- Stop when every claim has a verdict and every UNVERIFIED names its blocker. Not when an agent
  says it is done.

## The report

Load `unslop` first. Verdict first (what was checked, against which ref and snapshot time, the
overall verdict, what the reader must decide). Then findings, most severe first, each in plain
words with a worked example and why it matters. Evidence goes last, under "How we know". A
caller that runs unattended passes "non-interactive": the run then asks nothing and lists what
it would have asked under Open questions. Write
the report where `SKILL.md`, "Where files go", says: a git-ignored folder confirmed with
`git check-ignore`, or the session scratchpad; never into anything git tracks.
