"""`propagate` — bound propagation over the dispatch decision, to a fixed point.

This is the heart of the product, so it is worth being precise about what it does and why
it is not the obvious thing.

The obvious implementation checks each constraint against the plan and reports which ones
fail. That version is nearly useless, and the reason is worth stating because it is the
whole justification for this module: **if every constraint is checked independently, then
every infeasibility has a singleton core.** "Line L23 is overloaded" explains itself. The
operator's actual question is why the plan that was supposed to work does not, and the
answer almost always involves several limits *jointly* — a thermal rating, an export cap,
and a state-of-charge ceiling that between them leave no admissible dispatch.

So the engine does not check constraints, it *propagates* them. The variables are the bus
injections in each interval; each constraint is a linear form over those variables; and
satisfying a constraint narrows the domains of the variables appearing in it. A tightened
domain then feeds the next constraint, which tightens further, until nothing changes. That
is arc consistency (bounds consistency, for linear forms) and it is what makes a core of
size two or three possible — and real.

Two properties make this exact rather than approximate:

1. **Everything is linear.** A branch flow is a PTDF row over injections. A state-of-charge
   at interval *i* is ``soc_0 + sum_{j<i} eff * P_j * hours_j / energy`` — a linear form in
   the earlier intervals, which is precisely what couples a storage envelope to the thermal
   limits upstream of it. No constraint kind needed a nonlinear solver.
2. **Back-projection is the inverse of forward evaluation.** For ``sum c_k x_k in [L, U]``,
   each ``x_k`` is narrowed by subtracting the other terms' contributions. Because the forms
   are linear, that narrowing is sound: it removes only values that provably cannot appear in
   any satisfying assignment.

The verdict is three-valued and that is not hedging. An empty domain is a *proof* of
infeasibility. Non-empty domains after a fixpoint are a proof that *some* admissible dispatch
exists, because the box itself is one. And an unbounded variable is neither: no conclusion
is possible, so it is reported as undetermined rather than guessed.
"""

from __future__ import annotations

import math
from typing import TypedDict

from . import topology
from .intervals import EPS
from .model import Constraint, DispatchPlan, NetworkModel, Storage
from .protocol import EngineError

INF = math.inf


class Domain(TypedDict):
    lower: float
    upper: float


class Quantity(TypedDict):
    """One constraint's status in one interval."""

    interval: int
    hours: float
    lower: float
    upper: float
    excessMw: float


class QuantitySeries(TypedDict):
    constraintId: str
    kind: str
    target: str
    label: str
    lower: float
    upper: float
    verdict: str
    excessMw: float
    series: list[Quantity]
    violations: list[int]


class VariableReport(TypedDict):
    id: str
    interval: int
    bus: str
    lower: float
    upper: float
    unbounded: bool
    narrowedBy: list[str]


class PropagationResult(TypedDict):
    intervals: int
    fixpoint: bool
    iterations: int
    verdict: str
    feasible: bool
    quantities: list[QuantitySeries]
    violations: list[str]
    variables: list[VariableReport]


def _var(interval: int, bus: str) -> str:
    return f"p{interval}:{bus}"


def _branch_specs(model: NetworkModel) -> list[topology.BranchSpec]:
    """The model's branches as the positional tuples topology consumes."""
    return [
        (branch["id"], branch["fromBus"], branch["toBus"], branch["reactancePu"])
        for branch in model["branches"]
    ]


class _Form(TypedDict):
    """A constraint's linear form over bus-injection variables, per interval.

    ``offset`` carries any constant term — currently only a storage unit's initial state of
    charge — so that the form is genuinely ``offset + sum(c_k * x_k)`` and every range
    computation has to account for it. Ignoring it would silently drop ``soc_0`` and make
    every storage envelope read as far too tight.
    """

    interval: int
    coefficients: dict[str, float]
    offset: float
    unbounded: bool


def _soc_coefficients(
    unit: Storage, interval: int, hours: list[float]
) -> tuple[dict[str, float], float]:
    """SOC at ``interval`` as a linear form over earlier injections, plus its constant term.

    ``soc_i = soc_0 + sum_{j<i} eff * P_j * hours_j / energy``

    Returns ``(coefficients, offset)`` where ``offset`` is ``soc_0``. This is the coupling
    that makes multi-constraint cores real: the storage envelope depends on injections at the
    storage bus, which the thermal limits upstream also constrain, so the two can conflict
    together when neither is violated alone.
    """
    scale = float(unit["efficiency"]) / float(unit["energyMwh"])
    coefficients = {_var(j, str(unit["bus"])): scale * hours[j] for j in range(interval)}
    return coefficients, float(unit["socFracInitial"])


