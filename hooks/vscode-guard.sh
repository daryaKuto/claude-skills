#!/bin/bash
# PostToolUse(Bash) hook: after a git clone, remove the cloned repo's .vscode
# directory unless the repo is owned by a GitHub user or org listed in config.json trusted_github_owners (case-insensitive).
# Rationale: .vscode/tasks.json can carry autorun tasks that execute on folder
# open, a known supply-chain RCE vector. This is a best-effort mitigation, not
# a substitute for reviewing untrusted repos before opening them in an editor.

set -euo pipefail

input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
[[ -z "$cmd" ]] && exit 0

echo "$cmd" | grep -qE '(^|[;&|]|[[:space:]])git[[:space:]]+clone([[:space:]]|$)' || exit 0

segment=$(echo "$cmd" | grep -oE 'git[[:space:]]+clone[^;&|]*' | head -1)
[[ -z "$segment" ]] && exit 0

# Never eval the command text: `eval` here ran any $(...) or backtick inside a clone line a second
# time, from the hook (reproduced with a touch probe). Expansion
# characters mean the target cannot be read safely, so skip; quotes are stripped, then split on spaces.
[[ "$segment" =~ [\$\`\(\)\\] ]] && exit 0
segment=${segment//\"/}
segment=${segment//\'/}
read -r -a tokens <<< "$segment"

value_flags=(--branch -b --depth --origin -o --config -c --reference \
  --reference-if-able --separate-git-dir --shallow-since --shallow-exclude \
  --filter --template -j --jobs --bundle-uri)

positional=()
skip_next=0
# A quiet clone (-q, --quiet, stderr redirected) prints no "Cloning into" line, so the output check below cannot run.
quiet=0
re_err='git[[:space:]]+clone([^;|&]|&>)*(2>|&>)'
[[ "$cmd" =~ $re_err ]] && quiet=1
re_redir='^[0-9&]*>+'
re_bare='^[0-9&]*>+$'
re_q='^-[a-zA-Z]*q[a-zA-Z0-9]*$'
# tokens[0]=git tokens[1]=clone
for tok in "${tokens[@]:2}"; do
  if [[ $skip_next -eq 1 ]]; then
    skip_next=0
    continue
  fi
  # redirections are not arguments: `2>/dev/null`, `2>`, `2> /dev/null`, `>`
  if [[ "$tok" =~ $re_redir ]]; then
    [[ "$tok" =~ $re_bare ]] && skip_next=1
    continue
  fi
  if [[ "$tok" == --quiet || "$tok" == -q ]]; then
    quiet=1
    continue
  fi
  # a cluster may end in a glued number (-qj4): still a cluster, and its q still means quiet
  if [[ "$tok" =~ ^-[a-zA-Z][a-zA-Z0-9]+$ ]]; then
    [[ "$tok" =~ $re_q ]] && quiet=1
    # a cluster like -vb or -qb ends in a letter that takes a value (b o c j u): that value is the next word
    [[ "$tok" =~ [bocju]$ ]] && skip_next=1
    continue
  fi
  if [[ "$tok" == -* ]]; then
    for vf in "${value_flags[@]}"; do
      if [[ "$tok" == "$vf" ]]; then
        skip_next=1
        break
      fi
    done
    continue
  fi
  positional+=("$tok")
done

url="${positional[0]:-}"
dir="${positional[1]:-}"
[[ -z "$url" ]] && exit 0
# git prints the folder without its trailing slash, and the output check below matches that text.
while [[ "$dir" == */ && "$dir" != "/" ]]; do dir="${dir%/}"; done

if [[ -z "$dir" ]]; then
  base=$(basename "$url")
  dir="${base%.git}"
fi

[[ -d "$dir" ]] || exit 0

remote=$(git -C "$dir" remote get-url origin 2>/dev/null || echo "$url")

owner=""
if [[ "$remote" =~ github\.com[:/]+([^/]+)/ ]]; then
  owner="${BASH_REMATCH[1]}"
fi

owner_lower=$(echo "$owner" | tr '[:upper:]' '[:lower:]')
cfg="${CLAUDE_HOOKS_CONFIG:-$(cd "$(dirname "$0")" && pwd)/config.json}"
# An unreadable or missing config means nobody is trusted, so every cloned .vscode is removed.
if [[ -n "$owner_lower" ]] && jq -e --arg o "$owner_lower" '[.trusted_github_owners[]? | ascii_downcase] | index($o) != null' "$cfg" >/dev/null 2>&1; then
  exit 0
fi

# Only a clone that just succeeded made this folder. A failed clone ("fatal: destination path ... already
# exists") leaves an older checkout there, and its .vscode is not ours to delete. The PostToolUse payload
# carries the output in tool_response (stdout and stderr, no exit code): git prints "Cloning into '<dir>'"
# for a real clone and "fatal:" when it stops. If the output is missing or unclear, do nothing.
resp=$(echo "$input" | jq -r '.tool_response | if type=="object" then ((.stderr // "") + "\n" + (.stdout // "")) elif type=="string" then . else "" end' 2>/dev/null || true)
if [[ $quiet -eq 1 ]]; then
  # No "Cloning into" line to read. A failed clone into an existing repo (`|| true`, `; echo`) also reaches this hook,
  # so prove the folder was cloned just now: the oldest HEAD reflog entry is "clone: from" and under 120 s old.
  first=$(git -C "$dir" reflog --date=unix --format='%gd|%gs' 2>/dev/null | tail -1 || true)
  if [[ -z "$first" ]]; then
    # No reflog at all (core.logAllRefUpdates=false): fall back to when .git was created (macOS birth time).
    # shortcut: other systems have no portable birth time, so the folder is left alone there.
    [[ "$(uname)" == Darwin ]] || exit 0
    born=$(stat -f %B "$dir/.git" 2>/dev/null || true)
    [[ "$born" =~ ^[0-9]+$ ]] || exit 0
    (( $(date +%s) - born <= 120 )) || exit 0
  else
    [[ "$first" =~ ^HEAD@\{([0-9]+)\}\|clone:\ from ]] || exit 0
    (( $(date +%s) - BASH_REMATCH[1] <= 120 )) || exit 0
  fi
else
  grep -qF "Cloning into '$dir'" <<< "$resp" || exit 0
  grep -qE '^(fatal|error):' <<< "$resp" && exit 0
fi

if [[ -d "$dir/.vscode" ]]; then
  rm -rf "$dir/.vscode"
  msg="Removed .vscode/ from cloned repo '$dir' (GitHub owner: ${owner:-unknown}) as a precaution against malicious autorun tasks.json. Review it manually if you need those editor settings."
  jq -n --arg m "$msg" '{"systemMessage": $m}'
fi

exit 0
