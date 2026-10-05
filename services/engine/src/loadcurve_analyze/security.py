"""`contingency` — the N-1 security screen.

A plan that is feasible in the base case is not secure. The question an operator actually
has to answer before committing is: *if we lose this one element, does the plan still hold?*

So each declared outage is applied, the network is re-factored from scratch (a contingency
changes the admittance matrix, so the PTDF is genuinely different — this is not a
post-processing shortcut), every constraint is re-evaluated, and any resulting violation is
attributed to its own minimal core so the contingency is explained as precisely as the base
case is.

Three outcomes, never two:

``secure``     the plan survives the outage within every constraint.
``violated``   it does not, and a core says which constraints disagree.
``islanded``   dropping the branch split the network, so no DC power flow exists. This is
               reported as its own status rather than folded into ``violated``, because an
               islanded feeder is a categorically different operational problem from an
               overloaded one and an operator must not have to infer which happened.
"""

from __future__ import annotations

from typing import TypedDict

from . import topology
from .cores import minimal_core, satisfiable
from .model import Constraint, DispatchPlan, NetworkModel
from .propagate import propagate


class Outage(TypedDict):
    id: str
    branchId: str
    label: str


class ContingencyResult(TypedDict):
    outageId: str
    branchId: str
    label: str
    status: str
    violations: list[str]
    core: list[str]
    worstExcessMw: float


class SecurityReport(TypedDict):
    baseFeasible: bool
    contingencies: list[ContingencyResult]
    secure: int
    violated: int
    islanded: int


def _outaged(model: NetworkModel, branch_id: str) -> NetworkModel:
    """The model with one branch out of service.

    Returning a new model rather than mutating is what keeps the base case intact: the same
    base result is reused for every outage, so an N-element screen costs one base
    propagation plus N outaged ones rather than re-deriving the base each time.
    """
    return {
        **model,
        "branches": [branch for branch in model["branches"] if branch["id"] != branch_id],
    }


def contingency(
    model: NetworkModel,
    plan: DispatchPlan,
    constraints: list[Constraint],
    outages: list[Outage],
    budget: int,
    explain: bool = True,
) -> SecurityReport:
    """Re-screen the plan against each single-element outage."""
    active = [constraint for constraint in constraints if constraint["enabled"]]
    base = propagate(model, plan, active, budget)

    results: list[ContingencyResult] = []
    secure = 0
    violated = 0
    islanded = 0

    seen: set[str] = set()
    for outage in sorted(outages, key=lambda item: item["id"]):
        branch_id = outage["branchId"]
        if branch_id in seen:
            continue
        seen.add(branch_id)

        if branch_id not in {branch["id"] for branch in model["branches"]}:
            raise ValueError(f"outage target {branch_id!r} is not an in-service branch")

        outaged_model = _outaged(model, branch_id)
        topo = topology.build_topology(
            [bus["id"] for bus in model["buses"]],
            [
                (branch["id"], branch["fromBus"], branch["toBus"], branch["reactancePu"])
                for branch in outaged_model["branches"]
            ],
            model["slackBus"],
        )

        if not topo["connected"]:
            islanded += 1
            results.append(
                {
                    "outageId": outage["id"],
                    "branchId": branch_id,
                    "label": outage["label"],
                    "status": "islanded",
                    "violations": [],
                    "core": [],
                    "worstExcessMw": 0.0,
                }
            )
            continue

        screened = propagate(outaged_model, plan, active, budget)

        if screened["feasible"]:
            secure += 1
            results.append(
                {
                    "outageId": outage["id"],
                    "branchId": branch_id,
                    "label": outage["label"],
                    "status": "secure",
                    "violations": [],
                    "core": [],
                    "worstExcessMw": 0.0,
                }
            )
            continue

        violated += 1
        core_ids: list[str] = []
        if explain and screened["fixpoint"]:
            core_ids = minimal_core(outaged_model, plan, active, budget)["constraintIds"]

        worst = max((q["excessMw"] for q in screened["quantities"]), default=0.0)
        results.append(
            {
                "outageId": outage["id"],
                "branchId": branch_id,
                "label": outage["label"],
                "status": "violated",
                "violations": screened["violations"],
                "core": core_ids,
                "worstExcessMw": worst,
            }
        )

    return {
        "baseFeasible": base["feasible"],
        "contingencies": results,
        "secure": secure,
        "violated": violated,
        "islanded": islanded,
    }


def base_feasible(
    model: NetworkModel, plan: DispatchPlan, constraints: list[Constraint], budget: int
) -> bool:
    """Convenience predicate for callers that only need the base-case verdict."""
    return satisfiable(model, plan, [c for c in constraints if c["enabled"]], budget)
