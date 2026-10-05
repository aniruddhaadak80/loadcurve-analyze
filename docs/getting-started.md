# Getting started

## Requirements

- **Node ≥ 22.12** (`.nvmrc` pins the tested version)
- **Python ≥ 3.11** (`.python-version` pins it) — the deterministic engine is Python

## Install

```bash
git clone https://github.com/aniruddhaadak80/loadcurve-analyze.git
cd loadcurve-analyze
npm install
npm run build
```

`npm install` also runs Prettier, so the tree is formatted before your first gate.

## Verify the install

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

The `engine` row is the one that matters. It does not check that a `python` binary exists — it
**runs the engine** and asks for a content address, because a version check passes on a machine
where the engine is broken.

`WARN` on `config` is expected on a fresh checkout: the product runs on defaults.

## Run the worked example

```bash
loadcurve verify example
```

The example is a radial 11 kV feeder where a battery must reach 70% charge by hour two. That
needs 1.684 MW through a lateral rated 1 MW. Neither limit is violated alone; the pair admits no
dispatch. The output is in the [README](../README.md) in full.

## Write your own study

A study is one JSON document:

```json
{
  "model": {
    "name": "my-feeder",
    "baseMva": 40,
    "slackBus": "SLACK",
    "buses": [
      { "id": "SLACK", "baseKv": 69 },
      { "id": "B1", "baseKv": 11 }
    ],
    "branches": [{ "id": "TX1", "fromBus": "SLACK", "toBus": "B1", "reactancePu": 0.04, "ratingMw": 25 }],
    "storage": []
  },
  "plan": {
    "intervals": [{ "hours": 1, "buses": { "B1": { "lowerMw": -5, "upperMw": 5 } } }]
  },
  "constraints": [{ "id": "tx-rating", "kind": "line_thermal", "target": "TX1" }],
  "outages": []
}
```

```bash
loadcurve verify my-study.json
loadcurve verify my-study.json --json > result.json
```

`line_thermal` with no bounds inherits the branch's own ±rating. Every other kind must state at
least one bound — an unbounded band is not decidable, and the engine rejects it.

### Get the example request as a starting point

```bash
loadcurve verify example --json > my-study.json
```

That is a complete, valid, _infeasible_ study. Edit it into your own case.

## Interpret the verdict

| Verdict        | Means                                            |
| -------------- | ------------------------------------------------ |
| `feasible`     | an admissible dispatch exists                    |
| `infeasible`   | a proof that none does — read the core           |
| `undetermined` | the plan is `partial` and leaves a bus unbounded |

On `infeasible`, run `loadcurve explain` for the core and the cheapest fix on their own. On the
exited code: a verified-infeasible plan is a **successful analysis** and exits `0`; only
`undetermined` exits `1`.

## Run the web app

```bash
npm run dev
```

Then open `http://localhost:3000`. With Python available the page computes the example study live
on each request; the heading states which. See
[ADR-0003](adr/0003-web-app-self-contained.md) for why that distinction is shown.

## Use it from an agent

```bash
loadcurve mcp serve
```

Seven tools over stdio. See [MCP](mcp.md).

## Next

- [Architecture](architecture.md) — the narrow waist and what the engine actually computes
- [CLI reference](cli.md) · [MCP](mcp.md) · [Skills](skills.md)
- [Troubleshooting](troubleshooting.md) — when a gate fails
