"""`minimal_core` — the smallest set of constraints that is already contradictory.

This is the small explanation problem, and it is the reason the product exists. An operator
who is told "the plan is infeasible" still has to find out *why*. Today that means deleting
constraints by hand, one at a time, re-running the study, and hoping the last one removed was
not the load-bearing one.

The algorithm is deletion-based (a.k.a. linear-must-fix), and it is chosen over
QuickXplain because it is one pass, needs no oracle instrumentation, and is trivially
deterministic — the core it returns depends only on the input order, never on timing or
hash iteration:

    for each constraint c in order:
        if the set without c is still infeasible:
            drop c

The result is guaranteed minimal: removing any remaining member makes the set satisfiable.
That guarantee is not asserted here, it is *verified* before the core is returned, and the
verification is reported as ``irredundant``. An operator filing a study deserves a
certificate, not a promise.
"""

from __future__ import annotations

from typing import TypedDict

from .model import Constraint, DispatchPlan, NetworkModel
from .propagate import propagate


class Core(TypedDict):
    feasible: bool
    constraintIds: list[str]
    irredundant: bool
    checks: int


def satisfiable(
    model: NetworkModel,
    plan: DispatchPlan,
    constraints: list[Constraint],
    budget: int,
) -> bool:
    """Is there any dispatch inside the plan's windows that satisfies every constraint?

    Because bound propagation is exact over linear forms, this is a decision procedure, not
    a heuristic: ``False`` means no admissible dispatch exists.
    """
    if not constraints:
        return True
    return propagate(model, plan, constraints, budget)["feasible"]


def _enabled(constraints: list[Constraint]) -> list[Constraint]:
    return [constraint for constraint in constraints if constraint["enabled"]]


def minimal_core(
    model: NetworkModel,
    plan: DispatchPlan,
    constraints: list[Constraint],
    budget: int,
) -> Core:
    """Deletion-based extraction of a minimal unsatisfiable subset."""
    active = _enabled(constraints)
    checks = 0

    if satisfiable(model, plan, active, budget):
        checks += 1
        return {"feasible": True, "constraintIds": [], "irredundant": True, "checks": checks}

    core = list(active)
    for candidate in list(core):
        trial = [constraint for constraint in core if constraint["id"] != candidate["id"]]
        checks += 1
        if not satisfiable(model, plan, trial, budget):
            # Dropping this constraint did not restore satisfiability, so it is not part of
            # the explanation.
            core = trial

    core_ids = [constraint["id"] for constraint in core]

    # Verify minimality rather than trusting the algorithm. This is the certificate.
    irredundant = True
    for candidate_id in core_ids:
        trial = [constraint for constraint in core if constraint["id"] != candidate_id]
        checks += 1
        if not satisfiable(model, plan, trial, budget):
            irredundant = False
            break

    return {"feasible": False, "constraintIds": core_ids, "irredundant": irredundant, "checks": checks}
