---
name: whatnow
description: "Short status overview of the current session: what was done, what is running now (including subagents and workflows), and what comes next in the plan or task list. Use for /whatnow, \"where are we\", \"status\", \"what's left\", \"what are you doing\"."
argument-hint: "[plan folder]"
---

# What now

An overview the owner reads in under a minute. One line per task, never the detail of how
it was done. Read only; change nothing, start nothing.

## Gather (cheap, in this order)

1. **This conversation:** what the owner asked for and what was finished.
2. **Running work:** background agents, workflows and shells. Ask nothing of them. For each
   one this session launched (agent launches carry an agentId; Workflow and background
   Bash launches carry only a taskId, so match on either):
   - Look at its LAST event, not its first. One id notifies every time it stops, and again
     after a SendMessage wakes it. Running = launched or woken after its last
     task-notification. Finished = a notification after the last wake (status completed,
     failed or killed).
   - Agents and workflows: the notification check alone decides.
   - Background shells: "no notice yet" alone is not proof, because some shells never send
     one. Second check: `lsof -t -- <tasks dir>/<taskId>.output` (the path its launch result
     printed); exit 0 (a process holds the file) means running, exit 1 means ended. When the
     two checks disagree, write "unknown (launched <time>, no notice)".
   - Show each running item's start time, so one running for hours stands out. Shell:
     `stat -f %Sm <taskId>.output`. Agent or workflow: the launch line's timestamp in the
     transcript. None found: "start time unknown".
   - A finished one whose result you have not read yet is "done, not yet reviewed".
   - Launches no longer in context (after a compaction): grep the session transcript
     `~/.claude/projects/<project-dir>/<session-id>.jsonl` for `async_launched` and
     `task-notification`. Cannot read it: "unknown (history compacted)".
   Why this way: no built-in screen gives this list to a skill (`/tasks` and `/workflows`
   are for the owner's eyes), and the transcript rules above come from claude-hud
   `src/transcript.ts` and a checked run of this session's own transcript (research
   2026-10-18; claude-hud is github.com/jarrodwatts/claude-hud).
3. **The plan, if there is one:** the plan folder given in the args, otherwise the one this
   session worked in (plan-and-build: `progress.md`, `plan.md`, `register.md`; a skill plan
   in `~/plans/`; a research folder's `report.md`). Run
   `grep -n -E 'BLOCKED|UNVERIFIED|owner decides' <plan folder>/*.md` first, then read the
   end of `progress.md` and only the chunk and task lines of `plan.md`. No plan: use the
   task list or the conversation.
4. **Repo and branch, always:** for every repo or worktree this session worked in (the
   working directory, worktrees agents used, repos named in the plan), run
   `git -C <path> rev-parse --show-toplevel`, `git -C <path> branch --show-current` (empty
   means detached HEAD: say so), `git -C <path> status --short | wc -l` (the uncommitted
   count) and `git -C <path> remote get-url origin` (fails when there is no remote). Name
   the repo by its folder. Not a git repo: say so.

Never trust memory for "running": a task is running only if a check above shows it. If
something cannot be checked, write "unknown" for it.

## Write (load `unslop` first)

Plain words, no task ids (write what T4 is, not "T4"), no em dashes. Each item: one line,
saying what it is and what it needs or uses (a skill, tool, branch, service, or a decision
from the owner).

```
**Goal:** <one sentence: what this session or plan is for>
**Where:** <repo> on branch `<branch>` (<clean | N uncommitted files>); one line per repo
or worktree in use, e.g. "agent worktree: ui-qa on `plan/ui-qa-c2`"

**Done**
- <task>: <result in a few words> (<what it used>)

**Running now**
- <task>: <who is doing it: main session, agent "<name>", workflow> (<what it uses>)
  or "Nothing running."

**Next**
1. <task>: <what it needs> (<skill or tool>)

**Blocked:** <items that cannot move and why (BLOCKED lines, failed agents), or omit>
**Waiting on you:** <decisions or steps only the owner can do, or "nothing">
```

Rules:
- Caps: at most 8 items under Done (merge older ones into one line, such as "earlier: 3
  setup tasks"), 5 under Running now (then "plus N more"), 5 under Next, 3 under Blocked.
  About 250 words in all, and the word cap wins: cut older Done lines first, then Next
  items 4 and 5, then detail inside lines.
- Next is in plan order: item 1 is the first open task whose prerequisites are all done;
  items 2 to 5 are the open tasks after it, even when they wait on item 1. Only tasks
  waiting on the owner, or on a failed or BLOCKED item, go under Blocked or Waiting on you.
- Mark at most one item as in progress: the one the main session is on now.
- In a plan, say which part of the plan each Next item belongs to, in words ("part 3 of 5:
  the AI judge").
- Bugs or problems found along the way with no fix, ticket or Done line yet go in one Done line
  ("found along the way: ...").
