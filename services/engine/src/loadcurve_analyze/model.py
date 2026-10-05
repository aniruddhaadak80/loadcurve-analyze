"""The typed domain model, and the validation that stands between untrusted JSON and the
proof engine.

Everything is a ``TypedDict`` rather than a dataclass or a pydantic model, for two reasons
that are load-bearing rather than stylistic:

* The engine is a subprocess called on every tool invocation. Its runtime dependency count
  is zero, and it stays that way.
* The same shapes cross the wire to TypeScript, where ``packages/engine-model`` mirrors
  them as zod schemas. A ``TypedDict`` and a zod schema are structurally the same contract,
  so the mirror is checkable rather than aspirational.

Validation is explicit and raises ``EngineError`` with a stable code. An interconnection
study is a document that gets filed, so a malformed model must fail loudly rather than
propagate a default into a bound.
"""

from __future__ import annotations

import math
from typing import Final, TypedDict

from .protocol import EngineError

#: The five constraint kinds this engine can decide. Every one is a linear form over bus
#: injections, which is what keeps bound propagation exact rather than approximate.
CONSTRAINT_KINDS: Final[frozenset[str]] = frozenset(
    {"line_thermal", "branch_group", "poi_export", "storage_soc", "ramp"}
)


class Bus(TypedDict):
    id: str
    baseKv: float


class Branch(TypedDict):
    id: str
    fromBus: str
    toBus: str
    reactancePu: float
    ratingMw: float


class Storage(TypedDict):
    id: str
    bus: str
    chargeMwMax: float
    dischargeMwMax: float
    energyMwh: float
    socFracMin: float
    socFracMax: float
    socFracInitial: float
    efficiency: float


class NetworkModel(TypedDict):
    name: str
    baseMva: float
    slackBus: str
    buses: list[Bus]
    branches: list[Branch]
    storage: list[Storage]


class Injection(TypedDict):
    lowerMw: float
    upperMw: float


class IntervalInjections(TypedDict):
    hours: float
    buses: dict[str, Injection]


class DispatchPlan(TypedDict):
    intervals: list[IntervalInjections]
    #: When true, a bus absent from an interval is treated as *unconstrained* (its domain is
    #: unbounded) and any constraint touching it is reported ``undetermined``. When false —
    #: the default — an absent bus is taken as not dispatching in that interval, which is the
    #: usual reading of a dispatch plan: it states what will happen, and a bus it says
    #: nothing about sits still. The distinction is exposed rather than assumed, because
    #: getting it wrong turns a proof into a guess.
    partial: bool


class Constraint(TypedDict):
    id: str
    kind: str
    target: str
    label: str
    members: list[str]
    lower: float | None
    upper: float | None
    enabled: bool
    #: Interval window this constraint applies to. Defaults to the whole horizon. Grid codes
    #: routinely bind a condition only from a given hour onwards — "state of charge must be
    #: at least 70% by the end of the second hour" — and expressing that as a window keeps
    #: such a rule from being reported as violated in interval 0, where it does not apply.
    fromInterval: int
    toInterval: int | None


