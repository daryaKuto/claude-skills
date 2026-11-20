# The enforcement pyramid

A rule that lives only in `CLAUDE.md` is a request. An agent can forget it, misread it or talk itself out of it.
The pyramid ranks where a rule is held, strongest first. Move a rule up whenever you can.

| Layer | What holds the rule | Strength |
| --- | --- | --- |
| 1. Codebase | The project's own lint, CI and tests | Fails the build for everyone, agent or not |
| 2. Static | Hooks and `permissions.deny` rules in `settings.json` | Refuses the command before it runs |
| 3. Verification | Test suites that prove each hook refuses what it should and allows normal work | Catches a hook that broke or got weaker |
| 4. Prose | `CLAUDE.md` lines and skills | The agent can forget it |
| 5. You | Rules only a person can hold | Needs your attention |

This repo ships layers 2, 3 and 4 for the rules below. Layers 1 and 5 are yours.

## Terms

- **Hook**: a script Claude Code runs on an event, such as `PreToolUse` for Bash. It reads the call as JSON on stdin and can print a
  `deny` decision. Exit code 2, or `onFailure: "block"` on a crash, stops the call.
- **Detector**: a small hook that looks for one kind of problem. `policy-guard.py` runs four detectors in parallel and prints the
  strictest answer.
- **Fail closed / fail open**: what happens when a hook itself crashes. Closed means the command is denied. Open means it runs.
  Detectors that guard data or guards fail closed. The memory check fails open, because it protects the machine, not data.
- **Worktree**: an extra checkout of the same git repo in another folder.

## Rule table

| Rule | Layer | Held by | Test |
| --- | --- | --- | --- |
| Never `git stash` (stashes are shared across worktrees) | Static | `hooks/stash-secret-guard.py`, deny rule `Bash(git stash*)` | `tests/stash-secret-guard-cases.py`, `tests/bypass-corpus.py` |
| Secrets are never printed: `.env` files, key files, `printenv`, `env`, keychain reads | Static | `hooks/stash-secret-guard.py`, the `Read(...)` deny rules, `hooks/lib/env-keys.py` (names only) | `tests/stash-secret-guard-cases.py`, `tests/env-keys-cases.py`, `tests/settings-cases.py` |
| `git -c`, `--config-env` and `--exec-path` cannot smuggle in an alias | Static | deny rules in `settings.example.json`, `hooks/stash-secret-guard.py` | `tests/settings-cases.py`, `tests/stash-secret-guard-cases.py` |
| No Claude attribution in a commit or PR | Static | `hooks/commit-guard.py` | `tests/commit-guard-cases.py` |
| Fork branches never merge into the default branch | Static | `hooks/commit-guard.py` reading `fork_branches` | `tests/commit-guard-cases.py` |
| `.claude/` and `specs/` are never force-added | Static | `hooks/commit-guard.py` | `tests/commit-guard-cases.py` |
| Guards, settings and their switches are not edited from Bash | Static | `hooks/tamper-guard.py` | `tests/tamper-guard-cases.py` |
| A guard folder's parents are guarded too (`rm`, `mv`, whole-folder copy, git work-tree) | Static | `hooks/tamper-guard.py` | `tests/tamper-ancestors-cases.py` (rows generated from the guard folders) |
| Subagents cannot Write or Edit guard files | Static | `hooks/write-guard.py` | `tests/write-guard-cases.py` |
| No `pkill`, `killall`, `kill -1` or `kill 0` | Static | `hooks/kill-guard.py` | `tests/kill-guard-cases.py`, `tests/bypass-corpus.py` |
| Long commands run in the background | Static | `hooks/heavy-guard.py` (rule e), `env.BASH_DEFAULT_TIMEOUT_MS` | `tests/heavy-guard-cases.py`, `tests/readonly-battery.py` |
| Nothing heavy starts when memory or disk is critical | Static | `hooks/heavy-guard.py` (rule b), `hooks/lib/limits.json`, `hooks/lib/mem-check.sh` | `tests/heavy-guard-cases.py` |
| Heavy runs take the project's lock (optional) | Static | `hooks/heavy-guard.py` (rule a), `heavy_lock_script` | `tests/heavy-guard-cases.py` |
| Free disk without deleting anyone's work | Static | `hooks/lib/free-disk.py` (agents may only clear tool caches) | `tests/free-disk-cases.py`, `tests/policy-guard-cases.py` |
| Warn the user once when memory is critical | Static | `hooks/shed-load.py` | `tests/shed-load-cases.py` |
| Workers run on Sonnet, only judges on Opus | Static | `hooks/sonnet-workers-guard.py` | `tests/sonnet-workers-guard-cases.py` |
| Test output stays short: failures and totals | Static | `hooks/trim-output.py` | `tests/trim-output-cases.py` |
| A cloned repo's `.vscode/` autorun tasks are removed | Static | `hooks/vscode-guard.sh` reading `trusted_github_owners` | `tests/vscode-guard-cases.py` |
| Every registered hook exists and fails closed; deny rules are all present | Verification | `hooks/settings.example.json` | `tests/settings-cases.py` |
| Everyday read and dev commands never prompt or block | Verification | the whole dispatcher | `tests/readonly-battery.py` |
| Known bypass spellings are refused | Verification | the whole dispatcher | `tests/bypass-corpus.json` run by `tests/bypass-corpus.py` |
| The hooks stay generic: no project names, accounts, dates or home paths | Verification | `tests/no-private-terms-cases.py` | itself |

`bash hooks/tests/run-all.sh` runs every suite. The suites run the real hooks against real temporary folders and git repos.
There are no mocks.

## Codebase layer: rules that belong in each project

These need a project's own tooling, so a global hook cannot hold them. Put them in lint, CI or a test:

- No mocking layer in tests (a lint rule on `vi.mock`, `jest.mock` and HTTP-mocking libraries).
- No committed `.claude/` folder (`.gitignore` plus a CI check that `git ls-files .claude` is empty).
- No Claude attribution in commit messages (a `commit-msg` hook or a CI check on the PR's commits).
- The same checks the hooks make for you locally, run again in CI, because a hook only runs on your machine.

## You: rules only a person can hold

- Keep secrets in a password manager, never in a file an agent can read.
- Merge to the default branch and deploy to production yourself.
- Approve removing `node_modules` (`free-disk.py --yes` without `--caches-only`). The tool refuses that form inside an agent shell.
- Read the guard's refusal message before approving a change to a guard.
- Review any change to `hooks/`, `settings.json` or `CLAUDE.md`. Agents cannot edit them, so the review is yours.

## Known limits

The tamper guard and the secret guard read command text. They are best-effort checks, not a sandbox. A script an agent writes
elsewhere and then runs can still do what its author wants. Layer 5 (you) and layer 1 (CI) cover that gap.
