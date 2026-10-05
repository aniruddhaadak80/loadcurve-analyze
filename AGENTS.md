# AGENTS.md

A **router**, not a manual. Read the file that owns the area before changing it.

| Area                                          | Read first                                                                              |
| --------------------------------------------- | --------------------------------------------------------------------------------------- |
| **the product's capabilities**                | `packages/tools/src/registry.ts` — the seven tools                                      |
| tool interface, registry, permissions, errors | `packages/core/src/`                                                                    |
| the engine's I/O contract (zod mirror)        | `packages/engine-model/src/index.ts`                                                    |
| the subprocess boundary                       | `packages/engine-client/src/bridge.ts`                                                  |
| the deterministic operations                  | `services/engine/src/loadcurve_analyze/`                                                |
| content addressing                            | `packages/studies/src/canonical.ts` + `services/engine/src/loadcurve_analyze/digest.py` |
| study storage, migrations                     | `packages/studies/src/store.ts`                                                         |
| configuration schema                          | `packages/config/src/schema.ts`                                                         |
| skill format and authoring rules              | `skills/AGENTS.md`                                                                      |
| plugin manifest contract                      | `docs/plugins.md`                                                                       |
| MCP surface and tool naming                   | `docs/mcp.md`                                                                           |
| CLI commands and rendering                    | `packages/cli/src/program.ts`, `render.ts`                                              |
| the web app and design tokens                 | `apps/web/styles/tokens.css`                                                            |
| CI jobs and gates                             | `docs/ci.md`                                                                            |
| architectural decisions                       | `docs/adr/`                                                                             |

## Hard rules

1. **The narrow waist holds.** One registry, one `Tool` interface. A surface is a transport,
   never a second implementation. A second code path is a bug even when it works.
2. **The footprint ladder is binding.** Extend an existing tool → CLI command + skill →
   service-gated tool → plugin → MCP tool → new core tool. Core is last, not first.
3. **No cross-package deep imports.** Only declared entry points. `check:boundaries` fails
   otherwise.
4. **Tokens only in `apps/web`.** No raw colour literal outside `styles/tokens.css`.
5. **Never edit a version in a PR.** The release workflow owns version bumps.
6. **Never edit an applied migration.** Append a new one.
7. **The engine is pure.** No clock, no network, no randomness, no filesystem — and **no model
   call anywhere in the analysis path** (ADR-0004).
8. **Bump `metadata.version` on any `SKILL.md` body change.**
9. **Keep the two canonicalisers in agreement.** Python's `digest.py` and TypeScript's
   `canonical.ts` must produce the same address for the same input. A test asserts it; if you
   change one, change both and re-run it.
10. **Run the full gate before claiming done:** `npm run check`.

## The footprint ladder

In order of preference. Adding a core tool is **last, not first**.

1. Extend an existing tool in `packages/tools/src/registry.ts`
2. New CLI command + a matching skill in `skills/`
3. Service-gated tool — one that needs the engine subprocess
4. Plugin — a model-format adapter, under `plugins/`
5. New MCP server tool (almost always free: MCP derives its list from the registry)
6. New core tool — last resort

Adding a tool to `packages/tools` makes it reachable from the CLI, MCP and the web API at once,
so there is no "and also add it to the server" step that can be forgotten.

## The engine's invariants

These are the properties the product's credibility rests on. Breaking one silently turns a proof
into an estimate.

- **Everything is linear.** Every constraint is a linear form over bus injections, so the
  attainable range is _computed_, not bounded. If you add a constraint kind, keep it linear — a
  nonlinear form makes the propagation conservative and the `minimal_core` claim unsound.
- **Propagate, do not check.** Constraints narrow variable domains. Checking them independently
  makes every infeasibility a singleton core, which proves nothing.
- **`minimal_core` is verified minimal** before it is returned. Do not weaken that to a
  best-effort path; report `irredundant: false` instead.
- **Relaxation is an L1 minimum** when `optimal: true`. Above 14 core members it degrades and
  says so.
- **Verdicts are three-valued.** `undetermined` is an answer, not a failure.
- **Bit-reproducible.** Only `+ - * /` on the bound path. No transcendental may perturb a study.

## Structural limits

A file over ~2000 lines, a function over ~300 lines, or a cyclomatic complexity over 30 is a
defect, not a style preference. Split it.

## Definition of done

- [ ] `npm run check` exits 0
- [ ] tests cover the failure path, not only the happy path
- [ ] `python -m pytest services/engine -q` exits 0
- [ ] `python -m mypy --strict services/engine/src` is clean
- [ ] `CHANGELOG.md` has an `Unreleased` entry
- [ ] any user-visible change has a docs update (see the table in `docs/notes/`)

<!-- BEGIN:turborepo-agent-rules -->

# This is NOT the Turborepo you know

Turborepo configuration, task behavior, and CLI commands can vary between installed versions and may differ from your training data. Resolve the `turbo` package from this file's directory or relevant workspace; in monorepos, it may not be visible from the repository root. For example, run `node -p "require.resolve('turbo/package.json')"` from a workspace that depends on `turbo`.

Read `docs/README.md` inside that installed package first, then read the relevant pages from its `docs/` directory before changing Turborepo configuration or commands. Heed deprecation notices. These bundled docs match the installed package version and are available without network access.

This block is written and re-added by `turbo` before repository-scoped commands when an AI agent is detected. In the Turborepo source repository, its template is defined in `crates/turborepo-cli/src/cli/agent_guidance.rs`. Removing the managed block while updates are enabled means a later qualifying invocation will add it again. Set `"agentGuidance": false` in the root `turbo.json` or `turbo.jsonc` to opt out; this does not remove an existing block. Keep the block committed with your work to avoid an uncommitted change on the next agent invocation.
<!-- END:turborepo-agent-rules -->
