# Skills

A skill is markdown instructions for an agent, loaded from disk at runtime. This product ships
three, one per workflow.

## The catalog

| Skill                                                                 | Use it when                                        |
| --------------------------------------------------------------------- | -------------------------------------------------- |
| [`screen-dispatch-plan`](../skills/screen-dispatch-plan/SKILL.md)     | a plan must be proven admissible before committing |
| [`diagnose-infeasibility`](../skills/diagnose-infeasibility/SKILL.md) | a plan failed and you need the responsible pair    |
| [`assess-n1-security`](../skills/assess-n1-security/SKILL.md)         | a plan must survive a single-element outage        |

## Layout

```
skills/
  ATTRIBUTION.md          provenance for anything adapted from elsewhere
  AGENTS.md              the authoring standard
  <skill-name>/
    SKILL.md
```

## Frontmatter

```yaml
---
name: example-skill
description: Use when the user asks to <specific thing>, because <reason>.
metadata:
  version: 1.0.0
---
```

Validation is enforced by `packages/skills`:

- `name` is kebab-case and **unique** across the catalog
- `description` exists — and says _when to use_, not what the skill is
- `metadata.version` is valid semver
- YAML is parsed with a real parser, never a regex; malformed YAML is reported with the file
  and the offending line

## The version gate

`npm run check:skill-version` fails when a `SKILL.md` body changes without a
`metadata.version` bump.

```console
$ npm run check:skill-version
skills/diagnose-infeasibility/SKILL.md: body changed but metadata.version is still 1.0.0
  bump it to 1.1.0 (or higher) — an unbumped skill is an update users never receive
```

This is the one gate in the repository that earns its place by preventing a specific, quiet
failure: skills ship into _users' agent directories_, where an unversioned change is never
delivered.

## Discovery

```bash
loadcurve tools          # includes list_skills
```

Over MCP, `list_skills` returns name, version, description, and optionally the full body:

```json
{ "includeBodies": true }
```

## Authoring

The standard is in [`skills/AGENTS.md`](../skills/AGENTS.md). The short version: write
instructions to an agent in second person and numbered steps, name exact commands, and state
what _not_ to do. A skill that only says what to do leaves the agent to invent the failure modes.

Provenance matters: anything adapted from another project declares `metadata.upstream*` and gets
a row in [`skills/ATTRIBUTION.md`](../skills/ATTRIBUTION.md). Nothing in this catalog is adapted
from elsewhere today.
