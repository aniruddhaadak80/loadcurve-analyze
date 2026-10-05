"""Deterministic engine for loadcurve-analyze.

The engine is deliberately dependency-free. Every operation is a pure function:
same input, same output, no clock, no network, no randomness. Time and any entropy
must be passed in by the caller.

The product is a feasibility prover for grid operating plans. It answers three questions,
in increasing order of usefulness:

    propagate      which constraints does this plan violate, and by how much?
    minimal_core   which *smallest* subset of constraints is already contradictory?
    relaxation     what is the cheapest set of bound changes that fixes it?

``contingency`` adds the N-1 security screen, and ``study`` runs all of them together.
"""

from .protocol import EngineError, dispatch
from .analysis import ENGINE_VERSION, EPSILON, OPERATIONS, analyse
from .digest import digest

__all__ = [
    "ENGINE_VERSION",
    "EPSILON",
    "EngineError",
    "OPERATIONS",
    "analyse",
    "digest",
    "dispatch",
]
__version__ = ENGINE_VERSION
