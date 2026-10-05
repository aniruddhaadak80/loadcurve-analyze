"""Network topology and the power transfer distribution factors.

The engine works on the lossless (DC) network: ``P = B @ theta`` with ``B`` the bus
admittance matrix assembled from branch susceptances ``1/x``. Bus angles are solved with
the slack bus as reference, and a branch's flow is ``(theta_i - theta_j) / x_e``.

Every branch flow is therefore a *linear* function of the bus injections, with coefficients
given by the power transfer distribution factors:

    f_e = sum_k PTDF[e][k] * P_k

That linearity is the whole basis of the product. It means a dispatch plan expressed as a
range of injections per bus yields an *exact* range of flows, computed with interval
arithmetic rather than a solver run and hoped over.

Islanding is detected explicitly. Dropping a branch can split the network, and the DC
equations have no solution across a split — so a contingency that islands a feeder is
reported as ``islanded``, never silently ignored, because an islanded feeder is a worse
outcome than an overloaded one.
"""

from __future__ import annotations

from typing import TypedDict

from . import linalg
from .protocol import EngineError


class TopologyBranch(TypedDict):
    id: str
    fromIndex: int
    toIndex: int
    reactancePu: float


#: ``(id, fromBus, toBus, reactance)`` — the branch identity topology needs. Positional
#: because it is unpacked straight from the model on every call.
BranchSpec = tuple[str, str, str, float]


class Topology(TypedDict):
    order: list[str]
    index: dict[str, int]
    slackIndex: int
    branches: list[TopologyBranch]
    connected: bool


def build_topology(
    buses: list[str],
    branches: list[BranchSpec],
    slack_bus: str,
) -> Topology:
    """Index the network and decide whether the in-service branch set is connected.

    ``buses`` order fixes every index, so the matrix layout — and therefore the floating
    point summation order — depends only on the model, never on dictionary iteration.
    """
    order = list(buses)
    index = {bus: position for position, bus in enumerate(order)}
    if slack_bus not in index:
        raise EngineError("UNKNOWN_SLACK", f"slack bus {slack_bus!r} is not in the bus list")
    if len(order) < 2:
        raise EngineError("DEGENERATE_NETWORK", "a DC model needs at least two buses")

    resolved: list[TopologyBranch] = []
    for branch_id, from_bus, to_bus, reactance in branches:
        if from_bus not in index:
            raise EngineError("UNKNOWN_BUS", f"branch {branch_id!r} references unknown bus {from_bus!r}")
        if to_bus not in index:
            raise EngineError("UNKNOWN_BUS", f"branch {branch_id!r} references unknown bus {to_bus!r}")
        if from_bus == to_bus:
            raise EngineError("DEGENERATE_BRANCH", f"branch {branch_id!r} is a self-loop")
        if reactance == 0.0:
            raise EngineError("DEGENERATE_BRANCH", f"branch {branch_id!r} has zero reactance")
        resolved.append(
            {
                "id": branch_id,
                "fromIndex": index[from_bus],
                "toIndex": index[to_bus],
                "reactancePu": reactance,
            }
        )

    return {
        "order": order,
        "index": index,
        "slackIndex": index[slack_bus],
        "branches": resolved,
        "connected": is_connected(len(order), resolved),
    }


def is_connected(size: int, branches: list[TopologyBranch]) -> bool:
    """Union-find over the branch set. Deterministic, and independent of solve order."""
    parent = list(range(size))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for branch in branches:
        left, right = find(branch["fromIndex"]), find(branch["toIndex"])
        if left != right:
            parent[left] = right
    return len({find(node) for node in range(size)}) == 1


