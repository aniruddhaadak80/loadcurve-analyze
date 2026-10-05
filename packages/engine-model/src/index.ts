/**
 * The engine's I/O contract, mirrored in TypeScript.
 *
 * The Python side declares these shapes as `TypedDict`s. That pairing is only worth
 * anything if something checks the two against each other, so this package is the schema of
 * record for the boundary: every tool validates its input with `StudyRequestSchema` before
 * the subprocess is spawned, and the engine's output is parsed with the response schemas
 * before it reaches a surface.
 *
 * When the engine changes a field, this file is where the TypeScript compiler finds out —
 * which is the point. A drift that would otherwise surface as `undefined` at runtime fails
 * at build time instead.
 *
 * Constraint kinds and their semantics are documented on `ConstraintSchema`, because the
 * kind determines which members are meaningful and a caller that guesses produces a
 * constraint the engine will accept and reason about wrongly.
 */
import { z } from 'zod'

/** Float in MW or per-unit. Finite by construction — the engine rejects non-finite bounds. */
const mw = z.number().finite()
const fraction = z.number().finite()

export const BusSchema = z.object({
  id: z.string().min(1),
  baseKv: z.number().positive(),
})
export type Bus = z.infer<typeof BusSchema>

export const BranchSchema = z.object({
  id: z.string().min(1),
  fromBus: z.string().min(1),
  toBus: z.string().min(1),
  reactancePu: z.number().refine((v) => v !== 0, { message: 'reactance must be non-zero' }),
  ratingMw: z.number().positive(),
})
export type Branch = z.infer<typeof BranchSchema>

export const StorageSchema = z.object({
  id: z.string().min(1),
  bus: z.string().min(1),
  chargeMwMax: mw,
  dischargeMwMax: mw,
  energyMwh: z.number().positive(),
  socFracMin: fraction.min(0).max(1),
  socFracMax: fraction.min(0).max(1),
  socFracInitial: fraction.min(0).max(1),
  efficiency: z.number().gt(0).max(1),
})
export type Storage = z.infer<typeof StorageSchema>

export const NetworkModelSchema = z.object({
  name: z.string().min(1),
  baseMva: z.number().positive(),
  slackBus: z.string().min(1),
  buses: z.array(BusSchema).min(2),
  branches: z.array(BranchSchema).min(1),
  storage: z.array(StorageSchema).default([]),
})
export type NetworkModel = z.infer<typeof NetworkModelSchema>

export const InjectionSchema = z.object({
  lowerMw: mw,
  upperMw: mw,
})
export type Injection = z.infer<typeof InjectionSchema>

export const IntervalInjectionsSchema = z.object({
  hours: z.number().positive(),
  buses: z.record(z.string(), InjectionSchema),
})
export type IntervalInjections = z.infer<typeof IntervalInjectionsSchema>

export const DispatchPlanSchema = z.object({
  intervals: z.array(IntervalInjectionsSchema).min(1),
  /**
   * When true, a bus absent from an interval is unconstrained and any constraint touching it
   * is reported `undetermined`. When false (the default) an absent bus is pinned to zero —
   * the usual reading of a plan, which states what will happen.
   */
  partial: z.boolean().default(false),
})
export type DispatchPlan = z.infer<typeof DispatchPlanSchema>

/**
 * The five decidable constraint kinds.
 *
 * - `line_thermal`  two-sided limit on one branch's flow. `target` is a branch id; `members`
 *   must be empty. Omitted bounds default to the branch's own ±rating.
 * - `branch_group` net limit across a set of branches — a transformer bank or an intertie.
 *   `members` are branch ids.
 * - `poi_export`   net injection cap over a set of buses — a DER export limit at the point of
 *   interconnection. `members` are bus ids.
 * - `storage_soc`  state-of-charge envelope for one unit. `target` is a storage id. The
 *   quantity at interval *i* is `soc_0 + sum_{j<i} eff * P_j * hours_j / energy`, which is
 *   what couples storage limits to the thermal limits upstream of it.
 * - `ramp`          per-interval change limit. `target` is a bus or a storage id.
 */
export const CONSTRAINT_KINDS = ['line_thermal', 'branch_group', 'poi_export', 'storage_soc', 'ramp'] as const

