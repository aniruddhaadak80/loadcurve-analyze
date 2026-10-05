# ADR 0002 — The deterministic engine is a pure Python function

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

Parts of this product must be exactly right. Whether a dispatch plan is feasible is arithmetic
and constraint logic: a bound that is off by 0.7 MW is a plan that either cannot be dispatched
or can, and the difference is a real interconnection cost. Those parts need property tests,
deterministic replay, and the ability to run with no network and no API key.

## Decision

Those parts live in `services/engine`, a **dependency-free** Python package, invoked as a
**pure function over stdin/stdout**. No server, no port, no daemon, no persisted state.

- Input: one JSON object `{"op": "...", "input": ...}` on stdin.
- Output: one JSON object on stdout. Diagnostics on stderr only.
- No clock reads, no randomness, no network, no filesystem. Time and entropy are arguments.

Zero runtime dependencies, not "few". `pydantic` was available and deliberately unused: the
engine is spawned on every tool invocation, so every transitive dependency is startup latency,
and `TypedDict` plus explicit validation is a stronger gate than a permissive model would be.

## Consequences

**Good**

- Every operation is property-testable in isolation with `hypothesis`; the suite generates
  networks and plans rather than asserting hand-picked examples.
- Two concurrent calls cannot interfere — there is no state to interleave.
- A failing call is reproducible: same input, same failure, same bytes.
- `mypy --strict` over a small dependency-free package is a genuinely strong gate. It found real
  defects during development, including a wrong branch tuple order that the type checker flagged
  as non-overlapping comparisons.
- The product is fully exercisable offline, which is what keeps the local suite fast.

**Bad**

- No in-process sharing, so each call pays interpreter startup (~120 ms). Accepted: the
  alternative — a persistent worker — introduces a lifetime and a port, and buys latency the
  operator will not notice against a study that takes seconds of thought.
- JSON serialisation is the boundary, so a type error surfaces at the boundary rather than at the
  call site. Mitigated by validating on **both** sides: `packages/engine-model` parses the
  request before spawning and the response after, so a drift is caught at build time.

## The hand-rolled linear algebra

The DC model needs `B θ = P` solved for a small dense system. NumPy would do it, and the engine
does not use it. A Gaussian elimination with partial pivoting uses only `+ - * /`, which
IEEE-754 specifies exactly — so a study produces bit-identical results on any conforming
platform, which is the property a filed document depends on. A singular matrix raises
`SINGULAR_MATRIX` rather than returning zeros, because a singular admittance matrix is a
modelling error an operator must see.

See [ADR-0004](0004-no-model-in-the-analysis-path.md) for why the boundary excludes model calls
entirely rather than merely preferring determinism.