def admittance(topology: Topology) -> list[list[float]]:
    """Assemble ``B`` with the slack row and column removed.

    The slack bus absorbs the system imbalance, so its angle is pinned to zero and its
    equation dropped. What remains is a square, non-singular system when the network is
    connected.
    """
    reduced = [bus for position, bus in enumerate(topology["order"]) if position != topology["slackIndex"]]
    local = {bus: position for position, bus in enumerate(reduced)}

    matrix = linalg.zeros(len(reduced), len(reduced))
    for branch in topology["branches"]:
        if branch["fromIndex"] == topology["slackIndex"] or branch["toIndex"] == topology["slackIndex"]:
            # A branch to slack still contributes to the other end's diagonal.
            other = branch["toIndex"] if branch["fromIndex"] == topology["slackIndex"] else branch["fromIndex"]
            if other == topology["slackIndex"]:
                continue
            matrix[local[topology["order"][other]]][local[topology["order"][other]]] += (
                1.0 / branch["reactancePu"]
            )
            continue
        left = local[topology["order"][branch["fromIndex"]]]
        right = local[topology["order"][branch["toIndex"]]]
        susceptance = 1.0 / branch["reactancePu"]
        matrix[left][left] += susceptance
        matrix[right][right] += susceptance
        matrix[left][right] -= susceptance
        matrix[right][left] -= susceptance
    return matrix


def flows_from_angles(topology: Topology, angles: list[float]) -> list[float]:
    """Branch flows from a full-length angle vector, indexed like ``topology.branches``."""
    flows: list[float] = []
    for branch in topology["branches"]:
        difference = angles[branch["fromIndex"]] - angles[branch["toIndex"]]
        flows.append(difference / branch["reactancePu"])
    return flows


def power_transfer_factors(topology: Topology) -> list[list[float]]:
    """``PTDF[branch_index][bus_index]`` — the sensitivity of each flow to each injection.

    Unit-injection solves rather than a matrix inverse, because a solve is one LU
    factorisation reused per column and keeps the failure mode explicit: if the network is
    islanded the solve raises instead of returning infinities.
    """
    if not topology["connected"]:
        raise EngineError(
            "ISLANDED",
            "the in-service network is not connected; a DC power flow is undefined until "
            "the split is re-energised",
        )

    size = len(topology["order"])
    slack = topology["slackIndex"]
    reduced_buses = [position for position in range(size) if position != slack]
    # Maps a full-system bus position to its row in the reduced system.
    row_of_bus = {position: index for index, position in enumerate(reduced_buses)}
    matrix = admittance(topology)

    factors: list[list[float]] = [[0.0] * size for _ in topology["branches"]]
    for injection_bus in range(size):
        if injection_bus == slack:
            # The slack absorbs the imbalance, so it has no solve of its own. Its column is
            # filled in afterwards so every row sums to zero, which is what makes
            # `sum_k PTDF[e][k] * P_k` invariant to how the imbalance is distributed.
            continue
        rhs = [0.0] * len(reduced_buses)
        rhs[row_of_bus[injection_bus]] = 1.0
        reduced_angles = linalg.solve(matrix, rhs)
        angles = [0.0] * size
        for position, angle in zip(reduced_buses, reduced_angles, strict=True):
            angles[position] = angle
        for row, flow in enumerate(flows_from_angles(topology, angles)):
            factors[row][injection_bus] = flow

    # Close the slack column. Injecting one MW at *every* bus and withdrawing it at slack is
    # a net-zero injection, so every branch flow must be zero — which forces the slack
    # sensitivity to be the negation of the others. Setting it to zero instead would make
    # flows depend on the slack's own injection, which is not how a network behaves.
    for row in range(len(factors)):
        factors[row][slack] = -sum(factors[row][bus] for bus in range(size) if bus != slack)
    return factors


def drop_branch(topology: Topology, branch_id: str) -> Topology:
    """A copy of the topology with one branch out of service."""
    if branch_id not in {branch["id"] for branch in topology["branches"]}:
        raise EngineError("UNKNOWN_BRANCH", f"outage target {branch_id!r} is not an in-service branch")
    remaining = [branch for branch in topology["branches"] if branch["id"] != branch_id]
    return {**topology, "branches": remaining, "connected": is_connected(len(topology["order"]), remaining)}