def _form_for(
    constraint: Constraint,
    interval: int,
    plan: DispatchPlan,
    model: NetworkModel,
    factors: list[list[float]],
    order: list[str],
    branch_position: dict[str, int],
    hours: list[float],
) -> _Form:
    coefficients: dict[str, float] = {}
    offset = 0.0

    if constraint["kind"] == "line_thermal":
        position = branch_position.get(constraint["target"])
        if position is None:
            raise EngineError(
                "UNKNOWN_BRANCH",
                f"constraint {constraint['id']!r} targets out-of-service branch "
                f"{constraint['target']!r}",
            )
        row = factors[position]
        for bus_position, bus in enumerate(order):
            coefficient = row[bus_position]
            if coefficient != 0.0:
                coefficients[_var(interval, bus)] = coefficient

    elif constraint["kind"] == "branch_group":
        for member in constraint["members"]:
            position = branch_position.get(member)
            if position is None:
                raise EngineError(
                    "UNKNOWN_BRANCH",
                    f"constraint {constraint['id']!r} groups out-of-service branch {member!r}",
                )
            row = factors[position]
            for bus_position, bus in enumerate(order):
                coefficient = row[bus_position]
                if coefficient != 0.0:
                    key = _var(interval, bus)
                    coefficients[key] = coefficients.get(key, 0.0) + coefficient

    elif constraint["kind"] == "poi_export":
        for member in constraint["members"]:
            coefficients[_var(interval, member)] = coefficients.get(_var(interval, member), 0.0) + 1.0

    elif constraint["kind"] == "storage_soc":
        unit = next((u for u in model["storage"] if u["id"] == constraint["target"]), None)
        if unit is None:
            raise EngineError(
                "UNKNOWN_STORAGE", f"constraint {constraint['id']!r} targets unknown storage"
            )
        coefficients, offset = _soc_coefficients(unit, interval, hours)

    elif constraint["kind"] == "ramp":
        target = constraint["target"]
        unit = next((u for u in model["storage"] if u["id"] == target), None)
        bus = str(unit["bus"]) if unit is not None else target
        if interval > 0:
            key = _var(interval, bus)
            coefficients[key] = coefficients.get(key, 0.0) + 1.0
            previous = _var(interval - 1, bus)
            coefficients[previous] = coefficients.get(previous, 0.0) - 1.0

    # A ``partial`` plan leaves omitted buses unbounded, so any form touching one cannot be
    # decided. Reported as undetermined rather than silently treated as satisfied.
    unbounded = bool(plan.get("partial", False)) and any(
        coefficients.get(_var(interval, bus)) for bus in order
    )
    return {
        "interval": interval,
        "coefficients": coefficients,
        "offset": offset,
        "unbounded": unbounded,
    }



def _forward(
    form: _Form, domains: dict[str, Domain]
) -> tuple[float, float, bool]:
    """Range of ``offset + sum(c_k * x_k)`` under the current domains."""
    lower = form["offset"]
    upper = form["offset"]
    unbounded = False
    for key, coefficient in sorted(form["coefficients"].items()):
        domain = domains.get(key)
        if domain is None or not math.isfinite(domain["lower"]) or not math.isfinite(domain["upper"]):
            unbounded = True
            continue
        if coefficient >= 0:
            lower += coefficient * domain["lower"]
            upper += coefficient * domain["upper"]
        else:
            lower += coefficient * domain["upper"]
            upper += coefficient * domain["lower"]
    return lower, upper, unbounded


