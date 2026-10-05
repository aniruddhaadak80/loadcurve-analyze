"""Closed-interval arithmetic — the primitive every bound in this engine is made of.

An interval is a closed real interval ``[lower, upper]``.

The important property, and the reason this engine can claim a *proof* rather than a bound:
a linear functional over a hyperrectangular uncertainty set attains its extrema at the
vertices of that set. Every quantity this engine derives from a dispatch plan is a linear
functional of per-bus injection intervals, so interval arithmetic here is not an
over-approximation — it computes the exact range. That is what makes ``minimal_core``
sound: when it reports two constraints as contradictory, no admissible dispatch exists
between them.

Only ``+ - * /`` and comparisons are used anywhere on the bound path. Those are IEEE-754
exact operations, so the engine is bit-reproducible across platforms — no libm
transcendental is allowed to perturb a study result.
"""

from __future__ import annotations

import math
from typing import Final, TypedDict

from .protocol import EngineError

#: Tolerance for float comparisons. Bounds are compared with this slack so that a value
#: that is 1e-12 over a limit because of rounding is not reported as a violation.
EPS: Final[float] = 1e-9


class Interval(TypedDict):
    """A closed real interval."""

    lower: float
    upper: float


def interval(lower: float, upper: float, *, what: str = "interval") -> Interval:
    """Build a validated interval. Rejects NaN, infinities, and inverted bounds."""
    for name, value in (("lower", lower), ("upper", upper)):
        if not math.isfinite(value):
            raise EngineError(
                "NON_FINITE_BOUND",
                f"{what}.{name} must be finite (got {value!r}); unbounded bands are not "
                "expressible as JSON and are not decidable here",
            )
    if lower > upper + EPS:
        raise EngineError(
            "INVERTED_INTERVAL",
            f"{what} is inverted: lower {lower} exceeds upper {upper}",
        )
    # Within tolerance, snap to degenerate rather than returning an interval whose own ends
    # are inverted. Callers may assume lower <= upper without re-checking against EPS.
    lower = min(lower, upper)
    return {"lower": lower, "upper": upper}


def point(value: float) -> Interval:
    """A degenerate interval pinned to one value."""
    return interval(value, value, what="point")


def from_magnitude(maximum: float, *, what: str = "magnitude") -> Interval:
    """The symmetric band ``[-maximum, +maximum]`` — how a two-sided limit is expressed."""
    return interval(-maximum, maximum, what=what)


def add(left: Interval, right: Interval) -> Interval:
    return {"lower": left["lower"] + right["lower"], "upper": left["upper"] + right["upper"]}


def negate(value: Interval) -> Interval:
    return {"lower": -value["upper"], "upper": -value["lower"]}


def subtract(left: Interval, right: Interval) -> Interval:
    return add(left, negate(right))


def scale(value: Interval, coefficient: float) -> Interval:
    """Multiply by a signed scalar, swapping the ends when the coefficient is negative."""
    if not math.isfinite(coefficient):
        raise EngineError("NON_FINITE_BOUND", f"scale coefficient must be finite (got {coefficient})")
    if coefficient >= 0:
        return {"lower": coefficient * value["lower"], "upper": coefficient * value["upper"]}
    return {"lower": coefficient * value["upper"], "upper": coefficient * value["lower"]}


def linear(terms: list[tuple[float, Interval]]) -> Interval:
    """``sum(coefficient * interval)`` over a linear form.

    Exact for independent per-term intervals, which is the case for every PTDF row: the
    coefficients come from the network topology and the terms are per-bus injections.
    """
    lower = 0.0
    upper = 0.0
    for coefficient, value in terms:
        if coefficient >= 0:
            lower += coefficient * value["lower"]
            upper += coefficient * value["upper"]
        else:
            lower += coefficient * value["upper"]
            upper += coefficient * value["lower"]
    return {"lower": lower, "upper": upper}


def intersect(left: Interval, right: Interval) -> Interval | None:
    """Overlap of two intervals, or ``None`` when they are disjoint."""
    lower = max(left["lower"], right["lower"])
    upper = min(left["upper"], right["upper"])
    if lower > upper + EPS:
        return None
    return {"lower": lower, "upper": upper}


def disjoint(left: Interval, right: Interval) -> bool:
    return intersect(left, right) is None


def contains(value: Interval, candidate: float) -> bool:
    return candidate >= value["lower"] - EPS and candidate <= value["upper"] + EPS


def width(value: Interval) -> float:
    return value["upper"] - value["lower"]


def lower_excess(value: Interval, limit: float) -> float:
    """How far ``value`` sits above ``limit``; ``0.0`` when it does not."""
    return max(0.0, value["lower"] - limit)


def upper_excess(value: Interval, limit: float) -> float:
    """How far ``value`` sits below ``limit``; ``0.0`` when it does not."""
    return max(0.0, limit - value["upper"])


def excess(value: Interval, lower_limit: float, upper_limit: float) -> float:
    """Total distance between ``value`` and the permitted band, ``0.0`` when satisfied.

    ``EPS`` is subtracted before the comparison, so a plan that lands exactly on its limit
    is feasible. Without this, a value that reaches its bound to within one floating point
    step — which interval arithmetic over several terms produces routinely — would be
    reported as a violation of magnitude 1e-15 MW, and an operator would be sent to chase a
    rounding artefact.
    """
    return max(0.0, value["lower"] - upper_limit - EPS, lower_limit - value["upper"] - EPS)


def round6(value: float) -> float:
    """Transport rounding.

    Applied only when serialising a result, never inside a comparison, so the arithmetic
    stays exact and only the wire format is quantised to a micrometre-grade grid.
    """
    return round(value + 0.0, 6)


def rounded(value: Interval) -> Interval:
    return {"lower": round6(value["lower"]), "upper": round6(value["upper"])}
