"""Content addressing — the reason a study can be filed and re-checked years later.

Two runs of the same model, the same plan, and the same constraints must produce the same
digest, on any machine, forever. That is only true if canonicalisation is total: no
dictionary iteration order, no float formatting differences, no whitespace, no key
ordering left to chance.

So the canonical form is explicit: keys sorted, floats quantised to a fixed number of
decimal places, separators pinned, and non-finite values rejected outright. A digest computed
over that form is a statement about the *study*, not about the serialiser that happened to
serialise it.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .protocol import EngineError

#: Decimal places retained for floats in the canonical form. Inputs are quantities in MW and
#: per-unit; six places is a nanometre of precision and well below any engineering
#: tolerance, so quantising here cannot merge two genuinely different studies.
FLOAT_PLACES = 6


def canonical(value: Any) -> Any:
    """Recursively canonicalise a JSON value: sorted keys, quantised floats, no whitespace.

    Every number becomes a float, including ones ``json.loads`` parsed as ``int``. That is not
    tidiness, it is the only way this digest can match the TypeScript implementation: JSON has
    one number type, but Python distinguishes ``int`` from ``float`` and re-serialises them
    differently (``1`` versus ``1.0``), while JavaScript does not. Promoting ints to floats
    here makes both sides emit ``1.0`` for the same document.
    """
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise EngineError("NON_FINITE", "cannot content-address a non-finite value")
        rounded = round(number, FLOAT_PLACES)
        # Normalise -0.0 to 0.0 so the two cannot produce different digests.
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    raise EngineError("UNHASHABLE", f"cannot canonicalise a {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """The canonical serialisation, as a string."""
    return json.dumps(
        canonical(value), separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    """A `sha256:<hex>` content address for any canonicalisable value."""
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
