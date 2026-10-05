# LoadCurve Analyze

**Prove a grid operating plan is physically admissible — and when it is not, name the smallest
contradictory constraint set and the exact relaxation each constraint needs.**

A dispatcher proposes a plan. Some limits are about to be breached. The question is never "is
this bad?" — it is **"which two of my assumptions are fighting, and what is the cheapest way to
settle it?"** This tool answers that, deterministically, in under a second.

```console
$ loadcurve verify example

Verdict: infeasible
Input digest: sha256:7044544dd180104868da7c705efcc0fd0371eb48bc55329e586ed5cb2aa05fac

CONSTRAINT   KIND          TARGET  VERDICT  WORST
l23-rating   line_thermal  L23     satisfied  -
soc-floor    storage_soc   BESS1   violated  0.081 MW
l45-lateral  line_thermal  L45     violated  0.684 MW
poi-export   poi_export    poi     satisfied  -
------------------------------------------------------------------------
Minimal unsatisfiable core (2 member(s)):
  - soc-floor
  - l45-lateral
  verified minimal: removing any one member makes the rest satisfiable (6 satisfiability checks)

Cheapest relaxation (total 0.765, proven minimum total movement):
CONSTRAINT                SIDE    FROM        TO          DELTA
l45-lateral               lower   -1.000      -1.684      0.684
soc-floor                 lower   0.700       0.619       0.081

Base case: infeasible. N-1 screen: 2 islanded
OUTAGE            BRANCH      STATUS      WORST       CORE
lose-l12          L12         islanded    -           -
lose-l14          L14         islanded    -           -
------------------------------------------------------------------------
Converged: yes after 2 sweep(s)
```

## What this actually does

The example above is the whole product in one screen. A battery must reach 70% charge by the
second hour. That needs **1.684 MW** through a lateral rated **1 MW**. Neither limit is
violated on its own — the floor is reachable if the lateral is upgraded, the lateral is fine if
the floor is dropped — and **the pair admits no dispatch at all.**

That is the situation this tool exists for, and a violation list cannot express it. Every
violated constraint explains itself; what an engineer needs is the _coupling_, and finding it by
hand means deleting constraints one at a time and re-running the study until something changes.

So this does not report violations. It computes:

| Question                      | Answer                                                                     |
| ----------------------------- | -------------------------------------------------------------------------- |
| Is the plan admissible?       | `feasible` / `infeasible` / `undetermined` — three-valued on purpose       |
| Which limits are responsible? | The **minimal unsatisfiable core**, verified minimal, not merely plausible |
| What is the cheapest fix?     | The minimum total bound movement, proven minimal                           |
| Is it secure?                 | An N-1 screen with islanding reported separately from overload             |

## Why the engine is Python and boring

An interconnection study is a document that gets filed. Its numbers must be reproducible years
later on a different machine, so the analysis path is pure code:

- **No model call, anywhere.** Not "usually" — structurally. There is no provider abstraction to
  reach for, because a non-deterministic answer disqualifies the result. See
  [ADR-0004](docs/adr/0004-no-model-in-the-analysis-path.md).
- **No clock, no network, no randomness, no filesystem.** The engine is a subprocess over
  stdin/stdout: one JSON request in, one JSON response out. Same input, same bytes, forever.
- **Hand-rolled dense linear algebra** rather than NumPy — a Gaussian elimination uses only
  `+ - * /`, which IEEE-754 specifies exactly, so results are bit-identical across platforms.
- **Content-addressed inputs.** Every study carries a `sha256` over its canonical JSON, so
  "did these two people run the same study?" is answerable without trusting either filename.

## Install

Requires **Node ≥ 22.12** and **Python ≥ 3.11**.

```bash
git clone https://github.com/aniruddhaadak80/loadcurve-analyze.git
cd loadcurve-analyze
npm install
npm run build
loadcurve doctor
```

## Walkthrough

Every command below was run against this repository.

**1. Confirm the installation actually works.** `doctor` does not check that a binary exists on
`PATH` — it runs the Python engine and asks for a content address, because a version check
passes on a machine where the engine is broken.

```bash
loadcurve doctor
```

```
loadcurve-analyze doctor
  [PASS] node     v22.23.2
  [PASS] package  loadcurve-analyze@0.1.0
  [PASS] skills   3 skills, 0 invalid
  [PASS] plugins  1 active, 0 disabled
  [WARN] config   no product.config.json — using defaults
         fix: run with defaults, or create product.config.json
  [PASS] engine   reachable, digest 7044544dd180…
  [PASS] tools    7 registered, 5 engine-backed

all required checks passed
```

**2. Run the worked example.** The header of this README is that output.

```bash
loadcurve verify example
```

**3. Ask for the explanation on its own.**

```bash
loadcurve explain example
```

**4. Write a study file and screen your own.** The request format is
`{model, plan, constraints, outages}`:

```bash
loadcurve verify my-study.json --json > result.json
```

**5. Expose it to any MCP client.** Seven tools over stdio — the engine as a tool provider for
other agents:

```bash
loadcurve mcp serve
```

**6. Run the gates.**

```bash
npm run check
```

## The five constraint kinds

| Kind           | Quantity                         | Real-world meaning                             |
| -------------- | -------------------------------- | ---------------------------------------------- |
| `line_thermal` | one branch's flow                | conductor rating                               |
| `branch_group` | net flow across several branches | transformer bank, intertie                     |
| `poi_export`   | net injection over buses         | DER export cap at the point of interconnection |
| `storage_soc`  | state-of-charge envelope         | grid-code charge requirement                   |
| `ramp`         | per-interval change              | ramp-rate limit                                |

