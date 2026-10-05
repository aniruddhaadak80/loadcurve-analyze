"""Shared fixtures: a small radial distribution feeder and the plans screened against it.

The network is a 5-bus 11 kV radial feeder behind a 40 MVA transformer — the shape of a real
distribution study rather than a toy graph:

    SLACK(69) -- TX1 -- B1(11) -- L12 -- B2 -- L23 -- B3(der)
                              |
                             L14 -- B4(der) -- L45 -- B5(bess)

`loadcurve`'s whole point is that a plan can be *infeasible for a reason*, so the fixtures
include deliberately broken plans alongside correct ones. Each carries the reason in its
docstring, because a test that does not say why it is infeasible teaches nobody anything.
"""

from __future__ import annotations

from typing import Any

#: A radial 11 kV feeder with two DER sites and a battery at the end of the lateral.
FEEDER: dict[str, Any] = {
    "name": "radial-11kv-feeder",
    "baseMva": 40.0,
    "slackBus": "SLACK",
    "buses": [
        {"id": "SLACK", "baseKv": 69.0},
        {"id": "B1", "baseKv": 11.0},
        {"id": "B2", "baseKv": 11.0},
        {"id": "B3", "baseKv": 11.0},
        {"id": "B4", "baseKv": 11.0},
        {"id": "B5", "baseKv": 11.0},
    ],
    "branches": [
        {"id": "TX1", "fromBus": "SLACK", "toBus": "B1", "reactancePu": 0.04, "ratingMw": 25.0},
        {"id": "L12", "fromBus": "B1", "toBus": "B2", "reactancePu": 0.05, "ratingMw": 12.0},
        {"id": "L23", "fromBus": "B2", "toBus": "B3", "reactancePu": 0.06, "ratingMw": 10.0},
        {"id": "L14", "fromBus": "B1", "toBus": "B4", "reactancePu": 0.07, "ratingMw": 9.0},
        {"id": "L45", "fromBus": "B4", "toBus": "B5", "reactancePu": 0.08, "ratingMw": 6.0},
    ],
    "storage": [
        {
            "id": "BESS1",
            "bus": "B5",
            "chargeMwMax": 4.0,
            "dischargeMwMax": 4.0,
            "energyMwh": 8.0,
            "socFracMin": 0.15,
            "socFracMax": 0.95,
            "socFracInitial": 0.5,
            "efficiency": 0.95,
        }
    ],
}


#: A meshed transmission-side model. The radial feeder above has the property that *every*
#: branch outage islands part of it, which is realistic for a distribution lateral but makes
#: it useless for testing the N-1 screen: there is no outage that leaves the network intact.
#: This loop closes the ring so individual outages stay connected and the security screen has
#: something real to decide.
MESHED: dict[str, Any] = {
    "name": "meshed-132kv-loop",
    "baseMva": 100.0,
    "slackBus": "S1",
    "buses": [
        {"id": "S1", "baseKv": 132.0},
        {"id": "S2", "baseKv": 132.0},
        {"id": "S3", "baseKv": 132.0},
        {"id": "S4", "baseKv": 132.0},
    ],
    "branches": [
        {"id": "T12", "fromBus": "S1", "toBus": "S2", "reactancePu": 0.10, "ratingMw": 60.0},
        {"id": "T23", "fromBus": "S2", "toBus": "S3", "reactancePu": 0.12, "ratingMw": 50.0},
        {"id": "T34", "fromBus": "S3", "toBus": "S4", "reactancePu": 0.10, "ratingMw": 50.0},
        {"id": "T41", "fromBus": "S4", "toBus": "S1", "reactancePu": 0.14, "ratingMw": 60.0},
    ],
    "storage": [],
}


def plan(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """A dispatch plan from per-interval bus windows.

    Each entry is ``{"hours": float, "buses": {bus: (lowerMw, upperMw)}}``. A bus absent from
    an interval is unconstrained in that interval, which is how a real plan expresses "this
    asset does not move right now".
    """
    return {
        "intervals": [
            {
                "hours": entry["hours"],
                "buses": {
                    bus: {"lowerMw": bounds[0], "upperMw": bounds[1]}
                    for bus, bounds in sorted(entry["buses"].items())
                },
            }
            for entry in entries
        ]
    }


def hour(buses: dict[str, tuple[float, float]], hours: float = 1.0) -> dict[str, Any]:
    """A single-interval plan."""
    return plan([{"hours": hours, "buses": buses}])


def line_thermal(constraint_id: str, branch: str, rating: float | None = None) -> dict[str, Any]:
    """A two-sided thermal limit. Omit ``rating`` to inherit the branch's own rating."""
    constraint: dict[str, Any] = {"id": constraint_id, "kind": "line_thermal", "target": branch}
    if rating is not None:
        constraint["lower"] = -rating
        constraint["upper"] = rating
    return constraint


def poi_export(
    constraint_id: str, members: list[str], upper: float, lower: float | None = None
) -> dict[str, Any]:
    """A net-injection cap over a set of buses — a DER export limit at the point of tie."""
    constraint: dict[str, Any] = {
        "id": constraint_id,
        "kind": "poi_export",
        "target": constraint_id,
        "members": members,
        "upper": upper,
    }
    if lower is not None:
        constraint["lower"] = lower
    return constraint


def storage_soc(
    constraint_id: str,
    unit: str,
    upper: float | None = None,
    lower: float | None = None,
    from_interval: int | None = None,
) -> dict[str, Any]:
    """A state-of-charge envelope for one storage unit.

    ``from_interval`` exists because a grid code's SOC condition usually binds only from a
    given hour on — "at least 70% charged by the end of hour two". Without the window the
    condition would be reported as violated in interval 0, where it simply does not apply.
    """
    constraint: dict[str, Any] = {"id": constraint_id, "kind": "storage_soc", "target": unit}
    if upper is not None:
        constraint["upper"] = upper
    if lower is not None:
        constraint["lower"] = lower
    if from_interval is not None:
        constraint["fromInterval"] = from_interval
    return constraint


def branch_group(constraint_id: str, members: list[str], lower: float, upper: float) -> dict[str, Any]:
    """A net limit across a group of branches — a transformer bank or an intertie."""
    return {
        "id": constraint_id,
        "kind": "branch_group",
        "target": constraint_id,
        "members": members,
        "lower": lower,
        "upper": upper,
    }


def ramp(constraint_id: str, target: str, lower: float, upper: float) -> dict[str, Any]:
    """A per-interval ramp limit on a bus or storage unit."""
    return {
        "id": constraint_id,
        "kind": "ramp",
        "target": target,
        "lower": lower,
        "upper": upper,
    }


def outages(*pairs: tuple[str, str] | str) -> list[dict[str, str]]:
    """Declared N-1 outages.

    Accepts either ``(outageId, branchId)`` pairs or bare branch ids, in which case the
    outage takes the branch's own name. The bare form exists because "every branch of this
    model, one at a time" is a common test case and spelling out the ids for it is noise.
    """
    declared: list[dict[str, str]] = []
    for pair in pairs:
        if isinstance(pair, str):
            declared.append({"id": pair, "branchId": pair, "label": pair})
        else:
            outage_id, branch_id = pair
            declared.append({"id": outage_id, "branchId": branch_id, "label": outage_id})
    return declared
