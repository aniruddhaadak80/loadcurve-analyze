/**
 * The engine contract's own tests.
 *
 * These check the schemas rather than the engine: that a well-formed study passes, that a
 * malformed one is rejected with a field-level message, and — most importantly — that the
 * recorded study shipped for the deployed demo actually satisfies the response schema. Without
 * that last check, an engine change could ship a demo that renders `undefined` and no local
 * test would notice, because the local tests compute a live result instead.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  ConstraintSchema,
  OPERATIONS,
  RESPONSE_SCHEMAS,
  StudyRequestSchema,
  StudyResultSchema,
} from './index.js'

const MODEL = {
  name: 'test-feeder',
  baseMva: 10,
  slackBus: 'S1',
  buses: [
    { id: 'S1', baseKv: 33 },
    { id: 'S2', baseKv: 33 },
  ],
  branches: [{ id: 'T12', fromBus: 'S1', toBus: 'S2', reactancePu: 0.1, ratingMw: 5 }],
  storage: [],
}

const REQUEST = {
  model: MODEL,
  plan: { intervals: [{ hours: 1, buses: { S2: { lowerMw: 1, upperMw: 1 } } }] },
  constraints: [{ id: 'c1', kind: 'line_thermal', target: 'T12' }],
}

describe('StudyRequestSchema', () => {
  it('accepts a minimal valid study and fills the defaults', () => {
    const parsed = StudyRequestSchema.parse(REQUEST)
    expect(parsed.plan.partial).toBe(false)
    expect(parsed.constraints[0]?.enabled).toBe(true)
    expect(parsed.budget).toBe(64)
    expect(parsed.explain).toBe(true)
  })

  it('rejects a zero-reactance branch', () => {
    const broken = {
      ...REQUEST,
      model: { ...MODEL, branches: [{ ...MODEL.branches[0], reactancePu: 0 }] },
    }
    expect(StudyRequestSchema.safeParse(broken).success).toBe(false)
  })

  it('rejects a non-thermal constraint with neither bound, which is not decidable', () => {
    const result = StudyRequestSchema.safeParse({
      ...REQUEST,
      constraints: [{ id: 'c', kind: 'poi_export', target: 'c', members: ['S2'] }],
    })
    expect(result.success).toBe(false)
  })

  it('accepts a line_thermal constraint with neither bound, inheriting the branch rating', () => {
    const parsed = StudyRequestSchema.parse({
      ...REQUEST,
      constraints: [{ id: 'c', kind: 'line_thermal', target: 'T12' }],
    })
    // The engine resolves the inherited rating; the schema must not reject it first.
    expect(parsed.constraints[0]?.lower ?? null).toBeNull()
  })

  it('rejects a line_thermal constraint naming a branch that does not exist', () => {
    const result = StudyRequestSchema.safeParse({
      ...REQUEST,
      constraints: [{ id: 'c', kind: 'line_thermal', target: 'NOPE', lower: 1, upper: 2 }],
    })
    expect(result.success).toBe(false)
  })

  it('rejects an unknown constraint kind rather than ignoring it', () => {
    expect(
      ConstraintSchema.safeParse({ id: 'c', kind: 'vibes', target: 'T12', lower: 1, upper: 2 }).success,
    ).toBe(false)
  })
})

describe('recorded study', () => {
  it('satisfies the response schema the demo page renders', () => {
    // The deployed demo renders this file when no Python runtime is available, so it must
    // parse against the same schema a live result is checked against. Vitest runs with the
    // *package* directory as cwd, so the repo root is two levels up.
    const raw = readFileSync(
      join(process.cwd(), '..', '..', 'apps', 'web', 'lib', 'recorded-study.json'),
      'utf8',
    )
    const parsed = StudyResultSchema.parse(JSON.parse(raw))
    expect(parsed.verdict).toBe('infeasible')
    expect(parsed.core.constraintIds.length).toBeGreaterThan(0)
    expect(parsed.propagation.quantities.length).toBeGreaterThan(0)
  })
})

describe('operation table', () => {
  it('has a response schema for every operation', () => {
    for (const operation of OPERATIONS) {
      expect(RESPONSE_SCHEMAS[operation]).toBeDefined()
    }
  })
})
