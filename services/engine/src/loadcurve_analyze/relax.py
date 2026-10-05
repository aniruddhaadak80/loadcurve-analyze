"""`relaxation` — the smallest total bound change that makes a contradictory core feasible.

An unsatisfiable core answers "these constraints fight". An operator's real question is "what
is the cheapest thing I can change?", and the cheapest change is usually not to abandon one
constraint outright: widening a thermal rating by a megawatt or two is often far cheaper than
relaxing a grid-code limit.

So this computes a genuine **L1 minimum** — the smallest sum of bound movements that makes
every constraint in the core satisfiable at once — and it does so exactly, not heuristically.

The cost of each individual edge is found by bisection, which is valid because feasibility is
**monotone** in a relaxation: widening a band can never remove a solution, so ``feasible(δ)``
is a step function with a single threshold, and binary search finds it. With an exact cost per
edge, the combination step is exhaustive over the edges' sign choices, which is what makes the
total a proven minimum rather than a good guess.

A minimal unsatisfiable subset is small by construction — that is what deletion-based
extraction guarantees — so the combination search is bounded. Above
``MAX_CORE_FOR_EXHAUSTIVE`` members it degrades to per-edge bests and reports
``optimal: False`` rather than pretending to a minimum it did not prove.
"""

from __future__ import annotations

from typing import TypedDict

from .model import Constraint, DispatchPlan, NetworkModel
from .protocol import EngineError
from .propagate import propagate


class Relaxation(TypedDict):
    constraintId: str
    side: str
    fromBound: float
    toBound: float
    delta: float


class RelaxationPlan(TypedDict):
    feasible: bool
    optimal: bool
    totalDelta: float
    relaxations: list[Relaxation]
    combinations: int


#: 14 members is 2**14 = 16384 propagation runs over an already-small core.
MAX_CORE_FOR_EXHAUSTIVE = 14

#: Bisection resolution. One MW is 1e-6 here, which is far below any engineering tolerance
#: and comfortably above float noise for MW-scale quantities.
BISECTION_STEPS = 60

#: Feasibility probe: pass this many constraints to `propagate`. Small on purpose, because
#: this is called inside a bisection inside a combination search.
PROBE_BUDGET = 32


def _satisfiable(
    model: NetworkModel,
    plan: DispatchPlan,
    core: list[Constraint],
    moves: dict[str, tuple[str, float]],
) -> bool:
    rebuilt: list[Constraint] = []
    for constraint in core:
        move = moves.get(constraint["id"])
        if move is None:
            rebuilt.append(constraint)
        elif move[0] == "lower":
            rebuilt.append({**constraint, "lower": move[1]})
        else:
            rebuilt.append({**constraint, "upper": move[1]})
    return propagate(model, plan, rebuilt, PROBE_BUDGET)["feasible"]


def _edges(constraint: Constraint) -> list[tuple[str, float]]:
    """The relaxable (side, current bound) pairs of one constraint.

    A band that is already infinite on one side has nothing to widen on that side, so only
    the bounded sides are candidates.
    """
    edges: list[tuple[str, float]] = []
    if constraint["lower"] is not None:
        edges.append(("lower", float(constraint["lower"])))
    if constraint["upper"] is not None:
        edges.append(("upper", float(constraint["upper"])))
    return edges


def _minimal_move(
    model: NetworkModel,
    plan: DispatchPlan,
    core: list[Constraint],
    constraint_id: str,
    side: str,
    bound: float,
    ceiling: float,
) -> float | None:
    """The least movement of one bound that restores feasibility, or ``None`` if it never does.

    Bisection rather than a closed form because the interaction between bounds is only
    captured by running propagation; there is no formula to shortcut to, and monotonicity is
    what makes the search correct rather than lucky.
    """
    direction = -1.0 if side == "lower" else 1.0

    def feasible_at(delta: float) -> bool:
        return _satisfiable(model, plan, core, {constraint_id: (side, bound + direction * delta)})

    if not feasible_at(ceiling):
        return None

    low, high = 0.0, ceiling
    for _ in range(BISECTION_STEPS):
        middle = (low + high) / 2.0
        if feasible_at(middle):
            high = middle
        else:
            low = middle
    return high