def _require_mapping(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EngineError("BAD_SHAPE", f"{what} must be an object")
    return value


def _require_number(container: dict[str, object], key: str, what: str) -> float:
    raw = container.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise EngineError("MISSING_FIELD", f"{what}.{key} must be a number")
    number = float(raw)
    if not math.isfinite(number):
        raise EngineError("NON_FINITE", f"{what}.{key} must be finite")
    return number


def _require_str(container: dict[str, object], key: str, what: str) -> str:
    raw = container.get(key)
    if not isinstance(raw, str) or not raw:
        raise EngineError("MISSING_FIELD", f"{what}.{key} must be a non-empty string")
    return raw


def _require_list(container: dict[str, object], key: str, what: str) -> list[object]:
    raw = container.get(key)
    if not isinstance(raw, list):
        raise EngineError("BAD_SHAPE", f"{what}.{key} must be an array")
    return raw


def _unique(values: list[str], what: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise EngineError("DUPLICATE_ID", f"{what} contains duplicate id {value!r}")
        seen.add(value)


def parse_model(raw: object) -> NetworkModel:
    """Validate a network model and return it in canonical form."""
    model = _require_mapping(raw, "model")
    name = _require_str(model, "name", "model")
    base_mva = _require_number(model, "baseMva", "model")
    slack_bus = _require_str(model, "slackBus", "model")
    if base_mva <= 0:
        raise EngineError("BAD_VALUE", "model.baseMva must be positive")

    buses: list[Bus] = []
    for index, entry in enumerate(_require_list(model, "buses", "model")):
        item = _require_mapping(entry, f"model.buses[{index}]")
        bus_id = _require_str(item, "id", f"model.buses[{index}]")
        base_kv = _require_number(item, "baseKv", f"model.buses[{index}]")
        if base_kv <= 0:
            raise EngineError("BAD_VALUE", f"model.buses[{index}].baseKv must be positive")
        buses.append({"id": bus_id, "baseKv": base_kv})
    _unique([bus["id"] for bus in buses], "model.buses")
    if len(buses) < 2:
        raise EngineError("DEGENERATE_NETWORK", "model.buses needs at least two buses")

    bus_ids = {bus["id"] for bus in buses}
    branches: list[Branch] = []
    for index, entry in enumerate(_require_list(model, "branches", "model")):
        item = _require_mapping(entry, f"model.branches[{index}]")
        branch_id = _require_str(item, "id", f"model.branches[{index}]")
        from_bus = _require_str(item, "fromBus", f"model.branches[{index}]")
        to_bus = _require_str(item, "toBus", f"model.branches[{index}]")
        reactance = _require_number(item, "reactancePu", f"model.branches[{index}]")
        rating = _require_number(item, "ratingMw", f"model.branches[{index}]")
        if reactance == 0.0:
            raise EngineError("BAD_VALUE", f"model.branches[{index}].reactancePu must be non-zero")
        if rating <= 0:
            raise EngineError("BAD_VALUE", f"model.branches[{index}].ratingMw must be positive")
        if from_bus not in bus_ids:
            raise EngineError("UNKNOWN_BUS", f"branch {branch_id!r} references unknown bus {from_bus!r}")
        if to_bus not in bus_ids:
            raise EngineError("UNKNOWN_BUS", f"branch {branch_id!r} references unknown bus {to_bus!r}")
        branches.append(
            {
                "id": branch_id,
                "fromBus": from_bus,
                "toBus": to_bus,
                "reactancePu": reactance,
                "ratingMw": rating,
            }
        )
    _unique([branch["id"] for branch in branches], "model.branches")
    if not branches:
        raise EngineError("DEGENERATE_NETWORK", "model.branches must not be empty")

    storage: list[Storage] = []
    for index, entry in enumerate(_require_list(model, "storage", "model")):
        what = f"model.storage[{index}]"
        item = _require_mapping(entry, what)
        storage_id = _require_str(item, "id", what)
        bus = _require_str(item, "bus", what)
        if bus not in bus_ids:
            raise EngineError("UNKNOWN_BUS", f"{what}.bus references unknown bus {bus!r}")
        energy = _require_number(item, "energyMwh", what)
        soc_min = _require_number(item, "socFracMin", what)
        soc_max = _require_number(item, "socFracMax", what)
        initial = _require_number(item, "socFracInitial", what)
        efficiency = _require_number(item, "efficiency", what)
        if energy <= 0:
            raise EngineError("BAD_VALUE", f"{what}.energyMwh must be positive")
        if not 0.0 <= soc_min <= 1.0 or not 0.0 <= soc_max <= 1.0:
            raise EngineError("BAD_VALUE", f"{what} soc bounds must lie in [0, 1]")
        if soc_min > soc_max:
            raise EngineError("BAD_VALUE", f"{what}.socFracMin exceeds socFracMax")
        if not soc_min <= initial <= soc_max:
            raise EngineError("BAD_VALUE", f"{what}.socFracInitial lies outside the soc envelope")
        if not 0.0 < efficiency <= 1.0:
            raise EngineError("BAD_VALUE", f"{what}.efficiency must lie in (0, 1]")
        storage.append(
            {
                "id": storage_id,
                "bus": bus,
                "chargeMwMax": _require_number(item, "chargeMwMax", what),
                "dischargeMwMax": _require_number(item, "dischargeMwMax", what),
                "energyMwh": energy,
                "socFracMin": soc_min,
                "socFracMax": soc_max,
                "socFracInitial": initial,
                "efficiency": efficiency,
            }
        )
    _unique([unit["id"] for unit in storage], "model.storage")

    return {
        "name": name,
        "baseMva": base_mva,
        "slackBus": slack_bus,
        "buses": buses,
        "branches": branches,
        "storage": storage,
    }


def parse_plan(raw: object, model: NetworkModel) -> DispatchPlan:
    """Validate a dispatch plan against its model and return it in canonical form."""
    plan = _require_mapping(raw, "plan")
    intervals: list[IntervalInjections] = []
    for index, entry in enumerate(_require_list(plan, "intervals", "plan")):
        what = f"plan.intervals[{index}]"
        item = _require_mapping(entry, what)
        hours = _require_number(item, "hours", what)
        if hours <= 0:
            raise EngineError("BAD_VALUE", f"{what}.hours must be positive")
        injections: dict[str, Injection] = {}
        for bus_id, bounds in _require_mapping(item.get("buses", {}), f"{what}.buses").items():
            if bus_id not in {bus["id"] for bus in model["buses"]}:
                raise EngineError("UNKNOWN_BUS", f"{what}.buses references unknown bus {bus_id!r}")
            window = _require_mapping(bounds, f"{what}.buses.{bus_id}")
            lower = _require_number(window, "lowerMw", f"{what}.buses.{bus_id}")
            upper = _require_number(window, "upperMw", f"{what}.buses.{bus_id}")
            if lower > upper:
                raise EngineError(
                    "INVERTED_INTERVAL",
                    f"{what}.buses.{bus_id} is inverted: {lower} > {upper}",
                )
            injections[bus_id] = {"lowerMw": lower, "upperMw": upper}
        intervals.append({"hours": hours, "buses": injections})
    if not intervals:
        raise EngineError("BAD_SHAPE", "plan.intervals must not be empty")
    partial_raw = plan.get("partial", False)
    if not isinstance(partial_raw, bool):
        raise EngineError("BAD_SHAPE", "plan.partial must be a boolean")
    return {"intervals": intervals, "partial": partial_raw}


def parse_constraints(raw: object, model: NetworkModel) -> list[Constraint]:
    """Validate the hard-constraint set, filling in each kind's default band."""
    if not isinstance(raw, list):
        raise EngineError("BAD_SHAPE", "constraints must be an array")
    entries = raw
    branch_ids = {branch["id"] for branch in model["branches"]}
    storage_ids = {unit["id"] for unit in model["storage"]}
    bus_ids = {bus["id"] for bus in model["buses"]}

    constraints: list[Constraint] = []
    for index, entry in enumerate(entries):
        what = f"constraints[{index}]"
        item = _require_mapping(entry, what)
        constraint_id = _require_str(item, "id", what)
        kind = _require_str(item, "kind", what)
        if kind not in CONSTRAINT_KINDS:
            known = ", ".join(sorted(CONSTRAINT_KINDS))
            raise EngineError("UNKNOWN_CONSTRAINT_KIND", f"{what}.kind {kind!r} is not one of: {known}")
        target = _require_str(item, "target", what)
        members_raw = item.get("members", [])
        if not isinstance(members_raw, list) or not all(isinstance(m, str) for m in members_raw):
            raise EngineError("BAD_SHAPE", f"{what}.members must be an array of strings")
        members = [str(member) for member in members_raw]

        if kind == "line_thermal":
            if target not in branch_ids:
                raise EngineError("UNKNOWN_BRANCH", f"{what}.target {target!r} is not an in-service branch")
            if members:
                raise EngineError("BAD_SHAPE", f"{what} of kind line_thermal must not declare members")
        elif kind == "storage_soc":
            if target not in storage_ids:
                raise EngineError("UNKNOWN_STORAGE", f"{what}.target {target!r} is not a storage unit")
        elif kind == "ramp":
            known_targets = storage_ids | bus_ids
            if target not in known_targets:
                raise EngineError(
                    "BAD_REFERENCE", f"{what}.target {target!r} is neither a bus nor a storage unit"
                )
        elif kind == "branch_group":
            if not members:
                raise EngineError("BAD_SHAPE", f"{what} of kind branch_group needs at least one member")
            unknown = [member for member in members if member not in branch_ids]
            if unknown:
                raise EngineError("UNKNOWN_BRANCH", f"{what}.members references unknown branches: {unknown}")
        elif kind == "poi_export":
            if not members:
                raise EngineError("BAD_SHAPE", f"{what} of kind poi_export needs at least one member bus")
            unknown = [member for member in members if member not in bus_ids]
            if unknown:
                raise EngineError("UNKNOWN_BUS", f"{what}.members references unknown buses: {unknown}")

        lower_raw = item.get("lower")
        upper_raw = item.get("upper")
        lower = None if lower_raw is None else _require_number(item, "lower", what)
        upper = None if upper_raw is None else _require_number(item, "upper", what)

        if kind == "line_thermal":
            rating = next(b["ratingMw"] for b in model["branches"] if b["id"] == target)
            if lower is None:
                lower = -rating
            if upper is None:
                upper = rating
        if lower is None and upper is None:
            raise EngineError(
                "BAD_SHAPE",
                f"{what} must declare at least one of lower or upper; an unbounded band is not decidable",
            )
        if lower is not None and upper is not None and lower > upper:
            raise EngineError("INVERTED_INTERVAL", f"{what} declares lower {lower} above upper {upper}")

        enabled_raw = item.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise EngineError("BAD_SHAPE", f"{what}.enabled must be a boolean")

        from_raw = item.get("fromInterval", 0)
        to_raw = item.get("toInterval")
        if isinstance(from_raw, bool) or not isinstance(from_raw, int) or from_raw < 0:
            raise EngineError("BAD_VALUE", f"{what}.fromInterval must be a non-negative integer")
        if to_raw is not None and (isinstance(to_raw, bool) or not isinstance(to_raw, int) or to_raw < 0):
            raise EngineError("BAD_VALUE", f"{what}.toInterval must be a non-negative integer")
        if to_raw is not None and to_raw < from_raw:
            raise EngineError("BAD_VALUE", f"{what}.toInterval precedes fromInterval")

        constraints.append(
            {
                "id": constraint_id,
                "kind": kind,
                "target": target,
                "label": str(item.get("label", target)),
                "members": members,
                "lower": lower,
                "upper": upper,
                "enabled": enabled_raw,
                "fromInterval": from_raw,
                "toInterval": to_raw,
            }
        )
    _unique([constraint["id"] for constraint in constraints], "constraints")
    return constraints


def parse_budget(raw: object, default: int = 64) -> int:
    """The propagation iteration budget. Bounded so a pathological input cannot hang."""
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise EngineError("BAD_SHAPE", "budget must be an integer")
    if raw < 1:
        raise EngineError("BAD_VALUE", "budget must be at least 1")
    if raw > 4096:
        raise EngineError("BAD_VALUE", "budget must not exceed 4096")
    return raw
