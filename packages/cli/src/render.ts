/**
 * Terminal rendering for study results.
 *
 * Plain text, no colour codes, no box drawing. An operator reads this output in CI logs and
 * pipes it to files, and a renderer that emits ANSI escapes makes both worse. The shape is a
 * fixed-width table plus one paragraph per finding, because the findings *are* the product —
 * a summary line that only said "infeasible" would throw away everything the engine found.
 */
import type {
  ContingencyResult,
  Core,
  PropagationResult,
  QuantitySeries,
  RelaxationPlan,
  StudyResult,
} from '@loadcurveanalyze/engine-model'

const RULE = '-'.repeat(72)

export interface ExplanationOutput {
  readonly verdict: string
  readonly core: Core
  readonly relaxation: RelaxationPlan
  readonly propagation: readonly QuantitySeries[]
}

function table(rows: readonly (readonly string[])[], widths: readonly number[]): string {
  const lines = rows.map((row) =>
    row
      .map((cell, index) => cell.padEnd(widths[index] ?? cell.length))
      .join('  ')
      .trimEnd(),
  )
  return lines.join('\n')
}

function seriesRow(quantity: QuantitySeries): string[] {
  const worst = quantity.excessMw
  const magnitude = worst === 0 ? '-' : `${worst.toFixed(3)} MW`
  return [quantity.constraintId, quantity.kind, quantity.target, quantity.verdict, magnitude]
}

export function renderPropagation(propagation: PropagationResult): string {
  const header = ['CONSTRAINT', 'KIND', 'TARGET', 'VERDICT', 'WORST']
  const widths = [
    Math.max(header[0]!.length, ...propagation.quantities.map((q) => q.constraintId.length)),
    Math.max(header[1]!.length, ...propagation.quantities.map((q) => q.kind.length)),
    Math.max(header[2]!.length, ...propagation.quantities.map((q) => q.target.length)),
    header[3]!.length,
    header[4]!.length,
  ]
  const rows = propagation.quantities.map(seriesRow)
  return [table([header, ...rows], widths), RULE].join('\n')
}

export function renderCore(core: Core): string {
  if (core.feasible) return 'No contradiction: the plan is admissible as declared.'
  const members = core.constraintIds.map((id) => `  - ${id}`).join('\n')
  const proof = core.irredundant
    ? 'verified minimal: removing any one member makes the rest satisfiable'
    : 'NOT verified minimal — treat this as a candidate core'
  return [
    `Minimal unsatisfiable core (${core.constraintIds.length} member(s)):`,
    members,
    `  ${proof} (${core.checks} satisfiability checks)`,
  ].join('\n')
}

export function renderRelaxation(plan: RelaxationPlan): string {
  if (plan.relaxations.length === 0) {
    return plan.feasible ? 'No relaxation required.' : 'No single-bound relaxation resolves this core.'
  }
  const header = ['CONSTRAINT', 'SIDE', 'FROM', 'TO', 'DELTA']
  const widths = [24, 6, 10, 10, 10]
  const rows = plan.relaxations.map((move) => [
    move.constraintId,
    move.side,
    move.fromBound.toFixed(3),
    move.toBound.toFixed(3),
    move.delta.toFixed(3),
  ])
  const optimality = plan.optimal
    ? 'proven minimum total movement'
    : 'best effort — this core was too large to search exhaustively'
  return [
    `Cheapest relaxation (total ${plan.totalDelta.toFixed(3)}, ${optimality}):`,
    table([header, ...rows], widths),
  ].join('\n')
}

export function renderSecurity(contingencies: readonly ContingencyResult[], base: boolean): string {
  if (contingencies.length === 0) return 'No outages declared.'
  const header = ['OUTAGE', 'BRANCH', 'STATUS', 'WORST', 'CORE']
  const widths = [16, 10, 10, 10, 28]
  const rows = contingencies.map((entry) => [
    entry.outageId,
    entry.branchId,
    entry.status,
    entry.worstExcessMw === 0 ? '-' : `${entry.worstExcessMw.toFixed(3)} MW`,
    entry.core.join(', ') || '-',
  ])
  const counts = contingencies.reduce<Record<string, number>>((acc, entry) => {
    acc[entry.status] = (acc[entry.status] ?? 0) + 1
    return acc
  }, {})
  const summary = Object.entries(counts)
    .map(([status, count]) => `${count} ${status}`)
    .join(', ')
  return [
    `Base case: ${base ? 'feasible' : 'infeasible'}. N-1 screen: ${summary}`,
    table([header, ...rows], widths),
  ].join('\n')
}

export function renderStudy(result: StudyResult): string {
  return [
    `Verdict: ${result.verdict}`,
    `Input digest: ${result.inputDigest}`,
    `Engine: ${result.engineVersion}`,
    '',
    renderPropagation(result.propagation),
    renderCore(result.core),
    '',
    renderRelaxation(result.relaxation),
    '',
    renderSecurity(result.security.contingencies, result.security.baseFeasible),
    RULE,
    `Converged: ${result.propagation.fixpoint ? 'yes' : 'NO'} after ${result.propagation.iterations} sweep(s)`,
  ].join('\n')
}

export function renderExplanation(output: ExplanationOutput): string {
  return [renderCore(output.core), '', renderRelaxation(output.relaxation), RULE].join('\n')
}
