# Troubleshooting

## `doctor` reports a failing row

Read the **fix** line under it — `doctor` names the remedy rather than only the status.

```bash
loadcurve doctor
```

### `[FAIL] engine  —  check that python 3.11+ is on PATH, or set PYTHON=/path/to/python`

`doctor` does not check that a binary exists; it runs the engine. So this row means the engine
genuinely failed. In order of likelihood:

1. **Python too old.** `python --version` must be ≥ 3.11.
2. **Wrong interpreter.** Point at it explicitly:
   ```bash
   PYTHON=/path/to/venv/bin/python loadcurve doctor
   ```
3. **Missing dependency.** The engine has _zero_ runtime dependencies, so a fresh interpreter
   should work. Verify:
   ```bash
   python -m pytest services/engine -q
   ```

### `[FAIL] skills` — a `SKILL.md` is invalid

`loadcurve tools --json` lists the issues with the file and line. The rules are in
[`skills/AGENTS.md`](../skills/AGENTS.md): unique kebab-case name, a `description`, and a valid
`metadata.version`.

### `[FAIL] tools` — fewer than five engine-backed tools

The registry did not build. Run `npm run build` — `packages/tools` compiles to `dist/`, and the
CLI loads the built output.

## A gate fails

```bash
npm run check          # the aggregate, same order as CI
```

Policy gates run before the expensive ones, so a bad hex literal fails in milliseconds rather
than after a build.

### `check:theme-tokens`

A raw colour literal appeared outside `apps/web/styles/tokens.css`. Add the colour **to
`tokens.css`** — do not inline it. The gate exists to stop the codebase drifting into forty
slightly different greys.

### `check:no-secrets`

Something resembling a credential was committed. `.env` files must be `.env.example` with empty
values. `*.pem`, `*.key`, `id_rsa`, `ghp_`, `github_pat_`, `sk-` and `xox[baprs]-` are all
detected.

### `check:public-hygiene`

A `*.log`, `.DS_Store`, `Thumbs.db`, `__pycache__/`, `.pytest_cache/`, a nested `node_modules/`,
or a file over 1 MB got committed. Delete it and check `.gitignore`.

### `check:boundaries`

A package imported another package's deep path. Import the declared entry point:

```ts
import { Tool } from '@loadcurveanalyze/core' // fine
import { registry } from '@loadcurveanalyze/core/src/registry.js' // violation
```

### `check:readme-commands`

A fenced command in the README is not a real script or binary. Every command in this README was
run before it was written; the gate keeps that true.

### `check:skill-version`

A `SKILL.md` body changed without a `metadata.version` bump. Skills ship into users' agent
directories, so an unbumped change is an update nobody receives. Bump the version.

## The engine misbehaves

### `UNDETERMINED` when you expected a verdict

Your plan sets `"partial": true`, which means a bus absent from an interval is _unconstrained_.
With an unbounded variable no conclusion is possible, and the engine says so rather than guessing.

Either declare the bus in every interval, or drop `partial` — its default meaning is that an
absent bus is not dispatching, which is usually what you want.

### A violation reported in an interval where the rule does not apply

The constraint needs a window. A grid code's "70% charged by hour 2" is `fromInterval: 1`:

```json
{ "id": "soc-floor", "kind": "storage_soc", "target": "BESS1", "lower": 0.7, "fromInterval": 1 }
```

Without it the condition is evaluated in interval 0 and reported as violated there.

### Every outage reports `islanded`

Your model is a radial lateral. Dropping any branch splits it, so no DC power flow exists — which
is reported as its own status because a split network is a different problem from an overload.
If you meant to test security, close the ring.

### A `SINGULAR_MATRIX` or `ISLANDED` error

The in-service branches do not form a connected network. The engine raises rather than returning
zeros, because a singular admittance matrix is a modelling error worth seeing.

### The engine times out

Raise the budget, or reduce the work:

```bash
loadcurve verify my-study.json --budget 256
```

If it is the N-1 screen, drop `"explain": false` — core extraction per violated outage is the
expensive part.

## The web app

### The deployed page shows a recorded result

Expected. Vercel has no Python runtime, so `apps/web` renders
`apps/web/lib/recorded-study.json` and **says so in the section heading**. See
[ADR-0003](adr/0003-web-app-self-contained.md).

If you changed `EXAMPLE_REQUEST`, re-record:

```bash
node scripts/record-study.mjs
```

A test asserts the recorded digest matches a live engine run, so a stale file fails CI.

### The page streams a skeleton forever

`dynamic = 'force-dynamic'` is missing from `app/page.tsx`. Without it Next prerenders a route
whose entire content is a subprocess call and ships the skeleton to production.

### `Failed to patch lockfile` during `next build`

Next walks up looking for a lockfile and finds a `yarn.lock` vendored inside a dependency, then
shells out to yarn. `apps/web/next.config.mjs` sets `NEXT_IGNORE_INCORRECT_LOCKFILE` for exactly
this reason; check it survived your edit.

## Still stuck

Open an issue with the output of `loadcurve doctor`, `loadcurve verify <study> --json`, and the
full text of the failing gate.
