---
name: screen-dispatch-plan
description: Use when a proposed dispatch or interconnection plan must be proven admissible against thermal, export, storage and ramp limits, because a violation found in commissioning is far more expensive than one found on paper.
metadata:
  version: 1.0.0
---

# Screen a dispatch plan

## When to use this

A plan exists — a network model plus a dispatch proposal — and someone needs to know whether
it can actually be dispatched before committing it.

## Steps

1. Write the study to a JSON file: `model`, `plan`, `constraints`, and any `outages`. Start
   from `loadcurve verify example --json` and edit, or take the request the user already has.

2. Declare every hard constraint explicitly. The five kinds are `line_thermal` (one branch),
   `branch_group` (net across several branches), `poi_export` (net injection over buses),
   `storage_soc` (a unit's charge envelope) and `ramp` (per-interval change). An undeclared
   limit is a limit the engine cannot check.

3. Scope a constraint to a window when it only binds part of the horizon. A grid code's
   "70% charged by hour 2" is `fromInterval: 1`; without it the floor is wrongly reported as
   violated in hour 1, where it does not apply.

4. Run `loadcurve verify <study.json>`.

5. Read the verdict:
   - `feasible` — the plan is admissible. Report the digest so the run can be reproduced.
   - `infeasible` — go to step 6.
   - `undetermined` — the plan declares `partial` and leaves a bus unbounded, so no conclusion
     is possible. Name the unconstrained bus rather than guessing a value for it.

6. On `infeasible`, run `loadcurve explain <study.json>` and report the **core**. The core is
   the smallest contradictory set, and every member of it is necessary. Do not summarise it as
   "some constraints conflict" — the operator needs the specific pairs.

7. Report the relaxation plan as numbers an operator can negotiate: which bound moves, from
   what, to what. If `optimal` is `false`, say the total is a best effort rather than a proven
   minimum.

8. If outages were declared, report the N-1 screen separately from the base case. A plan can be
   feasible and still not secure, and `islanded` is a different problem from `violated`.

## Verify

The digest in the output is stable: re-running the same study prints the same
`sha256:...`. If it changed, the inputs changed.

## What not to do

- Do not hand-check flows against ratings. That is the work this tool exists to replace.
- Do not relax a grid-code limit to make a plan pass without saying so. The relaxation output
  names exactly which bound you would have to move; that conversation belongs to the operator.
- Do not treat a singleton core as the whole story. A singleton means one limit is violated on
  its own; the interesting failures are the two- and three-member cores where no single limit
  is at fault.