export const ConstraintKindSchema = z.enum(CONSTRAINT_KINDS)
export type ConstraintKind = z.infer<typeof ConstraintKindSchema>

/**
 * One hard constraint.
 *
 * Note what is *not* validated here: whether the constraint references a branch or bus that
 * exists, and whether `members` is non-empty for the group kinds. Those checks need the model,
 * and duplicating them in TypeScript would create a second source of truth that drifts from
 * the engine's own validation. The engine rejects them with a specific code; the boundary here
 * catches shape errors, and the engine catches semantic ones.
 */
export const ConstraintSchema = z.object({
  id: z.string().min(1),
  kind: ConstraintKindSchema,
  target: z.string().min(1),
  label: z.string().default(''),
  members: z.array(z.string()).default([]),
  /**
   * Omitted on a `line_thermal` constraint means "inherit the branch's own ±rating", which the
   * engine applies. Omitted on every other kind is an unbounded band, which is not decidable —
   * so it is rejected here rather than producing a constraint the engine cannot reason about.
   */
  lower: mw.nullish(),
  upper: mw.nullish(),
  enabled: z.boolean().default(true),
  /** Interval window this applies to; defaults to the whole horizon. */
  fromInterval: z.number().int().min(0).default(0),
  toInterval: z.number().int().min(0).nullish(),
})
export type Constraint = z.infer<typeof ConstraintSchema>

export const OutageSchema = z.object({
  id: z.string().min(1),
  branchId: z.string().min(1),
  label: z.string().default(''),
})
export type Outage = z.infer<typeof OutageSchema>

/**
 * A whole study request.
 *
 * The cross-field refinement applies the same `line_thermal` default the engine applies —
 * an omitted bound inherits the branch's own ±rating — so a caller who omits it gets the same
 * constraint on this side as the engine would compute. Every other kind must state at least
 * one bound, because an unbounded band is not decidable.
 */
export const StudyRequestSchema = z
  .object({
    model: NetworkModelSchema,
    plan: DispatchPlanSchema,
    constraints: z.array(ConstraintSchema).default([]),
    outages: z.array(OutageSchema).default([]),
    budget: z.number().int().min(1).max(4096).default(64),
    explain: z.boolean().default(true),
  })
  .superRefine((request, ctx) => {
    const ratings = new Map(request.model.branches.map((branch) => [branch.id, branch.ratingMw]))
    request.constraints.forEach((constraint, index) => {
      const hasLower = constraint.lower !== null && constraint.lower !== undefined
      const hasUpper = constraint.upper !== null && constraint.upper !== undefined
      if (hasLower || hasUpper) return
      if (constraint.kind === 'line_thermal') return
      ctx.addIssue({
        code: 'custom',
        path: ['constraints', index],
        message: 'a constraint needs at least one of lower or upper; an unbounded band is not decidable',
      })
    })
    // A referenced branch must exist, so a typo fails with the constraint id in the message
    // rather than as an opaque engine error later.
    request.constraints.forEach((constraint, index) => {
      if (constraint.kind !== 'line_thermal') return
      if (!ratings.has(constraint.target)) {
        ctx.addIssue({
          code: 'custom',
          path: ['constraints', index, 'target'],
          message: `unknown branch ${JSON.stringify(constraint.target)}`,
        })
      }
    })
  })
export type StudyRequest = z.infer<typeof StudyRequestSchema>

// ---------------------------------------------------------------- results

/** Three-valued on purpose. `undetermined` is not a failure mode, it is an honest "no". */
export const VerdictSchema = z.enum(['feasible', 'infeasible', 'undetermined'])
export type Verdict = z.infer<typeof VerdictSchema>

export const QuantityPointSchema = z.object({
  interval: z.number().int(),
  hours: z.number(),
  lower: z.number(),
  upper: z.number(),
  excessMw: z.number(),
})
export type QuantityPoint = z.infer<typeof QuantityPointSchema>

export const QuantitySeriesSchema = z.object({
  constraintId: z.string(),
  kind: z.string(),
  target: z.string(),
  label: z.string(),
  lower: z.number(),
  upper: z.number(),
  verdict: z.enum(['satisfied', 'violated', 'undetermined']),
  excessMw: z.number(),
  series: z.array(QuantityPointSchema),
  violations: z.array(z.number().int()),
})
export type QuantitySeries = z.infer<typeof QuantitySeriesSchema>

