# ADR 0004 — No model call in the analysis path

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

This product is an agent product: it ships an MCP server, a skills catalog, and instructions an
agent follows. It is entirely reasonable to reach for a model when composing a study — to
translate "this battery needs to be 70% charged by hour two" into a JSON request, or to explain a
result in prose.

There is a line here, and this ADR is about where it is.

## Decision

**No model call anywhere in the analysis path.** Not as a default, and not "we prefer
determinism" — structurally. There is no provider abstraction in the tree to reach for.

Concretely:

| Concern                      | Owner                                                    |
| ---------------------------- | -------------------------------------------------------- |
| Interpreting a study request | a human, or an agent using `list_skills`                 |
| Deciding admissibility       | `propagate`, `minimal_core`, `relaxation`, `contingency` |
| Choosing a relaxation        | exhaustive search over bound movements                   |
| The numbers in a filing      | deterministic code                                       |

Model calls remain legitimate _outside_ that path — an agent may use one to decide which tool to
call, and a UI may use one to phrase prose. Neither touches a number.

## Why

**Reproducibility.** An interconnection study is a document that gets filed. Someone will ask
"what did this say in March?" and the answer has to be the same today. A sampled response cannot
be that answer, and "the model was probably consistent" is not a property an engineer can put in
front of a regulator.

**The core claim is a proof.** `grid_verify_plan` returns `infeasible` when propagation drove a
variable domain to empty, and a core that has been _verified_ minimal by removing each member and
re-checking. That is a mathematical claim. A plausible-looking list of constraints cannot
support it, and calling a model on that path would mean the word "proof" describes an
approximation.

**Correctness is decidable here.** Every quantity is a linear form over bus injections, so the
attainable range is computed exactly by interval arithmetic. There is no judgement call for a
model to make better — only arithmetic to get right. Using a model would replace a correct
calculation with an approximation of a correct calculation.

## Consequences

**The core is small and pure.** That is the cost, and it is a real one: the tool cannot infer
constraints from prose. An agent must compose the request, and `list_skills` exists to tell it
how. That is the correct division of labour — the agent decides _what to check_, the code decides
_whether it holds_.

**The relaxation search is exponential in principle.** Bounded at 14 core members, beyond which it
reports `optimal: false` rather than pretending. A model would have "handled" that case by
guessing. Reporting the limit is more useful than a confident wrong answer.

**If a future feature needs a model** — natural-language study authoring, say — it belongs at the
edge, before the request is built, and its output must be schema-validated into the same
`StudyRequest` this product already accepts. Adding it means adding a package, not editing the
engine.