def _project(
    form: _Form,
    band_lower: float,
    band_upper: float,
    domains: dict[str, Domain],
) -> list[str]:
    """Narrow every variable in the form. Returns the ids that actually moved.

    The inverse of ``_forward``: for ``sum c_k x_k in [L, U]``, the contribution of all terms
    except ``x_k`` is known from the current domains, so the band pins ``x_k`` to a range.
    """
    moved: list[str] = []
    # Coefficient -> domain, so the inner loop reads a scalar rather than a dict lookup.
    finite: dict[str, tuple[float, Domain]] = {
        key: (form["coefficients"][key], domains[key])
        for key in sorted(form["coefficients"])
        if key in domains
        and math.isfinite(domains[key]["lower"])
        and math.isfinite(domains[key]["upper"])
    }
    for key, coefficient in sorted(form["coefficients"].items()):
        if coefficient == 0.0 or key not in finite:
            continue
        rest_lower = form["offset"]
        rest_upper = form["offset"]
        for other_key, (other_coefficient, domain) in finite.items():
            if other_key == key:
                continue
            if other_coefficient >= 0:
                rest_lower += other_coefficient * domain["lower"]
                rest_upper += other_coefficient * domain["upper"]
            else:
                rest_lower += other_coefficient * domain["upper"]
                rest_upper += other_coefficient * domain["lower"]
        current = finite[key][1]
        if coefficient > 0:
            new_lower = max(current["lower"], (band_lower - rest_upper) / coefficient)
            new_upper = min(current["upper"], (band_upper - rest_lower) / coefficient)
        else:
            new_lower = max(current["lower"], (band_upper - rest_lower) / coefficient)
            new_upper = min(current["upper"], (band_lower - rest_upper) / coefficient)
        if new_upper < new_lower - EPS:
            # A genuinely empty domain is the proof of infeasibility this engine exists to
            # produce. Both ends are kept rather than collapsed, so the caller can report by
            # exactly how much the constraint is unsatisfiable instead of merely detecting
            # that it is.
            pass
        if new_lower > current["lower"] or new_upper < current["upper"]:
            domains[key] = {"lower": new_lower, "upper": new_upper}
            moved.append(key)
    return moved


def _empty(domains: dict[str, Domain]) -> list[str]:
    return sorted(key for key, domain in domains.items() if domain["upper"] < domain["lower"] - EPS)


def _build_domains(plan: DispatchPlan, order: list[str]) -> dict[str, Domain]:
    """Initial variable domains, one per (interval, bus).

    A bus the plan omits is pinned to zero in the default reading — a dispatch plan states
    what will happen, and a bus it says nothing about sits still — and left unbounded when
    the plan declares itself ``partial``.
    """
    partial = bool(plan.get("partial", False))
    domains: dict[str, Domain] = {}
    for index in range(len(plan["intervals"])):
        for bus in order:
            window = plan["intervals"][index]["buses"].get(bus)
            if window is not None:
                domains[_var(index, bus)] = {"lower": window["lowerMw"], "upper": window["upperMw"]}
            elif partial:
                domains[_var(index, bus)] = {"lower": -INF, "upper": INF}
            else:
                domains[_var(index, bus)] = {"lower": 0.0, "upper": 0.0}
    return domains


def attained_window(
    model: NetworkModel,
    plan: DispatchPlan,
    constraint: Constraint,
) -> tuple[float, float] | None:
    """The range this constraint's quantity takes under the *plan alone*, ignoring every
    other constraint.

    This is what relaxation needs, and it is deliberately different from the range reported
    by ``propagate``. After propagation the domains have been narrowed by the other
    constraints, so a quantity may look comfortable purely because something else is holding
    it down. Asking "how much must I relax this limit?" against the narrowed range would
    understate the answer. Against the plan's own windows it is the honest one: this is how
    far the operator's own proposal runs.
    """
    order = [bus["id"] for bus in model["buses"]]
    hours = [interval["hours"] for interval in plan["intervals"]]
    topo = topology.build_topology(
        order,
        _branch_specs(model),
        model["slackBus"],
    )
    factors = topology.power_transfer_factors(topo)
    branch_position = {branch["id"]: index for index, branch in enumerate(topo["branches"])}
    domains = _build_domains(plan, order)

    last_interval = len(plan["intervals"]) - 1
    start = min(constraint["fromInterval"], last_interval)
    end = constraint["toInterval"]
    window = range(start, last_interval + 1 if end is None else min(end, last_interval) + 1)

    lower = math.inf
    upper = -math.inf
    for index in window:
        form = _form_for(constraint, index, plan, model, factors, order, branch_position, hours)
        form_lower, form_upper, unbounded = _forward(form, domains)
        if unbounded:
            return None
        lower = min(lower, form_lower)
        upper = max(upper, form_upper)
    if lower is math.inf:
        return None
    return (lower, upper)


