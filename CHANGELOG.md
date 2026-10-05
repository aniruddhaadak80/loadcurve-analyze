# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [0.1.0] - 2026-10-05

### Added

- **The deterministic engine** (`services/engine`, Python, zero runtime dependencies):
  - `propagate` — bounds-consistency propagation of hard constraints over bus-injection
    variables to a fixed point, with an interval budget and a three-valued verdict.
  - `minimal_core` — deletion-based extraction of a minimal unsatisfiable subset, verified
    minimal before it is returned.
  - `relaxation` — the exact L1 minimum total bound movement that satisfies a core, by bisection
    per edge plus exhaustive combination search; degrades to a reported best effort above
    14 core members.
  - `contingency` — N-1 screen with `secure` / `violated` / `islanded` reported separately.
  - `digest` — `sha256` content addresses over canonical JSON.
  - Five linear constraint kinds: `line_thermal`, `branch_group`, `poi_export`, `storage_soc`,
    `ramp`.
- **Seven tools** over one registry, reachable from the CLI, the MCP server and the web app:
  `grid_verify_plan`, `grid_propagate`, `grid_explain_infeasibility`,
  `grid_screen_contingencies`, `grid_digest`, `list_skills`, `list_plugins`.
- **CLI**: `verify`, `explain`, `doctor`, `tools`, `mcp serve`, `mcp call`, `version`. Plain-text
  output with no ANSI escapes, and `--json` on every read-only command.
- **MCP server** over stdio, stateless, with the tool list derived from the registry.
- **Web app** (`apps/web`, Next.js): server-rendered study view with the load-staircase data
  treatment, a dense constraint table with server-side inline detail, and three distinct
  loading / empty / error states. Slate + amber, Geist pairing, `slate+amber` token palette.
- **Study store** (`packages/studies`): content-addressed SQLite with WAL, FTS5 search and
  numbered idempotent migrations. A repeat run of unchanged inputs is the same study.
- **Skills catalog**: three grid workflows with frontmatter validation and a CI gate that fails
  when a body changes without a version bump.
- **Quality gates**: `check:skill-version`, `check:no-secrets`, `check:theme-tokens`,
  `check:boundaries`, `check:public-hygiene`, `check:readme-commands`, aggregated as
  `npm run check`.
- **Architecture decision records**: the narrow waist, the Python engine boundary, the
  self-contained web app, and no model call in the analysis path.

### Deliberately omitted

- Desktop / Electron shell, channel adapters, and LLM provider abstractions. Each omission is
  recorded with its reason in the README and on `/surfaces`. See
  [ADR-0004](docs/adr/0004-no-model-in-the-analysis-path.md) for the provider decision.