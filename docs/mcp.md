# MCP

```bash
loadcurve mcp serve
```

The server speaks MCP over **stdio**. It exposes the product as a tool provider for other
agents, which is the highest-leverage thing this product can do: an agent that is about to
commit a dispatch plan can ask whether it is admissible instead of guessing.

stdout belongs to the protocol once the server starts. Diagnostics go to stderr.

## Tools

### `grid_verify_plan`

Prove whether a plan is physically admissible. Runs propagation to a fixed point, extracts the
minimal core on failure, computes the cheapest relaxation, and screens declared N-1 outages.

Returns the verdict, per-constraint verdicts and excesses, the core, the relaxation plan, and the
contingency report. **Use this before committing a dispatch or interconnection plan; do not
hand-check flows against ratings.**

### `grid_propagate`

Same propagation, cheaper result. Use when you already know the plan is feasible and only need
the numbers.

### `grid_explain_infeasibility`

The smallest contradictory subset plus the cheapest fix. This is the tool for "why does this plan
fail" when a violation list is not enough — a pair of limits can conflict jointly while neither
is violated alone. The returned core is **verified** minimal.

Returns `verdict`, `core`, `relaxation`, and the per-constraint propagation.

### `grid_screen_contingencies`

N-1 assessment. Re-solves with each declared branch out of service and classifies each outage
`secure`, `violated`, or `islanded`. Islanding is reported separately from violation because a
split network is a different operational problem from an overload.

### `grid_digest`

The `sha256` content address of a model and of a full study input. Use it to detect that a model
changed between runs, to key a cache, or to prove two studies used identical inputs.

### `list_skills`

The skill catalog with versions and descriptions. Discover the documented workflows before
guessing a command.

### `list_plugins`

The resolved plugin registry, including what was shadowed, disabled or rejected **and why**.

## Input shape

All five analysis tools take the same request:

```json
{
  "model": { "name": "...", "baseMva": 40, "slackBus": "...", "buses": [], "branches": [], "storage": [] },
  "plan": { "intervals": [], "partial": false },
  "constraints": [],
  "outages": []
}
```

`model` and `plan` are required. Everything else defaults: no constraints means nothing to
propagate, no outages means no screen, `budget` 64, `explain` true.

Input is validated **before** the engine is spawned, so a malformed request fails with a
field-level message rather than a Python traceback:

```
VALIDATION: study request is invalid at constraints.0.target: unknown branch "L99"
```

## Design notes

**Stateless.** Every tool is a pure function of its input and the study store. Nothing is
remembered between calls, which is what makes the server safe to share and the tools safe to run
in parallel.

**No duplicated logic.** `tools/list` is derived from the core registry. There is no separate MCP
tool list to drift out of sync. A name MCP cannot carry fails at server construction rather than
silently vanishing from the list.

**Permissions.** Each tool declares what it needs; the server grants the union of the declared
permissions. Running `mcp serve` is an explicit operator action, so a tool is not additionally
blocked for declaring what it requires — but nothing is granted beyond a tool's own declaration,
so a tool can never reach a capability it did not declare. Narrow it with
`PRODUCT_MCP_PERMISSIONS` for a tighter server:

```bash
PRODUCT_MCP_PERMISSIONS=fs:read loadcurve mcp serve
```

**No model call in the analysis path.** The tools that decide admissibility run deterministic
code. See [ADR-0004](adr/0004-no-model-in-the-analysis-path.md).

## Client configuration

```json
{
  "mcpServers": {
    "loadcurve": {
      "command": "loadcurve",
      "args": ["mcp", "serve"],
      "env": { "PYTHON": "/usr/bin/python3" }
    }
  }
}
```

`PYTHON` is optional; the engine uses `python` from `PATH` when it is unset.

## Using it without an MCP client

```bash
loadcurve mcp call grid_digest '{"model": ..., "plan": ...}'
```

Same registry, same validation, no protocol.
