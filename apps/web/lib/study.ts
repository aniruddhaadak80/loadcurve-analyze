/**
 * The engine's result shapes, as types only.
 *
 * The deployed web app is a **standalone Vercel project** — `vercel --prod` runs from
 * `apps/web`, outside the npm workspace, so it cannot import a workspace package. This file is
 * therefore a hand-maintained mirror of `packages/engine-model`'s response types rather than a
 * re-export.
 *
 * That mirror is the cost of the deployment boundary, and it is why this app never *computes* a
 * study: it renders `recorded-study.json`, produced by the real engine and asserted against the
 * real schema by `packages/engine-model`'s test. The types here are the app's view of that file;
 * the schema that validates it lives with the contract it belongs to.
 */
export type Verdict = 'feasible' | 'infeasible' | 'undetermined'
export type ConstraintVerdict = 'satisfied' | 'violated' | 'undetermined'
export type OutageStatus = 'secure' | 'violated' | 'islanded'

export interface QuantityPoint {
  readonly interval: number
  readonly hours: number
  readonly lower: number
  readonly upper: number
  readonly excessMw: number
}

export interface QuantitySeries {
  readonly constraintId: string
  readonly kind: string
  readonly target: string
  readonly label: string
  readonly lower: number
  readonly upper: number
  readonly verdict: ConstraintVerdict
  readonly excessMw: number
  readonly series: readonly QuantityPoint[]
  readonly violations: readonly number[]
}

export interface PropagationResult {
  readonly intervals: number
  readonly fixpoint: boolean
  readonly iterations: number
  readonly verdict: Verdict
  readonly feasible: boolean
  readonly quantities: readonly QuantitySeries[]
  readonly violations: readonly string[]
}

export interface Core {
  readonly feasible: boolean
  readonly constraintIds: readonly string[]
  readonly irredundant: boolean
  readonly checks: number
}

export interface Relaxation {
  readonly constraintId: string
  readonly side: 'lower' | 'upper'
  readonly fromBound: number
  readonly toBound: number
  readonly delta: number
}

export interface RelaxationPlan {
  readonly feasible: boolean
  readonly optimal: boolean
  readonly totalDelta: number
  readonly relaxations: readonly Relaxation[]
  readonly combinations: number
}

export interface ContingencyResult {
  readonly outageId: string
  readonly branchId: string
  readonly label: string
  readonly status: OutageStatus
  readonly violations: readonly string[]
  readonly core: readonly string[]
  readonly worstExcessMw: number
}

export interface SecurityReport {
  readonly baseFeasible: boolean
  readonly contingencies: readonly ContingencyResult[]
  readonly secure: number
  readonly violated: number
  readonly islanded: number
}

export interface StudyResult {
  readonly inputDigest: string
  readonly engineVersion: string
  readonly propagation: PropagationResult
  readonly core: Core
  readonly relaxation: RelaxationPlan
  readonly security: SecurityReport
  readonly verdict: Verdict
}

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
