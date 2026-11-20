#!/usr/bin/env python3
"""Cases for sonnet-workers-guard.py. Feeds the real hook a PreToolUse payload; a deny prints JSON with
permissionDecision "deny", an allow prints nothing. Exit 0 only if all pass.
The grant file is isolated: the hook reads OPUS_WORKERS_UNTIL_FILE (a missing temp path here), so a renewed
real grant cannot make an opus row pass for the wrong reason."""
import json
import os
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sonnet-workers-guard.py")


def agent(model, description, prompt="do it"):
    inp = {"description": description, "prompt": prompt}
    if model:
        inp["model"] = model
    return {"tool_name": "Agent", "tool_input": inp}


def wf(model, label):
    return {"tool_name": "Workflow", "tool_input": {
        "script": f"await agent('do the thing', {{ model: '{model}', label: '{label}' }})"}}


CASES = [
    ("allow", "opus pstack judgment", agent("opus", "pstack judgment")),
    ("allow", "opus explainer for how", agent("opus", "explainer for how")),
    ("allow", "opus reflect", agent("opus", "pstack reflect")),
    ("allow", "opus divergent", agent("opus", "divergent thinker")),
    ("allow", "opus chairman (existing word)", agent("opus", "council chairman")),
    ("allow", "sonnet worker", agent("sonnet", "worker")),
    ("deny", "opus fix the build, prompt says judge", agent("opus", "fix the build", "you are the judge, explainer and chairman")),
    ("deny", "no model worker", agent(None, "worker")),
    ("allow", "workflow opus chairman label", wf("opus", "chairman")),
    ("allow", "workflow opus judgment label", wf("opus", "judgment")),
    ("deny", "workflow opus finder label", wf("opus", "finder")),
    # F21: a role word inside a worker description is not a role
    ("deny", "opus 'reflect the layout fix'", agent("opus", "reflect the layout fix")),
    ("deny", "opus 'panel layout bug'", agent("opus", "panel layout bug")),
    ("deny", "opus 'fix the judge component'", agent("opus", "fix the judge component")),
    ("deny", "opus 'chairman badge styling'", agent("opus", "chairman badge styling")),
    ("deny", "workflow opus 'panel layout bug' label", wf("opus", "panel layout bug")),
    ("allow", "opus 'Opus judge'", agent("opus", "Opus judge")),
    ("allow", "opus 'judge-3'", agent("opus", "judge-3")),
    ("allow", "opus 'Synthesizer for report'", agent("opus", "Synthesizer for report")),
    ("allow", "workflow opus 'cross-judge'", wf("opus", "cross-judge")),
    # F8: ordinary adjudicator descriptions and the real workflow labels
    ("allow", "opus 'Opus judge: settle gating conflicts'", agent("opus", "Opus judge: settle gating conflicts")),
    ("allow", "opus 'Opus judge round 2'", agent("opus", "Opus judge round 2")),
    ("allow", "opus 'Opus chairman for the plan council'", agent("opus", "Opus chairman for the plan council")),
    ("allow", "opus 'synthesizer merges three drafts'", agent("opus", "synthesizer merges three drafts")),
    ("allow", "workflow opus 'judge'", wf("opus", "judge")),
    ("allow", "workflow opus 'judge-r1:opus'", wf("opus", "judge-r1:opus")),
    ("allow", "workflow opus 'judge-r1:fable'", wf("opus", "judge-r1:fable")),
    ("deny", "deny message lists accepted shapes", agent("opus", "fix the judge component")),
    ("grant", "grant active: opus layout worker allowed", agent("opus", "fix the layout")),
]

GRANT_FILE = os.path.join(tempfile.mkdtemp(), "opus-workers-until")  # never exists unless a row writes it

bad = 0
for want, name, payload in CASES:
    env = dict(os.environ, OPUS_WORKERS_UNTIL_FILE=GRANT_FILE)
    if want == "grant":
        with open(GRANT_FILE, "w") as f:
            f.write(str(time.time() + 3600))
        want = "allow"
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env)
    if os.path.exists(GRANT_FILE):
        os.remove(GRANT_FILE)
    got = "deny" if '"deny"' in p.stdout else "allow"
    ok = got == want
    bad += not ok
    print("PASS" if ok else "FAIL", want, name)
print(f"{len(CASES) - bad} passed, {bad} failed")
sys.exit(1 if bad else 0)