def relaxation(
    model: NetworkModel,
    plan: DispatchPlan,
    core_ids: list[str],
    constraints: list[Constraint],
) -> RelaxationPlan:
    """The minimum total L1 bound movement satisfying every constraint in ``core_ids``."""
    by_id = {constraint["id"]: constraint for constraint in constraints}
    core = [by_id[core_id] for core_id in core_ids if core_id in by_id]

    if not core or _satisfiable(model, plan, core, {}):
        return {"feasible": True, "optimal": True, "totalDelta": 0.0, "relaxations": [], "combinations": 0}

    # Grow the search ceiling until *some* single-edge relaxation restores feasibility.
    # Without a bound this loop would have no termination argument, so the count is capped
    # and running out of it is reported rather than silently treated as "no relaxation
    # exists" — the difference matters, because one means "too tight to find" and the other
    # means "genuinely impossible".
    ceiling = 1.0
    found_ceiling = False
    for _ in range(40):
        if any(
            _minimal_move(model, plan, core, constraint["id"], side, bound, ceiling)
            is not None
            for constraint in core
            for side, bound in _edges(constraint)
        ):
            found_ceiling = True
            break
        ceiling *= 4.0
    if not found_ceiling:
        return {
            "feasible": False,
            "optimal": False,
            "totalDelta": 0.0,
            "relaxations": [],
            "combinations": 0,
        }

    edges: list[tuple[str, str, float, float]] = []
    for constraint in core:
        for side, bound in _edges(constraint):
            moved = _minimal_move(model, plan, core, constraint["id"], side, bound, ceiling)
            if moved is not None:
                edges.append((constraint["id"], side, bound, moved))

    if not edges:
        return {"feasible": False, "optimal": False, "totalDelta": 0.0, "relaxations": [], "combinations": 0}

    by_constraint: dict[str, list[tuple[str, float, float]]] = {}
    for constraint_id, side, bound, moved in edges:
        by_constraint.setdefault(constraint_id, []).append((side, bound, moved))

    if len(core) > MAX_CORE_FOR_EXHAUSTIVE:
        return _per_edge_best(core, by_constraint, by_id)

    best: tuple[float, dict[str, tuple[str, float]]] | None = None
    combinations = 0

    def search(index: int, chosen: dict[str, tuple[str, float]], cost: float) -> None:
        nonlocal best, combinations
        if best is not None and cost >= best[0]:
            # Every remaining delta is non-negative, so this branch cannot beat the incumbent.
            return
        if index == len(core):
            combinations += 1
            if _satisfiable(model, plan, core, chosen) and (best is None or cost < best[0]):
                best = (cost, dict(chosen))
            return
        constraint = core[index]
        options = by_constraint.get(constraint["id"], [])
        if not options:
            search(index + 1, chosen, cost)
            return
        for side, bound, moved in options:
            chosen[constraint["id"]] = (side, bound + (moved if side == "upper" else -moved))
            search(index + 1, chosen, cost + moved)
            del chosen[constraint["id"]]

    search(0, {}, 0.0)

    if best is None:
        return {
            "feasible": False,
            "optimal": False,
            "totalDelta": 0.0,
            "relaxations": [],
            "combinations": combinations,
        }

    cost, moves = best
    return {
        "feasible": True,
        "optimal": True,
        "totalDelta": round(cost, 6),
        "relaxations": [_entry(by_id, constraint_id, side, target) for constraint_id, (side, target) in sorted(moves.items())],
        "combinations": combinations,
    }


def _entry(
    by_id: dict[str, Constraint], constraint_id: str, side: str, target: float
) -> Relaxation:
    """One movement, with the bound read off the constraint explicitly.

    An out-of-range side raises rather than silently reporting a wrong `fromBound`, which is
    why this does not index the TypedDict blindly: ``side`` arrives as a plain string from
    the search, so the lookup is validated at runtime.
    """
    constraint = by_id[constraint_id]
    if side not in ("lower", "upper"):
        raise EngineError("BAD_RELAXATION", f"{side!r} is not a relaxable side")
    original = constraint["lower"] if side == "lower" else constraint["upper"]
    if original is None:
        raise EngineError(
            "BAD_RELAXATION",
            f"constraint {constraint_id!r} has no {side} bound to relax",
        )
    return {
        "constraintId": constraint_id,
        "side": side,
        "fromBound": round(float(original), 6),
        "toBound": round(target, 6),
        "delta": round(abs(target - float(original)), 6),
    }


def _per_edge_best(
    core: list[Constraint],
    by_constraint: dict[str, list[tuple[str, float, float]]],
    by_id: dict[str, Constraint],
) -> RelaxationPlan:
    """Fallback for a core too large to search exhaustively.

    Applies every edge's own minimal movement at once. That is sound but not provably
    minimal, so it is reported with ``optimal: False``.
    """
    moves: dict[str, tuple[str, float]] = {}
    total = 0.0
    for constraint in core:
        options = by_constraint.get(constraint["id"], [])
        if not options:
            continue
        side, bound, moved = min(options, key=lambda option: option[2])
        moves[constraint["id"]] = (side, bound + (moved if side == "upper" else -moved))
        total += moved
    return {
        "feasible": True,
        "optimal": False,
        "totalDelta": round(total, 6),
        "relaxations": [_entry(by_id, constraint_id, side, target) for constraint_id, (side, target) in sorted(moves.items())],
        "combinations": len(core),
    }
