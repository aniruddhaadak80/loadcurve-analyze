---
name: diagnose-infeasibility
description: Use when a plan has already failed screening and the question is which pair of limits is responsible, because most failures involve two limits that conflict jointly and neither is at fault alone.
metadata:
  version: 1.0.0
---

# Diagnose an infeasible plan

## When to use this

A study came back `infeasible` and you need the reason, not the failure.

## Steps

1. Run `loadcurve explain <study.json>`.

2. Read the core and check the `irredundant` flag. `true` means the engine verified minimality
   by removing each member and re-checking, so every constraint in it is load-bearing. If it
   says `false`, treat the set as a candidate and investigate further rather than reporting it
   as the answer.

3. Identify the coupling. A multi-member core always means the members interact. The usual
   pattern is a storage envelope pulling on injections at a bus whose path upstream is already
   thermally constrained: the state-of-charge floor wants more charge than the conductor allows.

4. Read the relaxation plan as the actionable output. Each entry gives a constraint, a side,
   the current bound, the required bound and the delta. Prefer the plan with the smallest total
   movement; `totalDelta` is the sum, and `optimal: true` means it was proven minimal rather
   than guessed.

5. Check whether a bound is genuinely fixed. If a limit comes from a grid code, a study
   agreement or a manufacturer rating, report the required movement and let the operator decide.
   Do not propose editing a binding document.

6. Re-run the study with the relaxation applied to confirm it now comes back `feasible`. A
   relaxation plan that does not actually restore feasibility is a bug, not a near miss.

## Reporting

State the core members, the mechanism that couples them, and the cheapest fix with its numbers.
An engineer can act on that directly; "the constraints are inconsistent" cannot be acted on.

## What not to do

- Do not report a violation list as an explanation. Every violated constraint explains itself;
  the core is what explains the failure.
- Do not widen the first limit you find until the study passes. The engine's relaxation plan is
  the cheapest route, and it is usually not the limit you would have picked first.
