# Configuration

Layered, later wins:

```
defaults  →  product.config.json  →  environment
```

The zod schema in `packages/config/src/schema.ts` is the **single source of truth**. Any settings
UI derives its form from `z.toJSONSchema()` — that JSON Schema is never hand-written, so the two
cannot drift.

## Keys

| Key                | Type                                    | Default       | Meaning                                  |
| ------------------ | --------------------------------------- | ------------- | ---------------------------------------- |
| `productEnv`       | `development` \| `test` \| `production` | `development` | which environment is running             |
| `dataDir`          | string                                  | `.data`       | where the study store keeps its database |
| `engine.python`    | string                                  | `python`      | interpreter used to spawn the engine     |
| `engine.timeoutMs` | integer 1–120000                        | `30000`       | subprocess timeout                       |
| `engine.budget`    | integer 1–4096                          | `64`          | propagation sweep ceiling                |
| `logLevel`         | `debug` \| `info` \| `warn` \| `error`  | `info`        | diagnostic verbosity                     |

There is deliberately **no `providers` or `channels` block**. Those surfaces were omitted — see
[ADR-0004](adr/0004-no-model-in-the-analysis-path.md) — and a config key for a capability that
does not exist is a promise the product does not keep.

## Environment overrides

| Variable                  | Overrides                                          |
| ------------------------- | -------------------------------------------------- |
| `PRODUCT_DATA_DIR`        | `dataDir`                                          |
| `PYTHON`                  | `engine.python`                                    |
| `PRODUCT_LOG_LEVEL`       | `logLevel`                                         |
| `PRODUCT_MCP_PERMISSIONS` | comma-separated permission ceiling for `mcp serve` |

`PYTHON` matters most in practice: it is how the same CLI works against a virtualenv without a
config file, which is how a grid engineer actually runs it. It takes precedence over
`engine.python`.

## Creating one

```bash
cp product.config.json.example product.config.json
```

`loadcurve doctor` reports `WARN` when it is absent and `PASS` when present — the product runs
correctly on defaults, so absence is a warning rather than a failure.

## The study store

`dataDir` holds the SQLite database of past studies, keyed by content address. Because the key
_is_ the content address, a re-run of unchanged inputs updates one row and increments a run count
rather than creating a duplicate — so this database grows with distinct studies, not with
activity.

Deleting it loses history and nothing else. Studies are reproducible from their inputs and the
deterministic engine.

## No secrets

There is nothing secret in this configuration. The product makes no network calls to third
parties, holds no credentials, and spawns one local subprocess. `.env.example` is committed with
empty values and `check:no-secrets` fails the build on anything that looks like a credential.
