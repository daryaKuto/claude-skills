#!/usr/bin/env python3
"""Token cost of one Workflow run, per agent, from its transcripts. Run it after every loop.

Why: each tool call re-reads the agent's whole context, so cache READS dominate a verification
run (97% of tokens in a measured 72-agent run). This shows which agent spent them and whether
anything was reused across agents, so the next loop is sized from real numbers.

Usage:
  python3 run-cost.py latest            # newest workflow run of any session on this machine
  python3 run-cost.py <run dir>         # ~/.claude/projects/<proj>/<session>/subagents/workflows/<wf_...>
  python3 run-cost.py <run dir> --json  # machine-readable, for the register

"weight" is a relative cost in input-token equivalents, using Anthropic's published ratios
(cache read 0.1x input, 5-minute cache write 1.25x, output 5x for Sonnet). It is for comparing
runs and agents, not a bill.
"""
import glob, json, os, sys

def find_latest():
    runs = glob.glob(os.path.expanduser("~/.claude/projects/*/*/subagents/workflows/wf_*"))
    return max(runs, key=os.path.getmtime) if runs else None

def agent_rows(run):
    rows = []
    for f in sorted(glob.glob(os.path.join(run, "agent-*.jsonl")), key=os.path.getmtime):
        meta = {}
        mf = f[:-len(".jsonl")] + ".meta.json"
        if os.path.exists(mf):
            try:
                meta = json.load(open(mf))
            except ValueError:
                pass
        calls, last_id = [], None
        for line in open(f):
            try:
                msg = json.loads(line).get("message") or {}
            except ValueError:
                continue
            u = msg.get("usage")
            if u and msg.get("id") != last_id:  # one API call can span several transcript lines
                calls.append(u)
                last_id = msg.get("id")
        if not calls:
            continue
        s = lambda k: sum(c.get(k, 0) or 0 for c in calls)
        r = {"agent": (meta.get("label") or meta.get("description") or os.path.basename(f))[:32],
             "calls": len(calls), "cache_read": s("cache_read_input_tokens"),
             "cache_write": s("cache_creation_input_tokens"), "uncached_in": s("input_tokens"),
             "out": s("output_tokens"), "first_call_read": calls[0].get("cache_read_input_tokens", 0) or 0,
             "first_call_write": calls[0].get("cache_creation_input_tokens", 0) or 0}
        r["weight"] = round(r["cache_read"] * 0.1 + r["cache_write"] * 1.25 + r["uncached_in"] + r["out"] * 5)
        rows.append(r)
    return rows

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    run = find_latest() if sys.argv[1] == "latest" else sys.argv[1]
    if not run or not os.path.isdir(run):
        sys.exit(f"no workflow run found at {run}")
    rows = agent_rows(run)
    tot = {k: sum(r[k] for r in rows) for k in ("calls", "cache_read", "cache_write", "uncached_in", "out", "weight")}
    if "--json" in sys.argv:
        print(json.dumps({"run": run, "agents": rows, "total": tot}, indent=1))
        return
    print(f"run: {run}\n{len(rows)} agents")
    print(f"{'agent':32} {'calls':>5} {'cache read':>11} {'cache write':>11} {'out':>7} {'weight':>9}")
    for r in sorted(rows, key=lambda r: -r["weight"]):
        print(f"{r['agent']:32} {r['calls']:>5} {r['cache_read']:>11,} {r['cache_write']:>11,} {r['out']:>7,} {r['weight']:>9,}")
    print(f"{'TOTAL':32} {tot['calls']:>5} {tot['cache_read']:>11,} {tot['cache_write']:>11,} {tot['out']:>7,} {tot['weight']:>9,}")
    if rows:
        reused = [r for r in rows if r["first_call_read"] > min(x["first_call_read"] for x in rows if x["first_call_read"]) * 1.2] if any(x["first_call_read"] for x in rows) else []
        print(f"avg per agent: {tot['calls'] / len(rows):.1f} calls, {tot['cache_read'] / len(rows):,.0f} cache-read tokens")
        print(f"shared-prefix reuse across agents: {'yes, ' + str(len(reused)) + ' agents read more than the system prompt on call 1' if reused else 'none (each agent wrote its own first message)'}")

if __name__ == "__main__":
    main()
