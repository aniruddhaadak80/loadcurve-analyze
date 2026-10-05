/**
 * `@loadcurveanalyze/studies` — persistence for analysis runs.
 *
 * `canonical.ts` is the part that matters: it is a second implementation of the engine's
 * canonicalisation, and the golden test in `store.test.ts` asserts the two agree. If they ever
 * diverge, re-running an unchanged study stops being idempotent.
 */
export { canonicalize, canonicalJson, contentDigest } from './canonical.js'
export { StudyStore, SCHEMA_VERSION, type StudyRow, type StudySummary } from './store.js'
