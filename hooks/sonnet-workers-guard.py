#!/usr/bin/env python3
"""PreToolUse guard: workers run on Sonnet; only judges and adjudicators may run on Opus.

Global rule (~/.claude/CLAUDE.md, "Orchestration"): every worker subagent is Sonnet;
adjudicators (judge, panel, adjudicator, chairman, synthesizer) run on Opus. An Agent call
with no model, or a fork, inherits the session model (Opus), so it is denied too.
Workflow scripts are checked call by call: every agent() names its model, and an Opus one
must carry a judge-type label. Rule: the worker sonnet must be enforced.
"""
import json
import os
import re
import sys

JUDGE = re.compile(r"judge|panel|adjudicat|chair|synth|re-?judge|cross-judge|judgment|explainer|reflect|divergent", re.I)
# A role word counts only when it is used as the agent's role, within the first 3 words, in one of ROLE_SHAPES.
# "reflect the layout fix" or "panel layout bug" is a worker with a role word inside it, so it is denied.
ROLE_SHAPES = ("a role word first or right after opus/fable/pstack/council ('Opus judge round 2', 'council chairman', 'pstack judgment'), "
               "followed by ':' or '-' or a round number ('judge-r1:opus', 'judge-3'), by 'for/of ...' ('explainer for how'), "
               "or first and followed by a verb ending in s ('synthesizer merges three drafts'). Not 'panel layout bug' or 'reflect the layout fix'")
PREFIX_WORDS = {"opus", "fable", "pstack", "council", "cross", "re"}


def role_ok(text: str) -> bool:
    ws = list(re.finditer(r"\w+", text or ""))
    for i, m in enumerate(ws[:3]):
        if not re.match(JUDGE.pattern + r"\w*$", m.group(0), re.I):
            continue
        if i and not all(w.group(0).lower() in PREFIX_WORDS for w in ws[:i]):
            continue
        nxt = ws[i + 1].group(0) if i + 1 < len(ws) else ""
        between = text[m.end():ws[i + 1].start()] if nxt else ""
        if (i or len(ws) <= 2 or re.search(r"[:\-]", between) or re.fullmatch(r"r?\d+", nxt, re.I) or nxt.lower() in ("for", "of")
                or re.fullmatch(r"\w*[^s\W]s", nxt) and nxt.lower() not in ("this", "its", "as")):
            return True
    return False
# Role words are read only from an Agent call's description or a Workflow agent's label/phase, never from the prompt.
# pstack's Opus roles (pstack-models.md: judgment, how explainer, reflect, divergent) need these words.
# Optional time-boxed grant: while the epoch (seconds) in the opus-workers-until file is in the future, an explicitly named Opus worker is allowed. A call with no
# model (or a fork) is still denied, so nothing inherits the session model by accident. The grant ends on its own.
OPUS_UNTIL = os.environ.get("OPUS_WORKERS_UNTIL_FILE") or os.path.expanduser("~/.claude/hooks/opus-workers-until")  # env override is for the cases file


def opus_granted(model: str) -> bool:
    try:
        with open(OPUS_UNTIL, encoding="utf-8") as f:
            until = float(f.read().strip())
    except (OSError, ValueError):
        return False
    import time
    return model.startswith("opus") and time.time() < until
CALL = re.compile(r"\bagent\s*\(")
MODEL = re.compile(r"\bmodel\s*:\s*['\"`]([a-z0-9.\-]+)['\"`]", re.I)
LABEL = re.compile(r"\b(label|phase)\s*:\s*[`'\"]([^`'\"]*)", re.I)


def deny(why: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": why + " Workers run on Sonnet (model: \"sonnet\"); only a judge, panel, adjudicator, chairman or synthesizer may use Opus, and its description or label must say so. Accepted shapes: " + ROLE_SHAPES + ".",
    }}))
    sys.exit(0)


def check_agent(inp: dict) -> None:
    if inp.get("subagent_type") == "fork":
        deny("A fork always runs on the session model (Opus).")
    model = (inp.get("model") or "").lower()
    if not model:
        deny("This Agent call names no model, so it would inherit the session model (Opus).")
    if model.startswith("sonnet") or model.startswith("haiku") or opus_granted(model):
        return
    if role_ok(inp.get("description", "")):
        return
    deny(f"This Agent call asks for model '{model}' but its description does not name a judge-type role.")


def check_script(text: str) -> None:
    starts = [m.start() for m in CALL.finditer(text)]
    for i, s in enumerate(starts):
        seg = text[s: starts[i + 1] if i + 1 < len(starts) else len(text)]
        models = MODEL.findall(seg)
        line = text.count("\n", 0, s) + 1
        if not models:
            deny(f"Workflow agent() call at script line {line} names no model, so it inherits Opus.")
        m = models[0].lower()
        if m.startswith("sonnet") or m.startswith("haiku") or opus_granted(m):
            continue
        if not any(role_ok(v) for _, v in LABEL.findall(seg)):
            deny(f"Workflow agent() call at script line {line} uses model '{m}' without a judge-type label or phase.")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    name, inp = data.get("tool_name"), data.get("tool_input") or {}
    if name == "Agent":
        check_agent(inp)
    elif name == "Workflow":
        text = inp.get("script")
        if not text and inp.get("scriptPath"):
            try:
                with open(os.path.expanduser(inp["scriptPath"]), encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                return
        if text:
            check_script(text)


if __name__ == "__main__":
    main()