export const VariableReportSchema = z.object({
  id: z.string(),
  interval: z.number().int(),
  bus: z.string(),
  lower: z.number(),
  upper: z.number(),
  unbounded: z.boolean(),
  narrowedBy: z.array(z.string()),
})
export type VariableReport = z.infer<typeof VariableReportSchema>

export const PropagationResultSchema = z.object({
  intervals: z.number().int(),
  fixpoint: z.boolean(),
  iterations: z.number().int(),
  verdict: VerdictSchema,
  feasible: z.boolean(),
  quantities: z.array(QuantitySeriesSchema),
  violations: z.array(z.string()),
  variables: z.array(VariableReportSchema),
})
export type PropagationResult = z.infer<typeof PropagationResultSchema>

export const CoreSchema = z.object({
  feasible: z.boolean(),
  constraintIds: z.array(z.string()),
  /** Verified minimal by the engine, not merely asserted. */
  irredundant: z.boolean(),
  checks: z.number().int(),
})
export type Core = z.infer<typeof CoreSchema>

export const RelaxationSchema = z.object({
  constraintId: z.string(),
  side: z.enum(['lower', 'upper']),
  fromBound: z.number(),
  toBound: z.number(),
  delta: z.number(),
})
export type Relaxation = z.infer<typeof RelaxationSchema>

export const RelaxationPlanSchema = z.object({
  feasible: z.boolean(),
  /** False means a best effort the engine could not prove minimal. */
  optimal: z.boolean(),
  totalDelta: z.number(),
  relaxations: z.array(RelaxationSchema),
  combinations: z.number().int(),
})
export type RelaxationPlan = z.infer<typeof RelaxationPlanSchema>

export const ContingencyResultSchema = z.object({
  outageId: z.string(),
  branchId: z.string(),
  label: z.string(),
  status: z.enum(['secure', 'violated', 'islanded']),
  violations: z.array(z.string()),
  core: z.array(z.string()),
  worstExcessMw: z.number(),
})
export type ContingencyResult = z.infer<typeof ContingencyResultSchema>

export const SecurityReportSchema = z.object({
  baseFeasible: z.boolean(),
  contingencies: z.array(ContingencyResultSchema),
  secure: z.number().int(),
  violated: z.number().int(),
  islanded: z.number().int(),
})
export type SecurityReport = z.infer<typeof SecurityReportSchema>

export const StudyResultSchema = z.object({
  inputDigest: z.string(),
  engineVersion: z.string(),
  propagation: PropagationResultSchema,
  core: CoreSchema,
  relaxation: RelaxationPlanSchema,
  security: SecurityReportSchema,
  verdict: VerdictSchema,
})
export type StudyResult = z.infer<typeof StudyResultSchema>

export const DigestResultSchema = z.object({
  modelDigest: z.string(),
  studyDigest: z.string(),
})
export type DigestResult = z.infer<typeof DigestResultSchema>

/** The operation names the engine exposes. Exhaustive so a rename cannot drift silently. */
export const OPERATIONS = [
  'study',
  'propagate',
  'minimal_core',
  'relaxation',
  'contingency',
  'digest',
] as const
export type Operation = (typeof OPERATIONS)[number]

/**
 * The response envelope, per operation.
 *
 * Keyed by operation so the caller cannot parse a `Core` as a `PropagationResult` and get
 * `undefined` where a number belongs.
 */
export const RESPONSE_SCHEMAS = {
  study: StudyResultSchema,
  propagate: PropagationResultSchema,
  minimal_core: CoreSchema,
  relaxation: RelaxationPlanSchema,
  contingency: SecurityReportSchema,
  digest: DigestResultSchema,
} as const satisfies Record<Operation, z.ZodType>

export const EngineEnvelopeSchema = z.object({
  ok: z.boolean(),
  value: z.unknown().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
    })
    .optional(),
  durationMs: z.number(),
})
export type EngineEnvelope = z.infer<typeof EngineEnvelopeSchema>

export const ENGINE_MODULE = 'loadcurve_analyze'