def propagate(
    model: NetworkModel,
    plan: DispatchPlan,
    constraints: list[Constraint],
    budget: int,
) -> PropagationResult:
    """Propagate every enabled constraint to a fixed point, or report the proof of failure."""
    order = [bus["id"] for bus in model["buses"]]
    hours = [interval["hours"] for interval in plan["intervals"]]
    topo = topology.build_topology(
        order,
        _branch_specs(model),
        model["slackBus"],
    )
    factors = topology.power_transfer_factors(topo)
    branch_position = {branch["id"]: index for index, branch in enumerate(topo["branches"])}

    active = [constraint for constraint in constraints if constraint["enabled"]]

    # Precompute every (constraint, interval) form once. They are immutable, so building
    # them up front keeps the propagation loop free of interpretation work.
    last_interval = len(plan["intervals"]) - 1
    forms: list[list[_Form]] = []
    for constraint in active:
        start = min(constraint["fromInterval"], last_interval)
        end = constraint["toInterval"]
        window = range(start, last_interval + 1 if end is None else min(end, last_interval) + 1)
        forms.append(
            [
                _form_for(constraint, index, plan, model, factors, order, branch_position, hours)
                for index in window
            ]
        )

    domains = _build_domains(plan, order)

    fixpoint = False
    for sweep in range(1, budget + 1):
        iterations = sweep
        changed = False
        # One sweep: project every constraint, in declaration order, over the domains.
        for index, constraint in enumerate(active):
            band_lower = -INF if constraint["lower"] is None else float(constraint["lower"])
            band_upper = INF if constraint["upper"] is None else float(constraint["upper"])
            for form in forms[index]:
                if _project(form, band_lower, band_upper, domains):
                    changed = True
        if not changed:
            fixpoint = True
            break

    empties = _empty(domains)

    quantities: list[QuantitySeries] = []
    violating: set[str] = set()
    for index, constraint in enumerate(active):
        band_lower = -INF if constraint["lower"] is None else float(constraint["lower"])
        band_upper = INF if constraint["upper"] is None else float(constraint["upper"])
        series: list[Quantity] = []
        violated_here: list[int] = []
        worst = 0.0
        undetermined_here = False

        # Read the interval from the form, not from a loop counter: a constraint scoped to a
        # window (a state-of-charge floor applying from hour 2) has fewer forms than the plan
        # has intervals, and a positional counter would misreport every one of them as
        # starting at zero.
        for form in forms[index]:
            interval = form["interval"]
            lower, upper, unbounded = _forward(form, domains)
            if unbounded:
                undetermined_here = True
                series.append(
                    {
                        "interval": interval,
                        "hours": hours[interval],
                        "lower": lower if math.isfinite(lower) else 0.0,
                        "upper": upper if math.isfinite(upper) else 0.0,
                        "excessMw": 0.0,
                    }
                )
                continue
            excess = max(0.0, lower - band_upper - EPS, band_lower - upper - EPS)
            if excess > 0.0:
                violated_here.append(interval)
                worst = max(worst, excess)
            series.append(
                {
                    "interval": interval,
                    "hours": hours[interval],
                    "lower": round(lower, 6),
                    "upper": round(upper, 6),
                    "excessMw": round(excess, 6),
                }
            )

        if violated_here:
            violating.add(constraint["id"])
        verdict = (
            "undetermined"
            if undetermined_here
            else ("violated" if violated_here else "satisfied")
        )
        quantities.append(
            {
                "constraintId": constraint["id"],
                "kind": constraint["kind"],
                "target": constraint["target"],
                "label": constraint["label"],
                "lower": round(band_lower, 6) if math.isfinite(band_lower) else 0.0,
                "upper": round(band_upper, 6) if math.isfinite(band_upper) else 0.0,
                "verdict": verdict,
                "excessMw": round(worst, 6),
                "series": series,
                "violations": violated_here,
            }
        )

    # The verdict is derived from the *evaluated* quantities, not just from whether any
    # domain went empty. A constraint can be violated without emptying a domain — a state
    # of charge floor in the first interval has no variables to project onto, so it is
    # violated yet leaves the box intact. Reporting "feasible" there would be a proof of
    # something that is false.
    undetermined = any(quantity["verdict"] == "undetermined" for quantity in quantities)
    if violating or empties:
        verdict = "infeasible"
    elif undetermined:
        verdict = "undetermined"
    else:
        verdict = "feasible"

    variables: list[VariableReport] = []
    for key in sorted(domains):
        interval_text, _, bus = key.partition(":")
        domain = domains[key]
        variables.append(
            {
                "id": key,
                "interval": int(interval_text[1:]),
                "bus": bus,
                "lower": round(domain["lower"], 6) if math.isfinite(domain["lower"]) else 0.0,
                "upper": round(domain["upper"], 6) if math.isfinite(domain["upper"]) else 0.0,
                "unbounded": not math.isfinite(domain["lower"]) or not math.isfinite(domain["upper"]),
                "narrowedBy": [],
            }
        )

    return {
        "intervals": len(plan["intervals"]),
        "fixpoint": fixpoint,
        "iterations": iterations,
        "verdict": verdict,
        "feasible": verdict == "feasible",
        "quantities": quantities,
        "violations": sorted(violating),
        "variables": variables,
    }

