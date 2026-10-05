# Plugins

A plugin is a directory under `plugins/` containing a `plugin.json` manifest and any code it
needs. This product ships one, as a worked example of the contract.

## Where plugins belong

Per the [footprint ladder](architecture.md#the-footprint-ladder), a plugin is **step 4** —
below a service-gated tool and above a new core tool. Reach for one when the capability is a
genuine extension point: a new _model-format adapter_ is the obvious case, because grid models
arrive in vendor formats and the core has no business knowing them.

If a plugin would be strictly smaller than the core tool surface, the core is the honest place.

## Contract

| Field          | Type     | Rule                                        |
| -------------- | -------- | ------------------------------------------- |
| `name`         | string   | `^[a-z0-9][a-z0-9-]*$`                      |
| `version`      | string   | `^\d+\.\d+\.\d+$`                           |
| `description`  | string   | at least 10 characters                      |
| `enabled`      | boolean  | default `true`                              |
| `priority`     | integer  | 0–100, default 50 — higher wins a conflict  |
| `capabilities` | string[] | what the plugin claims                      |
| `engines`      | record   | required package → acceptable version range |

## The shipped example

```json
{
  "name": "sample",
  "version": "0.1.0",
  "description": "A minimal working plugin that demonstrates the manifest contract.",
  "enabled": true,
  "priority": 50,
  "capabilities": ["sample.echo"],
  "engines": { "@loadcurveanalyze": "0.1.0" }
}
```

## Resolution

Plugins are loaded from `plugins/*/plugin.json` and resolved in a fixed order:

1. **Validation.** A manifest that fails the schema is **rejected with the JSON path of the
   offending field**. A plugin is never skipped silently — a missing capability and a broken
   plugin look identical from the outside otherwise.
2. **Engine ranges.** `engines.<package>` is checked against the actual installed version. A
   mismatch fails loudly, naming the required range and what was found.
3. **Capability conflicts.** Two plugins claiming the same capability resolve by `priority`,
   highest first. Ties break by name so the result is deterministic. The loser is reported as
   `shadowed` rather than dropped.

## Inspecting

```bash
loadcurve tools        # includes list_plugins
```

Over MCP, `list_plugins` returns the active set plus everything that was disabled or rejected
**and why**:

```json
{
  "active": [{ "name": "sample", "version": "0.1.0", "capabilities": ["sample.echo"], "shadowed": false }],
  "disabled": [],
  "rejected": []
}
```

## Authoring

```
plugins/
  my-adapter/
    plugin.json
    index.js
```

The manifest is the whole contract. A plugin registers through the same core registry as
everything else — there is no second registration path, which is the narrow waist doing its job.
See [ADR-0001](adr/0001-narrow-waist.md).
