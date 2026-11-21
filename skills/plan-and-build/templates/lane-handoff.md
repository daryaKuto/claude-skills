# Lane handoff: <lane name>

Lives at `docs/plans/<orchestrator plan>/lanes/<lane>/handoff.md`. Kept briefs, rulings and logs go in `scratch/` next to it.
Throwaway files go in the session scratchpad. Use git, not `.bak` copies.

## Now
Overwritten at every step: status, what is running, the next step.

## Pinned
Never overwritten: owner rulings that bind this lane, each with its date.

## Done
One line per finished item, with its proof (command and result, PR or commit).

## Open
Items left, each with why it is not done.

## For the orchestrator
What changed for the shared plan docs (plan, register, progress, decision record) that the orchestrator must copy over.

## Log
Append-only. One dated line per state change.
