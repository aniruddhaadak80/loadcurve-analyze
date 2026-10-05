# Architecture

One rule governs this codebase: **every capability is a `Tool` in one registry.** Surfaces are
transports. Full reasoning in [ADR-0001](adr/0001-narrow-waist.md).

## The shape

```
                      packages/tools  ← the seven capabilities, declared once
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
    packages/cli       packages/mcp        apps/web
    loadcurve verify   stdio transport     server components
    loadcurve explain                     via lib/
    loadcurve doctor
          │                  │                  │
          └──────────────────┴──────────────────┘
                             ▼
                  packages/engine-client
              one typed client, validated both ways
                             ▼
                    services/engine  (Python)
              propagate → minimal_core → relaxation
                             ▼
                   packages/studies (SQLite)
```

## The engine

Four pure functions, each answering a question a dispatcher actually asks.

### `propagate` — which limits does this plan violate?

Not "check each constraint" — **propagate** them. The variables are the bus injections in each
interval; each constraint is a linear form over those variables; satisfying a constraint narrows
the domains of the variables in it. A narrowed domain then tightens the next constraint, until
nothing changes. That is bounds consistency, and it is what makes a two- or three-member core
possible: if constraints were merely checked independently, every infeasibility would have a
singleton core and the product would prove nothing a violation list does not.

Two properties make this exact rather than conservative:

- **Everything is linear.** A branch flow is a PTDF row over injections. A state-of-charge at
  interval _i_ is `soc₀ + Σ_{j<i} eff·P_j·hours_j / energy` — linear in the earlier intervals,
  which is precisely what couples a storage envelope to the thermal limits upstream of it.
- **Back-projection inverts forward evaluation.** For `Σ c_k x_k ∈ [L, U]`, each `x_k` is
  narrowed by subtracting the others' contributions. Because the forms are linear, that
  narrowing removes only values that cannot appear in any satisfying assignment.

### `minimal_core` — which constraints are jointly responsible?

Deletion-based: for each constraint in order, drop it and keep the result infeasible. The
guarantee that removing any remaining member restores satisfiability is **verified** before the
core is returned, and the verification count is reported. An operator filing a study deserves a
certificate, not a promise.

### `relaxation` — what is the cheapest fix?

A genuine L1 minimum: the smallest total bound movement satisfying every constraint in the core.
Each edge's cost is found by bisection, which is valid because feasibility is _monotone_ in a
relaxation — widening a band cannot remove a solution. With an exact cost per edge, the
combination search is exhaustive over sign choices and the total is a proven minimum rather than
a good guess.

Above 14 core members it degrades to per-edge bests and reports `optimal: false`.

### `contingency` — is it secure?

Each declared outage is applied and the network re-factored from scratch, because a contingency
changes the admittance matrix and therefore the PTDF. Three outcomes, never two: `secure`,
`violated`, or `islanded`. Islanding is its own status because a split network is a
categorically different operational problem from an overload.

## Precision

- **Bit-reproducible.** Dense LU with partial pivoting uses only `+ - * /`, which IEEE-754
  specifies exactly. No transcendental is allowed on the bound path.
- **EPS-clamped.** A plan resting on its limit to within 1e-9 is feasible. Without this, a value
  that reaches its bound to within one floating-point step — which interval arithmetic over
  several terms produces routinely — is reported as a 1e-15 MW violation, and the operator goes
  to chase a rounding artefact.
- **Deterministic ordering.** Bus order fixes every matrix index, so the floating-point
  summation order depends only on the model.

## Three-valued verdicts

`feasible` is a proof that an admissible dispatch exists. `infeasible` is a proof that none
does. `undetermined` means the plan declared `partial` and left a bus unbounded — no conclusion
is possible, and that is reported rather than guessed.

A plan is `partial` when a bus absent from an interval means "unconstrained" rather than "not
dispatching". The default is the latter: a dispatch plan states what will happen, and a bus it
says nothing about sits still. The distinction is exposed because getting it wrong turns a proof
into a guess.

## Content addressing

Every study carries `sha256` over its canonical JSON. Identical inputs always produce the same
address, independent of key order, and an identical re-analysis is the _same study_ rather than a
duplicate row.

The canonical form is pinned: sorted keys, six decimal places, integral floats rendered with an
explicit `.0`, negative zero normalised, non-finite values rejected. That last rule is
cross-language — Python distinguishes `int` from `float` and re-serialises them differently while
JavaScript does not, so the engine promotes every number to float. `packages/studies` mirrors
this in TypeScript and a test asserts the two agree, by invoking the engine as a subprocess.

## Package responsibilities

| Package             | Owns                             | Never does                        |
| ------------------- | -------------------------------- | --------------------------------- |
| `core`              | `Tool`, registry, error taxonomy | I/O of any kind                   |
| `tools`             | the product's capabilities       | transport                         |
| `engine-model`      | the wire contract as zod schemas | logic                             |
| `engine-client`     | the subprocess boundary          | domain reasoning                  |
| `studies`           | content-addressed persistence    | analysis                          |
| `skills`, `plugins` | on-disk catalogs                 | behaviour                         |
| `mcp`, `cli`        | transports                       | domain logic                      |
| `config`            | typed settings                   | defaults that override the engine |

## The footprint ladder

Where new capability goes, in order. **Adding a core tool is last, not first.** The full ladder
lives in [`AGENTS.md`](../AGENTS.md); it is repeated here because this is where a reader asks the
question.

1. Extend an existing tool
2. New CLI command + matching skill
3. Service-gated tool (needs the engine subprocess)
4. Plugin (a model-format adapter)
5. New MCP server tool
6. New core tool — last resort

Adding a tool to `packages/tools` makes it reachable from every surface, so there is no step
that can be forgotten.
