/**
 * The public facade. It re-exports the stable surface and nothing else — if a consumer can
 * reach an internal module from here, a boundary has been broken.
 *
 * Deliberately absent: `channels` and `providers`. This product has no remote surface and no
 * model call in its analysis path — see docs/adr/0004-no-model-in-the-analysis-path.md. A
 * consumer that cannot reach them cannot accidentally depend on them.
 */
export * from '@loadcurveanalyze/core'
export * from '@loadcurveanalyze/skills'
export * from '@loadcurveanalyze/plugins'
export * from '@loadcurveanalyze/memory'
export * from '@loadcurveanalyze/engine-model'
