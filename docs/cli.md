# CLI reference

```bash
loadcurve <command> [options]
```

## Exit codes

| Code | Meaning                                                                                        |
| ---- | ---------------------------------------------------------------------------------------------- |
| `0`  | success                                                                                        |
| `1`  | runtime failure — a check failed, the engine was unreachable, or the verdict is `undetermined` |
| `2`  | usage error — unknown command or flag                                                          |

**A verified-infeasible plan exits `0`.** The engine answered; the answer is in the body.
`infeasible` is a successful analysis, not a failure, and a CI job that greps for the verdict
should not have to distinguish the two.

## `loadcurve verify <study>`

Prove a plan is admissible. `<study>` is a path to a JSON file, or `example`.

| Option         | Effect                                             |
| -------------- | -------------------------------------------------- |
| `--json`       | machine-readable output, including the full result |
| `--budget <n>` | propagation sweep limit (default 64)               |

```bash
loadcurve verify example
loadcurve verify example --json > result.json
loadcurve verify my-study.json --budget 256
```

The output is a verdict, a constraint table, the minimal core, the relaxation plan and the N-1
screen. It is plain text with no ANSI escapes, because it gets read in CI logs and piped to files.

## `loadcurve explain <study>`

The core and the cheapest fix, without the rest. Same arguments as `verify`.

```bash
loadcurve explain example
```

```
Minimal unsatisfiable core (2 member(s)):
  - soc-floor
  - l45-lateral
  verified minimal: removing any one member makes the rest satisfiable (6 satisfiability checks)

Cheapest relaxation (total 0.765, proven minimum total movement):
CONSTRAINT                SIDE    FROM        TO          DELTA
l45-lateral               lower   -1.000      -1.684      0.684
soc-floor                 lower   0.700       0.619       0.081
```

`proven minimum total movement` is a claim the engine verifies by exhaustive search over the
core's bounds. When it says `best effort`, the core was too large to search exhaustively — read
the total as an upper bound, not a minimum.

## `loadcurve doctor`

Probe every subsystem and print a fix hint per failing row.

```bash
loadcurve doctor
loadcurve doctor --json
```

| Check     | What it proves                                             |
| --------- | ---------------------------------------------------------- |
| `node`    | runtime ≥ 22                                               |
| `package` | the workspace resolved                                     |
| `skills`  | the catalog parses and validates                           |
| `plugins` | manifests load and register                                |
| `config`  | `product.config.json` present (WARN if absent)             |
| `engine`  | **the engine actually ran** and returned a content address |
| `tools`   | the registry exposes at least five engine-backed tools     |

## `loadcurve tools`

The authoritative capability list.

```bash
loadcurve tools
loadcurve tools --json
```

Names match `^[a-z][a-z0-9_]*$` so every tool is directly exposable over MCP.

## `loadcurve mcp serve`

Run the MCP server over stdio.

```bash
loadcurve mcp serve
```

stdout belongs to the protocol from this point on; diagnostics go to stderr. See
[MCP](mcp.md).

## `loadcurve mcp call <tool> <json>`

Invoke one tool directly, without MCP. Useful for scripting and for reproducing a client's
behaviour.

```bash
loadcurve mcp call grid_digest '{"model": ..., "plan": ...}'
```

## `loadcurve version`

Version and runtime information as JSON, including the Python the engine will use.

```bash
loadcurve version
```

## Writing a study

See [Getting started](getting-started.md#write-your-own-study) for a minimal example. The five
constraint kinds, and what "per interval" means for each:

| Kind           | `target`          | `members`  | Quantity                          |
| -------------- | ----------------- | ---------- | --------------------------------- |
| `line_thermal` | branch id         | —          | that branch's flow                |
| `branch_group` | label             | branch ids | net flow across them              |
| `poi_export`   | label             | bus ids    | net injection at them             |
| `storage_soc`  | storage id        | —          | state-of-charge fraction          |
| `ramp`         | bus or storage id | —          | change from the previous interval |

Every constraint takes optional `fromInterval` and `toInterval`. Scope a limit to a window when
it binds only part of the horizon — a grid code's "70% by hour 2" is `fromInterval: 1`. Without
it the condition is reported as violated in interval 0, where it does not apply.

Set `plan.partial: true` to mean "a bus absent from an interval is unconstrained" rather than
"not dispatching". Results may then come back `undetermined`, which is the honest answer.

## Troubleshooting

See [Troubleshooting](troubleshooting.md).
