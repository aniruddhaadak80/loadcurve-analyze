/**
 * Types and view helpers for the study view.
 *
 * Re-exported from `@loadcurveanalyze/engine-model` rather than re-declared, so the web app
 * cannot drift from the engine's contract. Only presentation-shaped helpers live here.
 */
export type {
  StudyResult,
  QuantitySeries,
  PropagationResult,
  Core,
  RelaxationPlan,
  SecurityReport,
  ContingencyResult,
  Verdict,
} from '@loadcurveanalyze/engine-model'

export type VerdictTone = 'ok' | 'warn' | 'danger'

export function toneFor(verdict: string): VerdictTone {
  if (verdict === 'feasible') return 'ok'
  if (verdict === 'undetermined') return 'warn'
  return 'danger'
}

export function shortDigest(digest: string): string {
  const hex = digest.replace(/^sha256:/, '')
  return `${hex.slice(0, 12)}…${hex.slice(-6)}`
}
