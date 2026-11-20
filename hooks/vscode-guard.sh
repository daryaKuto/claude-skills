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
# tokens[0]=git tokens[1]=clone
for tok in "${tokens[@]:2}"; do
  if [[ $skip_next -eq 1 ]]; then
    skip_next=0
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
grep -qF "Cloning into '$dir'" <<< "$resp" || exit 0
grep -qE '^(fatal|error):' <<< "$resp" && exit 0

if [[ -d "$dir/.vscode" ]]; then
  rm -rf "$dir/.vscode"
  msg="Removed .vscode/ from cloned repo '$dir' (GitHub owner: ${owner:-unknown}) as a precaution against malicious autorun tasks.json. Review it manually if you need those editor settings."
  jq -n --arg m "$msg" '{"systemMessage": $m}'
fi

exit 0
