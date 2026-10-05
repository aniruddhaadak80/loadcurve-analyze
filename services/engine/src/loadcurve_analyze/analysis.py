"""The engine's operation table — the only surface the host can reach.

Each entry is a named pure function over validated input. There is no server, no port, and
no state that survives a call, so two concurrent invocations cannot interfere and a result
can be cached by its content address.

The five operations are the product:

``propagate``    tighten every constraint to a fixed point, or report the violation
``minimal_core`` the smallest contradictory subset, verified minimal before it is returned
``relaxation``  the minimum total bound movement that makes that core satisfiable
``contingency``  the N-1 screen, with a core per violated outage
``study``       all of the above plus the input digest, in one call
``digest``      the content address of any study, on its own
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, TypedDict

from . import digest as digest_module
from . import intervals
from .cores import Core, minimal_core
from .model import parse_budget, parse_constraints, parse_model, parse_plan
from .protocol import EngineError
from .propagate import PropagationResult
from .propagate import propagate as run_propagate
from .relax import RelaxationPlan
from .relax import relaxation as run_relaxation
from .security import Outage, SecurityReport
from .security import contingency as run_contingency


class StudyInput(TypedDict):
    model: Any
    plan: Any
    constraints: Any
    outages: Any
    budget: Any
    explain: bool


def _outages(raw: Any, model: Any) -> list[Outage]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise EngineError("BAD_SHAPE", "outages must be an array")
    branch_ids = {branch["id"] for branch in model["branches"]}
    outages: list[Outage] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise EngineError("BAD_SHAPE", f"outages[{index}] must be an object")
        outage_id = entry.get("id")
        branch_id = entry.get("branchId")
        if not isinstance(outage_id, str) or not outage_id:
            raise EngineError("MISSING_FIELD", f"outages[{index}].id must be a non-empty string")
        if not isinstance(branch_id, str) or not branch_id:
            raise EngineError("MISSING_FIELD", f"outages[{index}].branchId must be a non-empty string")
        if branch_id not in branch_ids:
            raise EngineError("UNKNOWN_BRANCH", f"outages[{index}].branchId {branch_id!r} is not in service")
        outages.append(
            {"id": outage_id, "branchId": branch_id, "label": str(entry.get("label", branch_id))}
        )
    return outages


class StudyResult(TypedDict):
    inputDigest: str
    engineVersion: str
    propagation: PropagationResult
    core: Core
    relaxation: RelaxationPlan
    security: SecurityReport
    verdict: str


def study(payload: StudyInput) -> StudyResult:
    """The full analysis: propagation, core, relaxation, and the N-1 screen."""
    if not isinstance(payload, dict):
        raise EngineError("BAD_SHAPE", "study input must be an object")
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    budget = parse_budget(payload.get("budget"))
    outages = _outages(payload.get("outages"), model)
    explain = payload.get("explain", True)
    if not isinstance(explain, bool):
        raise EngineError("BAD_SHAPE", "explain must be a boolean")

    input_address = digest_module.digest(
        {"model": model, "plan": plan, "constraints": constraints}
    )

    propagation = run_propagate(model, plan, constraints, budget)
    core = minimal_core(model, plan, constraints, budget)
    relaxation: RelaxationPlan = {
        "feasible": True,
        "optimal": True,
        "totalDelta": 0.0,
        "relaxations": [],
        "combinations": 0,
    }
    if not core["feasible"]:
        relaxation = run_relaxation(model, plan, core["constraintIds"], constraints)
    security = run_contingency(model, plan, constraints, outages, budget, explain)

    return {
        "inputDigest": input_address,
        "engineVersion": ENGINE_VERSION,
        "propagation": propagation,
        "core": core,
        "relaxation": relaxation,
        "security": security,
        "verdict": (
            "feasible"
            if propagation["feasible"]
            else "infeasible"
        ),
    }


def propagate_op(payload: dict[str, Any]) -> PropagationResult:
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    return run_propagate(model, plan, constraints, parse_budget(payload.get("budget")))


def minimal_core_op(payload: dict[str, Any]) -> Core:
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    return minimal_core(model, plan, constraints, parse_budget(payload.get("budget")))


def relaxation_op(payload: dict[str, Any]) -> RelaxationPlan:
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    budget = parse_budget(payload.get("budget"))
    core = minimal_core(model, plan, constraints, budget)
    if core["feasible"]:
        return {
            "feasible": True,
            "optimal": True,
            "totalDelta": 0.0,
            "relaxations": [],
            "combinations": 0,
        }
    return run_relaxation(model, plan, core["constraintIds"], constraints)


def contingency_op(payload: dict[str, Any]) -> SecurityReport:
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    outages = _outages(payload.get("outages"), model)
    budget = parse_budget(payload.get("budget"))
    explain = payload.get("explain", True)
    if not isinstance(explain, bool):
        raise EngineError("BAD_SHAPE", "explain must be a boolean")
    return run_contingency(model, plan, constraints, outages, budget, explain)


def digest_op(payload: dict[str, Any]) -> dict[str, Any]:
    model = parse_model(payload.get("model"))
    plan = parse_plan(payload.get("plan"), model)
    constraints = parse_constraints(payload.get("constraints"), model)
    return {
        "modelDigest": digest_module.digest(model),
        "studyDigest": digest_module.digest(
            {"model": model, "plan": plan, "constraints": constraints}
        ),
    }


OPERATIONS: Final[dict[str, Callable[[Any], Any]]] = {
    "study": study,
    "propagate": propagate_op,
    "minimal_core": minimal_core_op,
    "relaxation": relaxation_op,
    "contingency": contingency_op,
    "digest": digest_op,
}

ENGINE_VERSION: Final[str] = "0.1.0"

#: Exported so a host can round-check a bound without duplicating the tolerance.
EPSILON: Final[float] = intervals.EPS


def analyse(op: str, payload: Any) -> Any:
    handler = OPERATIONS.get(op)
    if handler is None:
        known = ", ".join(sorted(OPERATIONS))
        raise EngineError("UNKNOWN_OP", f"unknown op {op!r}; available: {known}")
    return handler(payload)
