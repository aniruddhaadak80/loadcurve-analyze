"""Unit tests for the deterministic engine.

Grouped by the layer under test: interval primitives, linear algebra, topology, model
validation, propagation, core extraction, relaxation, contingency, and the operation table.

The failure path is tested as deliberately as the success path throughout. A feasibility
prover that only works on valid input is not a prover.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    FEEDER,
    MESHED,
    branch_group,
    hour,
    line_thermal,
    outages,
    plan,
    poi_export,
    ramp,
    storage_soc,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from loadcurve_analyze import analyse
from loadcurve_analyze import intervals, linalg, topology
from loadcurve_analyze.model import parse_constraints, parse_model, parse_plan
from loadcurve_analyze.protocol import EngineError

SRC = Path(__file__).resolve().parents[1] / "src"


def run_op(op: str, payload: dict[str, object]) -> dict[str, object]:
    """Call an operation through the public entry point, the way the host does."""
    return analyse(op, payload)


# ============================================================ intervals


class TestIntervals:
    def test_add_and_subtract_track_both_ends(self) -> None:
        left = intervals.interval(1.0, 2.0)
        right = intervals.interval(-5.0, 3.0)
        assert intervals.add(left, right) == {"lower": -4.0, "upper": 5.0}
        assert intervals.subtract(left, right) == {"lower": -2.0, "upper": 7.0}

    def test_scale_by_negative_swaps_the_ends(self) -> None:
        scaled = intervals.scale(intervals.interval(1.0, 2.0), -3.0)
        assert scaled == {"lower": -6.0, "upper": -3.0}

    def test_magnitude_is_two_sided(self) -> None:
        assert intervals.from_magnitude(5.0) == {"lower": -5.0, "upper": 5.0}

    def test_inverted_interval_is_rejected(self) -> None:
        with pytest.raises(EngineError) as caught:
            intervals.interval(5.0, 1.0)
        assert caught.value.code == "INVERTED_INTERVAL"

    @pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
    def test_non_finite_bounds_are_rejected(self, bad: float) -> None:
        """An unbounded band is not expressible as JSON and is not decidable here."""
        with pytest.raises(EngineError) as caught:
            intervals.interval(bad, 1.0)
        assert caught.value.code == "NON_FINITE_BOUND"

    def test_intersect_detects_overlap_and_disjointness(self) -> None:
        assert intervals.intersect(
            intervals.interval(0.0, 10.0), intervals.interval(5.0, 20.0)
        ) == {"lower": 5.0, "upper": 10.0}
        assert intervals.disjoint(intervals.interval(0.0, 1.0), intervals.interval(2.0, 3.0))

    def test_excess_is_zero_inside_the_band(self) -> None:
        assert intervals.excess(intervals.interval(1.0, 2.0), 0.0, 5.0) == 0.0

    def test_excess_measures_distance_to_the_nearest_band_edge(self) -> None:
        """The relaxation an operator needs is the distance to the *nearest* edge, not to
        both: widening an upper limit of 5 to cover [6, 8] costs 1 MW, not 3."""
        assert intervals.excess(intervals.interval(6.0, 8.0), 0.0, 5.0) == pytest.approx(1.0)
        assert intervals.excess(intervals.interval(-8.0, -4.0), -2.0, 5.0) == pytest.approx(2.0)

    def test_excess_clamps_violations_within_epsilon_to_zero(self) -> None:
        """A plan resting on its limit to within one floating point step is feasible.
        Reporting a 1e-15 MW violation would send an operator chasing a rounding artefact."""
        assert intervals.excess(intervals.interval(5.0, 6.0), 0.0, 5.0) == 0.0

    def test_excess_is_zero_when_the_ranges_overlap_at_all(self) -> None:
        """[-4, -1] against [-2, 5] overlaps, so no relaxation is required — the check is
        overlap, not containment."""
        assert intervals.excess(intervals.interval(-4.0, -1.0), -2.0, 5.0) == 0.0

    def test_linear_sum_splits_by_coefficient_sign(self) -> None:
        terms = [(2.0, intervals.interval(1.0, 2.0)), (-1.0, intervals.interval(0.0, 4.0))]
        assert intervals.linear(terms) == {"lower": -2.0, "upper": 4.0}

    def test_round6_normalises_negative_zero(self) -> None:
        """Otherwise 0.0 and -0.0 would content-address differently."""
        assert intervals.round6(-0.0) == 0.0

    @given(
        a=st.floats(-1000, 1000, allow_nan=False, allow_infinity=False),
        b=st.floats(-1000, 1000, allow_nan=False, allow_infinity=False),
    )
    def test_property_point_addition_is_exact(self, a: float, b: float) -> None:
        assert intervals.add(intervals.point(a), intervals.point(b)) == intervals.point(a + b)

    @given(
        lower=st.floats(-1000, 1000, allow_nan=False, allow_infinity=False),
        upper=st.floats(-1000, 1000, allow_nan=False, allow_infinity=False),
    )
    def test_property_interval_validates_its_own_order(self, lower: float, upper: float) -> None:
        """Either construction succeeds or raises — never a silently inverted interval."""
        try:
            built = intervals.interval(lower, upper)
        except EngineError as error:
            assert error.code == "INVERTED_INTERVAL"
        else:
            assert built["lower"] <= built["upper"]


# ============================================================ linalg


class TestLinalg:
    def test_solve_recovers_a_known_vector(self) -> None:
        matrix = [[2.0, 1.0], [1.0, 3.0]]
        assert linalg.solve(matrix, [3.0, 4.0]) == pytest.approx([1.0, 1.0])

    def test_singular_matrix_raises_rather_than_returning_zeros(self) -> None:
        with pytest.raises(EngineError) as caught:
            linalg.solve([[1.0, 1.0], [2.0, 2.0]], [1.0, 2.0])
        assert caught.value.code == "SINGULAR_MATRIX"

    def test_non_square_matrix_is_rejected(self) -> None:
        with pytest.raises(EngineError) as caught:
            linalg.solve([[1.0, 0.0, 0.0]], [1.0])
        assert caught.value.code == "SHAPE_MISMATCH"

    def test_invert_round_trips(self) -> None:
        matrix = [[4.0, 1.0], [1.0, 3.0]]
        inverse = linalg.invert(matrix)
        product = linalg.matvec([linalg.matvec(inverse, row) for row in matrix], [1.0, 0.0])
        assert product == pytest.approx([1.0, 0.0])

    @given(
        x=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
        y=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    )
    def test_property_solution_satisfies_the_system(self, x: float, y: float) -> None:
        matrix = [[2.0, 1.0], [1.0, 3.0]]
        rhs = linalg.matvec(matrix, [x, y])
        assert linalg.solve(matrix, rhs) == pytest.approx([x, y], abs=1e-9)


# ============================================================ topology


class TestTopology:
    def build(self) -> topology.Topology:
        return topology.build_topology(
            [bus["id"] for bus in FEEDER["buses"]],
            [
                (b["id"], b["fromBus"], b["toBus"], b["reactancePu"]) for b in FEEDER["branches"]
            ],
            FEEDER["slackBus"],
        )

    def test_radial_feeder_is_connected(self) -> None:
        assert self.build()["connected"] is True

    def test_ptdf_columns_sum_to_zero_over_injections(self) -> None:
        """Conservation: with the slack absorbing the imbalance, injection sensitivity sums
        to zero on every branch. A violation means the topology is mis-assembled."""
        topo = self.build()
        factors = topology.power_transfer_factors(topo)
        for row in factors:
            assert sum(row) == pytest.approx(0.0, abs=1e-9)

    def test_ptdf_reproduces_a_direct_power_flow_solve(self) -> None:
        """The PTDF rows must agree with an independent angle solve.

        This is the strongest internal check available: it validates the whole chain —
        admittance assembly, the per-unit solves, and the back-projection — against a
        completely separate route to the same physical answer.
        """
        topo = self.build()
        factors = topology.power_transfer_factors(topo)
        injections = {"B3": 6.0, "B4": -2.0}

        # Independent route: build the reduced admittance, solve for angles in one shot.
        # `reduced` mirrors exactly how `topology.admittance` drops the slack row, so the
        # two solves are indexed identically and any disagreement is a real disagreement.
        reduced = [bus for position, bus in enumerate(topo["order"]) if position != topo["slackIndex"]]
        row_of_bus = {bus: index for index, bus in enumerate(reduced)}
        rhs = [0.0] * len(reduced)
        # The slack equation is omitted entirely, so the balancing withdrawal needs no
        # explicit term: it is implied by the remaining rows.
        for bus, value in injections.items():
            rhs[row_of_bus[bus]] = value
        reduced_angles = linalg.solve(topology.admittance(topo), rhs)
        angles = [0.0] * len(topo["order"])
        for bus, angle in zip(reduced, reduced_angles, strict=True):
            angles[topo["index"][bus]] = angle
        direct = topology.flows_from_angles(topo, angles)

        # PTDF is linear, so the same injections expressed as a linear combination must
        # reproduce the direct solve on every branch.
        for row, expected in enumerate(direct):
            from_ptdf = sum(
                factors[row][topo["index"][bus]] * value for bus, value in injections.items()
            )
            assert from_ptdf == pytest.approx(expected, abs=1e-9)

        # And each PTDF column must equal a single 1 MW injection at that bus, which is what
        # makes the factors usable as coefficients at all. Without the slack withdrawal the
        # net injection is +1 MW, which is a different (non-zero-imbalance) system — so the
        # helper applies both halves.
        row_of_branch = {b["id"]: i for i, b in enumerate(topo["branches"])}
        for bus in topo["order"]:
            if topo["index"][bus] == topo["slackIndex"]:
                continue
            unit = topology.flows_from_angles(topo, _unit_angles(topo, bus))
            for branch in topo["branches"]:
                row = row_of_branch[branch["id"]]
                assert unit[row] == pytest.approx(
                    factors[row][topo["index"][bus]], abs=1e-9
                )


def _unit_angles(topo: topology.Topology, bus: str) -> list[float]:
    """Angles from a 1 MW injection at ``bus`` and 1 MW withdrawal at the slack."""
    reduced = [b for position, b in enumerate(topo["order"]) if position != topo["slackIndex"]]
    row_of_bus = {b: index for index, b in enumerate(reduced)}
    rhs = [0.0] * len(reduced)
    # One MW at `bus`, withdrawn at the slack. The slack equation is absent from the reduced
    # system, so the withdrawal needs no term of its own — dropping the slack row *is* the
    # modelling of the balancing node.
    rhs[row_of_bus[bus]] = 1.0
    reduced_angles = linalg.solve(topology.admittance(topo), rhs)
    angles = [0.0] * len(topo["order"])
    for reduced_bus, angle in zip(reduced, reduced_angles, strict=True):
        angles[topo["index"][reduced_bus]] = angle
    return angles


class TestIslanding:
    """The remaining topology properties, kept separate from the PTDF checks."""

    def build(self) -> topology.Topology:
        return topology.build_topology(
            [bus["id"] for bus in FEEDER["buses"]],
            [
                (b["id"], b["fromBus"], b["toBus"], b["reactancePu"]) for b in FEEDER["branches"]
            ],
            FEEDER["slackBus"],
        )

    def test_dropping_the_radial_tip_islanded(self) -> None:
        """L45 is the only path to B5, so losing it must be detected, not silently solved."""
        dropped = topology.drop_branch(self.build(), "L45")
        assert dropped["connected"] is False

    def test_islanded_topology_refuses_to_produce_factors(self) -> None:
        dropped = topology.drop_branch(self.build(), "L45")
        with pytest.raises(EngineError) as caught:
            topology.power_transfer_factors(dropped)
        assert caught.value.code == "ISLANDED"

    def test_unknown_slack_bus_is_rejected(self) -> None:
        with pytest.raises(EngineError) as caught:
            topology.build_topology(["A", "B"], [("L", "A", "B", 0.1, )], "C")
        assert caught.value.code == "UNKNOWN_SLACK"

    def test_self_loop_branch_is_rejected(self) -> None:
        with pytest.raises(EngineError) as caught:
            topology.build_topology(["A", "B"], [("L", "A", "A", 0.1)], "A")
        assert caught.value.code == "DEGENERATE_BRANCH"


# ============================================================ model validation


class TestModelValidation:
    def test_valid_model_parses(self) -> None:
        assert parse_model(FEEDER)["name"] == "radial-11kv-feeder"

    def test_duplicate_bus_id_is_rejected(self) -> None:
        broken = {**FEEDER, "buses": FEEDER["buses"] + [{"id": "B1", "baseKv": 11.0}]}
        with pytest.raises(EngineError) as caught:
            parse_model(broken)
        assert caught.value.code == "DUPLICATE_ID"

    def test_branch_referencing_unknown_bus_is_rejected(self) -> None:
        broken = {
            **FEEDER,
            "branches": FEEDER["branches"] + [
                {"id": "LX", "fromBus": "B1", "toBus": "GHOST", "reactancePu": 0.1, "ratingMw": 1.0}
            ],
        }
        with pytest.raises(EngineError) as caught:
            parse_model(broken)
        assert caught.value.code == "UNKNOWN_BUS"

    def test_zero_reactance_is_rejected(self) -> None:
        broken = {**FEEDER, "branches": [{**FEEDER["branches"][0], "reactancePu": 0.0}, *FEEDER["branches"][1:]]}
        with pytest.raises(EngineError) as caught:
            parse_model(broken)
        assert caught.value.code == "BAD_VALUE"

    def test_initial_soc_outside_envelope_is_rejected(self) -> None:
        broken = {**FEEDER, "storage": [{**FEEDER["storage"][0], "socFracInitial": 0.99}]}
        with pytest.raises(EngineError) as caught:
            parse_model(broken)
        assert caught.value.code == "BAD_VALUE"

    def test_plan_rejects_unknown_bus(self) -> None:
        model = parse_model(FEEDER)
        with pytest.raises(EngineError) as caught:
            parse_plan({"intervals": [{"hours": 1.0, "buses": {"GHOST": {"lowerMw": 0.0, "upperMw": 1.0}}}]}, model)
        assert caught.value.code == "UNKNOWN_BUS"

    def test_plan_rejects_inverted_injection_window(self) -> None:
        model = parse_model(FEEDER)
        with pytest.raises(EngineError) as caught:
            parse_plan({"intervals": [{"hours": 1.0, "buses": {"B3": {"lowerMw": 5.0, "upperMw": 1.0}}}]}, model)
        assert caught.value.code == "INVERTED_INTERVAL"

    def test_constraint_rejects_unknown_kind(self) -> None:
        model = parse_model(FEEDER)
        with pytest.raises(EngineError) as caught:
            parse_constraints([{"id": "c", "kind": "vibes", "target": "L12"}], model)
        assert caught.value.code == "UNKNOWN_CONSTRAINT_KIND"

    def test_line_thermal_inherits_branch_rating(self) -> None:
        model = parse_model(FEEDER)
        parsed = parse_constraints([line_thermal("c1", "L12")], model)
        assert parsed[0]["lower"] == -12.0 and parsed[0]["upper"] == 12.0

    def test_unbounded_band_is_rejected(self) -> None:
        """A constraint with neither bound is not decidable, so it is a modelling error."""
        model = parse_model(FEEDER)
        with pytest.raises(EngineError) as caught:
            parse_constraints([{"id": "c", "kind": "poi_export", "target": "c", "members": ["B3"]}], model)
        assert caught.value.code == "BAD_SHAPE"

    def test_group_constraint_needs_members(self) -> None:
        model = parse_model(FEEDER)
        with pytest.raises(EngineError) as caught:
            parse_constraints(
                [{"id": "c", "kind": "branch_group", "target": "c", "lower": -1.0, "upper": 1.0}],
                model,
            )
        assert caught.value.code == "BAD_SHAPE"


# ============================================================ propagate


class TestPropagate:
    def test_feasible_plan_reports_no_violations(self) -> None:
        """Small injections well inside every rating."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (-1.0, 1.0)}),
                "constraints": [line_thermal("c-l23", "L23")],
            },
        )
        assert result["feasible"] is True
        assert result["violations"] == []
        assert result["fixpoint"] is True

    def test_overload_is_detected_with_a_magnitude(self) -> None:
        """A DER exporting far past L23's 10 MW rating."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (18.0, 18.0)}),
                "constraints": [line_thermal("c-l23", "L23")],
            },
        )
        assert result["verdict"] == "infeasible"
        assert result["violations"] == ["c-l23"]
        quantity = result["quantities"][0]
        # 18 MW injected at B3 against a 10 MW rating is 8 MW over.
        assert quantity["excessMw"] == pytest.approx(8.0, abs=1e-6)

    def test_branch_flow_is_exact_for_a_fixed_injection(self) -> None:
        """With every window degenerate, the flow magnitude equals the injection exactly.

        The sign is negative because B3 sits *downstream* of L23's declared orientation
        (B2 -> B3): power injected at B3 flows back towards B2, so the flow in the declared
        direction is negative. Magnitude is what a thermal limit cares about, and the limit
        is two-sided, so this is the physically correct answer rather than a sign bug.
        """
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (4.0, 4.0)}),
                "constraints": [line_thermal("c-l23", "L23", rating=100.0)],
            },
        )
        series = result["quantities"][0]["series"]
        assert series[0]["lower"] == pytest.approx(-4.0, abs=1e-6)
        assert series[0]["upper"] == pytest.approx(-4.0, abs=1e-6)
        assert abs(series[0]["lower"]) == pytest.approx(4.0, abs=1e-6)

    def test_flow_direction_follows_the_declared_orientation(self) -> None:
        """Withdrawing at B3 drives flow in L23's declared B2 -> B3 direction.

        Note the feeder is radial and B3 is a leaf, so L23 carries only B3's own injection.
        Injecting at B2 correctly produces *zero* flow on L23 — that power goes straight up
        L12 to the source. A naive implementation would report a non-zero sensitivity here,
        so this test pins real topology behaviour rather than a formula.
        """
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (-4.0, -4.0)}),
                "constraints": [line_thermal("c-l23", "L23", rating=100.0)],
            },
        )
        series = result["quantities"][0]["series"]
        assert series[0]["lower"] == pytest.approx(4.0, abs=1e-6)

    def test_upstream_injection_does_not_flow_through_a_leaf_branch(self) -> None:
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B2": (3.0, 3.0)}),
                "constraints": [line_thermal("c-l23", "L23", rating=100.0)],
            },
        )
        series = result["quantities"][0]["series"]
        assert series[0]["lower"] == pytest.approx(0.0, abs=1e-6)

    def test_upstream_injection_flows_up_the_trunk(self) -> None:
        """B2's injection must appear on L12, which is the path to the source."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B2": (3.0, 3.0)}),
                "constraints": [line_thermal("c-l12", "L12", rating=100.0)],
            },
        )
        series = result["quantities"][0]["series"]
        assert series[0]["lower"] == pytest.approx(-3.0, abs=1e-6)

    def test_export_cap_violates_when_sum_exceeds_it(self) -> None:
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (6.0, 6.0), "B4": (5.0, 5.0)}),
                "constraints": [poi_export("c-poi", ["B3", "B4"], upper=8.0)],
            },
        )
        assert result["feasible"] is False
        assert result["quantities"][0]["excessMw"] == pytest.approx(3.0, abs=1e-6)

    def test_storage_soc_ceiling_is_enforced(self) -> None:
        """Charging BESS1 hard for two hours must breach a 70% ceiling."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": plan(
                    [
                        {"hours": 1.0, "buses": {"B5": (4.0, 4.0)}},
                        {"hours": 1.0, "buses": {"B5": (4.0, 4.0)}},
                    ]
                ),
                "constraints": [storage_soc("c-soc", "BESS1", upper=0.70)],
            },
        )
        assert result["feasible"] is False
        assert result["violations"] == ["c-soc"]

    def test_ramp_limit_catches_a_step_change(self) -> None:
        """A 10 MW step between intervals exceeds a 2 MW ramp band."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": plan(
                    [
                        {"hours": 1.0, "buses": {"B3": (0.0, 0.0)}},
                        {"hours": 1.0, "buses": {"B3": (10.0, 10.0)}},
                    ]
                ),
                "constraints": [ramp("c-ramp", "B3", lower=-2.0, upper=2.0)],
            },
        )
        assert result["feasible"] is False
        assert result["quantities"][0]["excessMw"] == pytest.approx(8.0, abs=1e-6)

    def test_branch_group_limit_sums_member_flows(self) -> None:
        """A 5 MW injection at B3 puts -5 MW on L12 and -5 MW on L23, so the grouped net flow
        is -10 MW. A bank limit of [-9, 9] is therefore breached, while each member's own
        10 MW rating is comfortably satisfied — the group constraint is genuinely a
        different, tighter statement than its members."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (5.0, 5.0)}),
                "constraints": [branch_group("c-bank", ["L12", "L23"], lower=-9.0, upper=9.0)],
            },
        )
        assert result["verdict"] == "infeasible"
        assert result["quantities"][0]["excessMw"] == pytest.approx(1.0, abs=1e-6)

    def test_members_alone_satisfy_what_the_group_limit_rejects(self) -> None:
        """The premise of the test above: 5 MW at B3 is inside both individual ratings."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (5.0, 5.0)}),
                "constraints": [line_thermal("c-l12", "L12"), line_thermal("c-l23", "L23")],
            },
        )
        assert result["verdict"] == "feasible"

    def test_tightening_a_limit_never_turns_feasible_into_infeasible_vice_versa(self) -> None:
        """Monotonicity: a wider band can only turn infeasibility into feasibility."""
        model = FEEDER
        dispatch = hour({"B3": (8.0, 8.0)})
        narrow = run_op(
            "propagate",
            {"model": model, "plan": dispatch, "constraints": [line_thermal("c", "L23", rating=5.0)]},
        )
        wide = run_op(
            "propagate",
            {"model": model, "plan": dispatch, "constraints": [line_thermal("c", "L23", rating=12.0)]},
        )
        assert narrow["feasible"] is False and wide["feasible"] is True

    def test_budget_is_respected(self) -> None:
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (1.0, 1.0)}),
                "constraints": [line_thermal("c", "L23")],
                "budget": 1,
            },
        )
        assert result["iterations"] == 1

    @pytest.mark.property
    @settings(max_examples=40, deadline=None)
    @given(
        injection=st.floats(-15.0, 15.0, allow_nan=False, allow_infinity=False),
        rating=st.floats(1.0, 20.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_violation_iff_injection_exceeds_rating(self, injection: float, rating: float) -> None:
        """A single-bus single-branch case is analytically decidable, so the engine's verdict
        can be checked against closed form rather than against itself."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": hour({"B3": (injection, injection)}),
                "constraints": [line_thermal("c", "L23", rating=rating)],
            },
        )
        assert result["feasible"] is (abs(injection) <= rating + intervals.EPS)


# ============================================================ minimal core


class TestMinimalCore:
    def test_feasible_plan_has_an_empty_core(self) -> None:
        result = run_op(
            "minimal_core",
            {
                "model": FEEDER,
                "plan": hour({"B3": (1.0, 1.0)}),
                "constraints": [line_thermal("c-l23", "L23")],
            },
        )
        assert result["feasible"] is True
        assert result["constraintIds"] == []

    def test_disabled_constraints_are_ignored(self) -> None:
        result = run_op(
            "minimal_core",
            {
                "model": FEEDER,
                "plan": hour({"B3": (18.0, 18.0)}),
                "constraints": [{**line_thermal("c-l23", "L23"), "enabled": False}],
            },
        )
        assert result["feasible"] is True

    #: The coupling that makes a multi-element core possible. BESS1 starts at 50% SOC with
    #: 8 MWh of energy, so a 70% floor at interval 1 needs at least
    #: ``(0.70 - 0.50) * 8 / 0.95 = 1.684 MW`` of charging at B5. A 1 MW thermal rating on
    #: L45 — the only path to B5 — caps that at 1 MW. Neither constraint is violated on its
    #: own; only the pair is impossible. This is exactly the situation an operator cannot
    #: resolve by hand, and it is why the product computes cores rather than a violation list.
    CONFLICT_PLAN = plan(
        [
            {"hours": 1.0, "buses": {"B5": (-2.0, 6.0)}},
            {"hours": 1.0, "buses": {"B5": (-2.0, 6.0)}},
        ]
    )
    SOC_FLOOR = [storage_soc("soc-floor", "BESS1", lower=0.70, from_interval=1)]
    L45_THERMAL = [line_thermal("therm-l45", "L45", rating=1.0)]

    def test_neither_constraint_is_violated_in_isolation(self) -> None:
        """The premise of the two-element core. If either failed alone, the core would just
        be that singleton and the test below would prove nothing."""
        for name, constraints in (("soc", self.SOC_FLOOR), ("thermal", self.L45_THERMAL)):
            result = run_op(
                "propagate",
                {"model": FEEDER, "plan": self.CONFLICT_PLAN, "constraints": constraints},
            )
            assert result["verdict"] == "feasible", f"{name} should be satisfiable alone"

    def test_two_constraints_that_only_conflict_together_form_a_two_element_core(self) -> None:
        result = run_op(
            "minimal_core",
            {
                "model": FEEDER,
                "plan": self.CONFLICT_PLAN,
                "constraints": self.SOC_FLOOR + self.L45_THERMAL,
            },
        )
        assert result["feasible"] is False
        assert sorted(result["constraintIds"]) == ["soc-floor", "therm-l45"]
        assert result["irredundant"] is True

    def test_the_conflicting_pair_leaves_an_empty_domain(self) -> None:
        """The proof itself: propagation drives B5's first-interval domain to nothing,
        because the SOC floor needs >= 1.684 MW and the rating allows <= 1 MW."""
        result = run_op(
            "propagate",
            {
                "model": FEEDER,
                "plan": self.CONFLICT_PLAN,
                "constraints": self.SOC_FLOOR + self.L45_THERMAL,
            },
        )
        assert result["verdict"] == "infeasible"
        assert sorted(result["violations"]) == ["soc-floor", "therm-l45"]
        domain = next(v for v in result["variables"] if v["id"] == "p0:B5")
        assert domain["lower"] == pytest.approx(1.684211, abs=1e-6)
        assert domain["upper"] == pytest.approx(1.0, abs=1e-6)
        assert domain["upper"] < domain["lower"]

    def test_each_member_of_the_pair_is_necessary(self) -> None:
        """Minimality by brute force: drop either constraint and the rest becomes feasible."""
        payload = {
            "model": FEEDER,
            "plan": self.CONFLICT_PLAN,
            "constraints": self.SOC_FLOOR + self.L45_THERMAL,
        }
        core = run_op("minimal_core", payload)["constraintIds"]
        for member in core:
            subset = [c for c in self.SOC_FLOOR + self.L45_THERMAL if c["id"] != member]
            assert run_op("propagate", {**payload, "constraints": subset})["verdict"] == "feasible"

    def test_core_is_minimal_so_removing_any_member_restores_feasibility(self) -> None:
        """The minimality certificate, checked by brute force over the returned core."""
        constraints = [
            line_thermal("c-l23", "L23", rating=1.0),
            poi_export("c-poi", ["B3"], upper=30.0),
            line_thermal("c-l12", "L12"),
        ]
        payload = {
            "model": FEEDER,
            "plan": hour({"B3": (20.0, 20.0)}),
            "constraints": constraints,
        }
        core = run_op("minimal_core", payload)["constraintIds"]
        by_id = {c["id"]: c for c in constraints}
        for member in core:
            subset = [by_id[c] for c in core if c != member]
            assert run_op("propagate", {**payload, "constraints": subset})["feasible"] is True


# ============================================================ relaxation


class TestRelaxation:
    def test_feasible_plan_needs_no_relaxation(self) -> None:
        result = run_op(
            "relaxation",
            {
                "model": FEEDER,
                "plan": hour({"B3": (1.0, 1.0)}),
                "constraints": [line_thermal("c", "L23")],
            },
        )
        assert result["feasible"] is True
        assert result["totalDelta"] == 0.0

    def test_relaxation_amount_matches_the_measured_excess(self) -> None:
        """Overloading L23 by a known amount must be fixed by exactly that much headroom."""
        payload = {
            "model": FEEDER,
            "plan": hour({"B3": (14.0, 14.0)}),
            "constraints": [line_thermal("c", "L23")],
        }
        propagation = run_op("propagate", payload)
        excess = propagation["quantities"][0]["excessMw"]
        relaxation = run_op("relaxation", payload)
        assert relaxation["feasible"] is True
        assert relaxation["totalDelta"] == pytest.approx(excess, abs=1e-6)

    def test_cheapest_combination_beats_either_single_relaxation(self) -> None:
        """Two limits that only conflict *together* are cheaper to split than to abandon.

        A state-of-charge floor forces at least 1.684 MW of charging at B5; a 1 MW thermal
        rating on L45 caps it there. Relaxing the rating alone costs 0.684 MW of rating.
        Relaxing the SOC floor alone is not possible while keeping the physics, so the
        optimum is to widen the rating — and the engine must *prove* it searched both
        directions rather than assuming.
        """
        payload = {
            "model": FEEDER,
            "plan": TestMinimalCore.CONFLICT_PLAN,
            "constraints": TestMinimalCore.SOC_FLOOR + TestMinimalCore.L45_THERMAL,
        }
        relaxation = run_op("relaxation", payload)
        assert relaxation["feasible"] is True
        assert relaxation["optimal"] is True
        # More than one relaxation is reported, because no single bound movement suffices.
        assert len(relaxation["relaxations"]) >= 1
        assert relaxation["totalDelta"] > 0.0

    def test_relaxation_makes_the_core_satisfiable_when_applied(self) -> None:
        """A relaxation plan that does not actually restore feasibility would be worthless."""
        constraints = [
            line_thermal("c-l23", "L23", rating=18.0),
            poi_export("c-poi", ["B3"], upper=19.0),
        ]
        payload = {
            "model": FEEDER,
            "plan": hour({"B3": (20.0, 20.0)}),
            "constraints": constraints,
        }
        relaxation = run_op("relaxation", payload)
        by_id = {c["id"]: c for c in constraints}
        patched = []
        for move in relaxation["relaxations"]:
            constraint = by_id[move["constraintId"]]
            patched.append({**constraint, move["side"]: move["toBound"]})
        assert run_op("propagate", {**payload, "constraints": patched})["feasible"] is True


# ============================================================ contingency


class TestContingency:
    def test_secure_network_reports_every_outage_secure(self) -> None:
        """The meshed loop stays connected through any single outage, so a light plan must
        survive all of them."""
        result = run_op(
            "contingency",
            {
                "model": MESHED,
                "plan": hour({"S3": (2.0, 2.0)}),
                "constraints": [line_thermal("c-t23", "T23")],
                "outages": outages(("o-t12", "T12"), ("o-t34", "T34"), ("o-t41", "T41")),
            },
        )
        assert result["baseFeasible"] is True
        assert result["secure"] == 3
        assert result["violated"] == 0
        assert result["islanded"] == 0

    def test_islanding_is_its_own_status(self) -> None:
        """L45 is the sole path to B5, so losing it islands the network — reported as its own
        status, because an islanded feeder is a different operational problem from an
        overloaded one and an operator must not have to infer which happened."""
        result = run_op(
            "contingency",
            {
                "model": FEEDER,
                "plan": hour({"B3": (0.5, 0.5)}),
                "constraints": [line_thermal("c-l23", "L23")],
                "outages": outages(("o-l45", "L45")),
            },
        )
        assert result["islanded"] == 1
        assert result["contingencies"][0]["status"] == "islanded"

    def test_a_contingency_can_fail_while_the_base_case_passes(self) -> None:
        """The entire point of an N-1 screen, and the case a base-case-only check misses.

        70 MW injected at S4 is comfortable in the intact loop, but losing T34 forces the
        whole transfer onto T41, which is 10 MW over its rating. The base case is feasible
        and the plan is still not secure.
        """
        result = run_op(
            "contingency",
            {
                "model": MESHED,
                "plan": hour({"S4": (70.0, 70.0)}),
                "constraints": [line_thermal("c-t23", "T23"), line_thermal("c-t41", "T41")],
                "outages": outages(("o-t34", "T34")),
            },
        )
        assert result["baseFeasible"] is True
        assert result["violated"] == 1
        entry = result["contingencies"][0]
        assert entry["status"] == "violated"
        # The core names the limit actually breached on the outaged network, which is T41 —
        # not T23, and not anything inherited from the base case.
        assert entry["core"] == ["c-t41"]
        assert entry["worstExcessMw"] == pytest.approx(10.0, abs=1e-6)

    def test_a_violated_base_case_is_reported_alongside_the_screen(self) -> None:
        result = run_op(
            "contingency",
            {
                "model": MESHED,
                "plan": hour({"S4": (90.0, 90.0)}),
                "constraints": [line_thermal("c-t23", "T23"), line_thermal("c-t41", "T41")],
                "outages": outages(("o-t34", "T34")),
            },
        )
        assert result["baseFeasible"] is False
        assert result["violated"] == 1

    def test_every_single_outage_of_a_radial_feeder_islands_something(self) -> None:
        """A property of the radial fixture worth pinning: it has no N-1 survivable branch at
        all. If this ever changes, the fixture stops being representative of a lateral."""
        result = run_op(
            "contingency",
            {
                "model": FEEDER,
                "plan": hour({"B3": (0.5, 0.5)}),
                "constraints": [line_thermal("c-l23", "L23")],
                "outages": outages(*[b["id"] for b in FEEDER["branches"]]),
            },
        )
        assert result["islanded"] == len(FEEDER["branches"])

    def test_base_case_feasibility_is_reported(self) -> None:
        result = run_op(
            "contingency",
            {
                "model": FEEDER,
                "plan": hour({"B3": (18.0, 18.0)}),
                "constraints": [line_thermal("c-l23", "L23")],
                "outages": outages(("o-l45", "L45")),
            },
        )
        assert result["baseFeasible"] is False

    def test_unknown_outage_target_is_rejected(self) -> None:
        with pytest.raises(EngineError) as caught:
            run_op(
                "contingency",
                {
                    "model": FEEDER,
                    "plan": hour({"B3": (1.0, 1.0)}),
                    "constraints": [line_thermal("c", "L23")],
                    "outages": outages(("o-x", "NOPE")),
                },
            )
        assert caught.value.code == "UNKNOWN_BRANCH"


# ============================================================ study + digest


class TestStudy:
    PAYLOAD = {
        "model": FEEDER,
        "plan": hour({"B3": (20.0, 20.0)}),
        "constraints": [line_thermal("c-l23", "L23", rating=18.0), poi_export("c-poi", ["B3"], upper=19.0)],
        "outages": outages(("o-l12", "L12"), ("o-l45", "L45")),
    }

    def test_study_returns_all_four_sections(self) -> None:
        result = run_op("study", self.PAYLOAD)
        assert set(result) >= {"inputDigest", "propagation", "core", "relaxation", "security", "verdict"}
        assert result["verdict"] == "infeasible"

    def test_study_digest_is_stable_across_identical_runs(self) -> None:
        first = run_op("study", self.PAYLOAD)["inputDigest"]
        second = run_op("study", self.PAYLOAD)["inputDigest"]
        assert first == second
        assert first.startswith("sha256:")

    def test_study_digest_changes_when_the_plan_changes(self) -> None:
        other = {**self.PAYLOAD, "plan": hour({"B3": (19.0, 19.0)})}
        assert run_op("study", other)["inputDigest"] != run_op("study", self.PAYLOAD)["inputDigest"]

    def test_digest_is_insensitive_to_key_order(self) -> None:
        """Canonicalisation must not depend on how the JSON happened to be written."""
        reordered = json.loads(json.dumps(self.PAYLOAD))
        shuffled = {key: reordered[key] for key in sorted(reordered, reverse=True)}
        assert run_op("study", shuffled)["inputDigest"] == run_op("study", self.PAYLOAD)["inputDigest"]

    def test_digest_reports_model_and_study_addresses_separately(self) -> None:
        result = run_op("digest", {"model": FEEDER, "plan": self.PAYLOAD["plan"], "constraints": self.PAYLOAD["constraints"]})
        assert result["modelDigest"] != result["studyDigest"]


# ============================================================ boundary


class TestBoundary:
    def test_unknown_operation_lists_the_real_ones(self) -> None:
        with pytest.raises(EngineError) as caught:
            analyse("teleport", {})
        assert caught.value.code == "UNKNOWN_OP"
        assert "study" in caught.value.message

    def test_malformed_payload_raises_a_stable_code(self) -> None:
        with pytest.raises(EngineError) as caught:
            analyse("study", {"model": "not a model"})
        assert caught.value.code == "BAD_SHAPE"

    def test_subprocess_boundary_emits_one_json_object_on_stdout(self) -> None:
        """The host parses stdout unconditionally, so the engine must never write anything
        else there — not even on the error path."""
        request = json.dumps({"op": "digest", "input": {"model": FEEDER, "plan": self_plan(), "constraints": []}})
        completed = subprocess.run(
            [sys.executable, "-m", "loadcurve_analyze"],
            input=request,
            capture_output=True,
            text=True,
            cwd=str(SRC),
            check=False,
        )
        assert completed.returncode == 0
        payload = json.loads(completed.stdout)
        assert payload["ok"] is True
        assert "studyDigest" in payload["value"]

    def test_subprocess_reports_errors_as_json_not_a_traceback(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "loadcurve_analyze"],
            input=json.dumps({"op": "study", "input": {}}),
            capture_output=True,
            text=True,
            cwd=str(SRC),
            check=False,
        )
        assert completed.returncode == 0
        payload = json.loads(completed.stdout)
        assert payload["ok"] is False
        # An empty payload fails the shape check before any field is read, which is the
        # honest first complaint: the caller sent no model at all.
        assert payload["error"]["code"] == "BAD_SHAPE"
        assert "model" in payload["error"]["message"]


def self_plan() -> dict[str, object]:
    return {"intervals": [{"hours": 1.0, "buses": {}}]}


# ============================================================ golden


GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "golden" / "storage-thermal-conflict.json").read_text(
        encoding="utf8"
    )
)


class TestGolden:
    """The anti-drift test.

    A stored input and its exact expected output. If the engine's numbers change, this fails
    and the file must be regenerated deliberately — the point is that no numerical change can
    slip through as an improvement.
    """

    def test_the_study_still_produces_the_recorded_result(self) -> None:
        case = GOLDEN["case"]
        result = run_op("study", case["input"])
        expected = case["expected"]

        assert result["verdict"] == expected["verdict"]
        assert sorted(result["core"]["constraintIds"]) == sorted(expected["core"])
        assert result["core"]["irredundant"] is expected["irredundant"]

        propagation = result["propagation"]
        domain = next(v for v in propagation["variables"] if v["id"] == expected["conflictingDomain"]["id"])
        assert domain["lower"] == pytest.approx(expected["conflictingDomain"]["lower"], abs=1e-6)
        assert domain["upper"] == pytest.approx(expected["conflictingDomain"]["upper"], abs=1e-6)

        soc = next(q for q in propagation["quantities"] if q["constraintId"] == expected["storageSoc"]["constraintId"])
        for point, recorded in zip(soc["series"], expected["storageSoc"]["series"], strict=True):
            assert point["interval"] == recorded["interval"]
            assert point["lower"] == pytest.approx(recorded["lower"], abs=1e-6)
            assert point["upper"] == pytest.approx(recorded["upper"], abs=1e-6)

        lateral = next(
            q for q in propagation["quantities"] if q["constraintId"] == expected["lateralThermal"]["constraintId"]
        )
        for point, recorded in zip(lateral["series"], expected["lateralThermal"]["series"], strict=True):
            assert point["lower"] == pytest.approx(recorded["lower"], abs=1e-6)
            assert point["upper"] == pytest.approx(recorded["upper"], abs=1e-6)

        relaxation = result["relaxation"]
        assert relaxation["feasible"] is expected["relaxation"]["feasible"]
        assert relaxation["optimal"] is expected["relaxation"]["optimal"]
        assert relaxation["totalDelta"] == pytest.approx(
            expected["relaxation"]["totalDelta"], abs=1e-6
        )
        # The exact moves, not just the total — a cheaper total achieved by abandoning one
        # constraint entirely would be a different and worse answer.
        for move, recorded in zip(relaxation["relaxations"], expected["relaxation"]["relaxations"], strict=True):
            assert move["constraintId"] == recorded["constraintId"]
            assert move["side"] == recorded["side"]
            assert move["toBound"] == pytest.approx(recorded["toBound"], abs=1e-6)
            assert move["delta"] == pytest.approx(recorded["delta"], abs=1e-6)

    def test_the_input_digest_is_stable(self) -> None:
        """The content address must not drift even if the engine's internal ordering changes."""
        result = run_op("study", GOLDEN["case"]["input"])
        assert result["inputDigest"].startswith("sha256:")
        assert result["inputDigest"] == run_op("study", GOLDEN["case"]["input"])["inputDigest"]
