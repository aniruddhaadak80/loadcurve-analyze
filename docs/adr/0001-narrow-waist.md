# ADR 0001 — The narrow waist

**Status:** accepted · **Date:** 2026-10-05

## Context

This product has four front-ends: a CLI, an MCP server, a web app, and a set of skills that
instruct agents how to use it. Each could reasonably grow its own way of performing an analysis.

That is the failure mode worth designing against. Once `loadcurve verify` and the MCP
`grid_verify_plan` tool each hold their own copy of how a study is assembled, the two drift. The
drift is subtle — it shows up as "the CLI says feasible, the agent says infeasible" — and it is
discovered by a user, not by CI.

## Decision

**Every capability is a `Tool`, registered in exactly one registry. Surfaces are transports.**

```ts
interface Tool<I, O> {
  name: string
  description: string
  inputSchema: JsonSchema
  outputSchema: JsonSchema
  permissions: readonly Permission[]
  surface: 'core' | 'plugin' | 'mcp'
  handler: (input: I, ctx: ToolContext) => Promise<O>
}
```

Three properties make the waist hold, and all three are enforced rather than requested:

1. **Tools are stateless.** State lives in `packages/studies` or arrives in the context. A tool
   that remembered something between calls could not be exposed over MCP, where tools _must_ be
   stateless.
2. **Input is validated before the handler runs.** Not "the handler validates" — validated at the
   boundary, so an MCP client and the CLI cannot reach different code with different assumptions.
3. **Permissions are declared, not assumed.** A tool says what it needs; `invoke` refuses before
   the handler runs if the grant is missing. `loadcurve doctor` cross-checks the declaration.

A duplicate registration is a hard error naming both sources. A silently replaced tool is an
undebuggable product bug, so the registry refuses it.

## Consequences

**Adding a capability means adding one tool.** It becomes reachable from all four surfaces at
once, because they all call `buildToolRegistry`. There is no "also add it to the MCP server" step
that can be forgotten.

**The engine sits below the waist, not inside it.** Every surface reaches the Python engine
through one `EngineClient`. The CLI has no private path to it, and neither does the web app.

**The MCP server contains no domain logic.** It converts JSON Schema to MCP descriptors and
errors to the MCP error envelope. `tools/list` is derived from the registry, and a name MCP
cannot carry fails at construction rather than silently disappearing from the list.

**The cost is that `packages/tools` imports the engine client.** A tool that needs the engine
therefore cannot run in a context without Python — which is exactly why `apps/web` carries a
recorded result and labels it as recorded. See
[ADR-0003](0003-web-app-self-contained.md).

## Alternatives considered

**A service layer with per-surface wrappers.** Rejected: the wrappers _are_ the drift.

**Protocol-first design** (define the MCP tool surface, generate everything else from it).
Rejected: it makes MCP the primary interface, and this product is CLI-first. The registry is the
more neutral abstraction.