Each is a **linear form over bus injections**, which is what makes the propagation exact rather
than conservative: a linear functional over a box attains its extrema at the vertices, so the
attainable flow range is computed, not bounded.

`storage_soc` is what makes multi-constraint cores possible. The charge requirement at interval
_i_ is `soc₀ + Σ_{j<i} eff·P_j·hours_j / energy` — a linear form in the _earlier_ injections,
which the thermal limits upstream also constrain. The two therefore couple, and can conflict
jointly when neither is at fault alone.

## Constraints, not validation

Scope a constraint to a window when it binds only part of the horizon. A grid code's "70% by
hour 2" is `fromInterval: 1`; without it the floor is wrongly reported as violated in hour 1,
where it does not apply. This is why `QuantitySeries` reports each point at its **true interval
index** rather than renumbering from zero.

A verdict is three-valued because "no conclusion is possible" is a real answer:

- `feasible` — an admissible dispatch exists.
- `infeasible` — **a proof** that none does: propagation drove some domain empty.
- `undetermined` — the plan declares `partial` and leaves a bus unbounded. Name the bus; do not
  guess a value for it.

## Architecture

One rule: **every capability is a `Tool` in one registry.**

```
packages/tools/src/registry.ts   ← the seven tools, declared once
        │
        ├── packages/cli       loadcurve verify | explain | doctor | tools | mcp
        ├── packages/mcp       stdio transport, stateless, no duplicated logic
        └── apps/web           server components reading through lib/
                    │
                    ▼
          packages/engine-client          one typed client, validated both ways
                    │
                    ▼
       services/engine (Python)          propagate → minimal_core → relaxation
```

Surfaces are transports. There is no second implementation of anything.

| Package              | Owns                                                                |
| -------------------- | ------------------------------------------------------------------- |
| `core`               | the `Tool` interface, the registry, the error taxonomy. No I/O.     |
| `tools`              | the product's capabilities                                          |
| `engine-model`       | the engine's I/O contract as zod schemas, so both sides are checked |
| `engine-client`      | the subprocess boundary                                             |
| `studies`            | content-addressed SQLite persistence                                |
| `skills` / `plugins` | on-disk catalogs with validation and version gating                 |
| `mcp` / `cli`        | transports                                                          |

### The footprint ladder

Where new capability goes, in order. **Adding a core tool is last, not first.**

1. Extend an existing tool
2. New CLI command + matching skill
3. Service-gated tool (needs the engine subprocess)
4. Plugin (a model-format adapter)
5. New MCP server tool
6. New core tool — last resort

## Deliberately omitted

Omission is a design decision and each one is recorded here, because a surface left out silently
is indistinguishable from one that was forgotten.

- **Desktop / Electron.** This is a study tool that runs in CI and on a terminal. An Electron
  wrapper adds a 150 MB download to display a window around a web app.
- **Channels.** No remote surface exists; the only consumers are the CLI, JSON and MCP.
- **LLM providers.** A model call in the analysis path makes a study non-reproducible, and
  reproducibility is the product. Shipping a provider abstraction would also create a second
  path around the narrow waist.

## MCP

```bash
loadcurve mcp serve
```

| Tool                         | Use it to                                                 |
| ---------------------------- | --------------------------------------------------------- |
| `grid_verify_plan`           | prove admissibility, with core, relaxation and N-1 screen |
| `grid_propagate`             | get violated constraints and excesses, cheaply            |
| `grid_explain_infeasibility` | get the core and the cheapest fix                         |
| `grid_screen_contingencies`  | run an N-1 security assessment                            |
| `grid_digest`                | content-address a model or study                          |
| `list_skills`                | discover the documented workflows                         |
| `list_plugins`               | explain a missing capability                              |

## Skills

Three workflows ship in [`skills/`](skills/), loaded from disk with frontmatter validation.
A body change without a `metadata.version` bump **fails CI**.

- [`screen-dispatch-plan`](skills/screen-dispatch-plan/SKILL.md) — prove a plan before committing it
- [`diagnose-infeasibility`](skills/diagnose-infeasibility/SKILL.md) — find the pair that conflicts
- [`assess-n1-security`](skills/assess-n1-security/SKILL.md) — single-element outage assessment

## Documentation

- [Getting started](docs/getting-started.md) · [Architecture](docs/architecture.md)
- [CLI](docs/cli.md) · [MCP](docs/mcp.md) · [Skills](docs/skills.md) · [Plugins](docs/plugins.md)
- [Configuration](docs/configuration.md) · [Troubleshooting](docs/troubleshooting.md)
- ADRs: [narrow waist](docs/adr/0001-the-narrow-waist.md) ·
  [engine boundary](docs/adr/0002-python-engine-boundary.md) ·
  [content-addressed storage](docs/adr/0003-content-addressed-storage.md) ·
  [no model in the analysis path](docs/adr/0004-no-model-in-the-analysis-path.md)

## Development

```bash
npm run check          # the aggregate gate CI runs
python -m pytest services/engine -q
npm run dev            # web app on :3000
```

Python gates:

```bash
python -m ruff check services/engine
python -m mypy --strict services/engine/src
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Agent-facing instructions are in
[AGENTS.md](AGENTS.md); [CLAUDE.md](CLAUDE.md) points there rather than duplicating it.

## License

Apache-2.0 — see [LICENSE](LICENSE), [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
