export const meta = {
  name: 'need-simplicity-review',
  description: 'Attack a chunk from 5 angles of one question: do we need this, and is it simple enough to maintain? Defenders argue each finding back, blind checks on highs, Opus judge (report only)',
  phases: [{ title: 'Attack' }, { title: 'Defend' }, { title: 'Blind' }, { title: 'Judge', model: 'opus' }],
}
const A = args
const PRE = `Owner question for ${A.title}: "Do we need this, and is it simple enough to be maintained?" Report only: edit no repo file, commit nothing, write throwaway copies only under /private/tmp and delete them after.

## Target
- Repo ${A.repo}, branch ${A.branch} at ${A.head}. Chunk diff: \`git -C ${A.repo} diff ${A.base}..${A.head}\`.
- Also in scope, as it stands at ${A.head}: ${A.alsoInScope}
- Intent and plan: ${A.intent}
- Plan files: ${A.planDir}/plan.md (grep only), amendments.md (wins over plan.md), register.md (decisions, read the rows you cite).
- Checks already green at ${A.head}: ${A.checks}
- Run test suites only when no other run is active (they may share build output). Cloud accounts read only, if at all. Never print secrets or account numbers. Read narrowly. Budget about 45 tool calls: go deep.

## The reader
The person who maintains this after the build is one intern-level developer who did not write it. "Simple enough" means that person can change it safely in an afternoon.

## Each finding
piece (file:line range) | angle | what it is for, in one line | the problem | proof (a measurement, a command and its output, a /tmp deletion experiment, or a cited plan or decision line) | verdict: keep, simplify or delete | the smaller form and what it deletes (line count) | what protection, if any, is lost | severity (high: unneeded, or its upkeep clearly outweighs what it protects; medium: a simpler equal form exists; low: style).`
const FS = { type: 'object', properties: { findings: { type: 'array', items: { type: 'object', properties: { piece: { type: 'string' }, problem: { type: 'string' }, proof: { type: 'string' }, verdict: { type: 'string', enum: ['keep', 'simplify', 'delete'] }, smaller: { type: 'string' }, lost: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] } }, required: ['piece', 'problem', 'proof', 'verdict', 'smaller', 'lost', 'severity'] } }, kept: { type: 'string' }, notChecked: { type: 'string' } }, required: ['findings', 'kept', 'notChecked'] }
const ANGLES = [
  { key: 'necessity', text: 'Necessity. Trace every new or changed piece (each function, config entry, check, script branch, test helper, README section) to the thing that needs it: a planned chunk that will use it (grep plan.md and amendments.md), an accepted decision in register.md, or a real attack or failure you can state in one line. A piece nothing needs is a delete finding.' },
  { key: 'deletion-test', text: 'Deletion test. For each guard (validation, condition, check, readback, test), copy the repo files to /private/tmp, delete that one guard, and see what breaks: which test fails, and which bad input now gets through. Then check whether another layer already blocks the same thing. A guard whose deletion breaks nothing, or that another layer already covers, is a simplify or delete finding.' },
  { key: 'change-cost', text: 'Change cost for a new maintainer. In a /tmp copy, make 4 realistic future changes that the plan implies (pick them from plan.md) and count the files and lines each one touches and the tests you had to update. A change that touches many files for one idea is a finding.' },
  { key: 'duplication-layering', text: 'Duplication and layering. Map every rule that is written down more than once (the same list, pattern, limit or name typed in code, config, tests and docs), and every protection enforced by more than one layer. Each copy that can drift from the others is a finding; name the one place it should live.' },
  { key: 'complexity-alternatives', text: 'Complexity and simpler alternatives. Measure: lines per file, the 10 longest lines, functions over 30 lines, nesting depth, regexes, fixture sizes and near-copy fixtures, test-to-code ratio, comment density. Then ask whether a standard tool, library or platform feature already does a hand-written part, and show the smaller form.' },
]
phase('Attack')
const found = await parallel(ANGLES.map(a => () => agent(`${PRE}\n\nYour angle: ${a.text}`, { label: `attack:${a.key}`, phase: 'Attack', model: 'sonnet', schema: FS })))
phase('Defend')
const VS = { type: 'object', properties: { verdicts: { type: 'array', items: { type: 'object', properties: { index: { type: 'integer' }, verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNVERIFIED'] }, defence: { type: 'string' }, proof: { type: 'string' } }, required: ['index', 'verdict', 'defence', 'proof'] } } }, required: ['verdicts'] }
const def = await parallel(ANGLES.map((a, i) => () => {
  const f = found[i]
  if (!f || !f.findings.length) return Promise.resolve({ angle: a.key, verdicts: [] })
  return agent(`${PRE}\n\nLoad the skill verify-findings. You defend the code. For each finding below from the ${a.key} angle, make the strongest case that the piece IS needed or IS as simple as it can be: find the consumer, the failure it alone catches, or the reason the smaller form is worse. Use a different method from the attacker (if it measured, read the plan and decisions; if it read, run a /tmp experiment). Say CONFIRMED when the attacker is right despite your best defence, REFUTED when the defence holds, UNVERIFIED when neither side proves it. Number verdicts by the 0-based index.\n\nFindings:\n${JSON.stringify(f.findings)}`,
    { label: `defend:${a.key}`, phase: 'Defend', model: 'sonnet', schema: VS }).then(r => ({ angle: a.key, verdicts: r ? r.verdicts : null }))
}))
const highs = []
found.forEach((f, i) => { if (!f) return; f.findings.forEach((x, j) => { const v = (def[i].verdicts || []).find(v => v.index === j); if (x.severity === 'high' && (!v || v.verdict !== 'REFUTED')) highs.push({ angle: ANGLES[i].key, ...x }) }) })
const per = Math.max(1, Math.ceil(highs.length / 5)); const batches = []
for (let k = 0; k < highs.length; k += per) batches.push(highs.slice(k, k + per))
log(`high findings for blind check: ${highs.length} in ${batches.length} batches`)
phase('Blind')
const blind = await parallel(batches.map((b, k) => () => agent(`${PRE}\n\nBlind check. For each piece below, decide on your own whether it should be kept, simplified or deleted, and what deleting or simplifying it would lose. You are not shown anyone's reasoning. Run something for each (a /tmp deletion experiment, a grep of the plan for its consumer, a measurement).\n\nPieces:\n${JSON.stringify(b.map((h, n) => ({ n, piece: h.piece })))}`, { label: `blind:${k + 1}`, phase: 'Blind', model: 'sonnet' })))
phase('Judge')
const judged = await agent(`You are the adjudicator of the "do we need this, and is it simple enough to be maintained?" review of ${A.title}. Judge from the evidence only (one command allowed to settle a split). A finding two angles reach on their own goes up one severity. A delete or simplify verdict that loses real protection is wrong unless that protection is already enforced elsewhere. Write in plain words for an intern, no em dashes. Return the full report as your answer (do not write files):
1. The answer to the owner's question for the chunk as a whole, in one paragraph.
2. A table: piece | needed by (plan chunk, decision, or "nothing") | upkeep (files a change touches, lines) | verdict (keep, simplify, delete) | what it deletes | what is lost.
3. The confirmed simplify and delete findings, most valuable first, each with the smaller form and the proof.
4. UNVERIFIED ones with the command that would settle them; refuted ones in one line each; which agents failed or returned nothing.
5. The total lines the confirmed changes would delete, and the protections that stay.\n\nAttackers:\n${JSON.stringify(found.map((f, i) => ({ angle: ANGLES[i].key, result: f })))}\n\nDefenders:\n${JSON.stringify(def)}\n\nBlind checks (pieces in order of this list):\n${JSON.stringify({ highs: highs.map(h => ({ angle: h.angle, piece: h.piece })), blind })}`, { label: 'judge', phase: 'Judge', model: 'opus' })
return { notRun: ANGLES.filter((a, i) => !found[i]).map(a => a.key), defendFailed: def.filter(d => d && d.verdicts === null).map(d => d.angle), highs: highs.length, judged }
