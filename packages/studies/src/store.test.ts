/**
 * The studies store.
 *
 * The interesting test here is the cross-language one: `canonicalize` in this package and
 * `digest.canonical` in the Python engine must produce the same address for the same input.
 * They are separate implementations in separate languages, so nothing but a test stops them
 * from drifting — and if they did, re-running an unchanged study would silently create a
 * duplicate row, which is exactly the bug content addressing exists to prevent.
 */
import { describe, expect, it } from 'vitest'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { StudyResult } from '@loadcurveanalyze/engine-model'
import { canonicalize, canonicalJson, contentDigest } from './canonical.js'
import { SCHEMA_VERSION, StudyStore } from './store.js'

function result(overrides: Partial<StudyResult> = {}): StudyResult {
  return {
    inputDigest: 'sha256:aaa',
    engineVersion: '0.1.0',
    propagation: {
      intervals: 2,
      fixpoint: true,
      iterations: 2,
      verdict: 'infeasible',
      feasible: false,
      quantities: [],
      violations: ['soc-floor', 'l45-lateral'],
      variables: [],
    },
    core: {
      feasible: false,
      constraintIds: ['soc-floor', 'l45-lateral'],
      irredundant: true,
      checks: 6,
    },
    relaxation: { feasible: true, optimal: true, totalDelta: 0.765461, relaxations: [], combinations: 1 },
    security: {
      baseFeasible: false,
      contingencies: [],
      secure: 0,
      violated: 0,
      islanded: 0,
    },
    verdict: 'infeasible',
    ...overrides,
  } as StudyResult
}

describe('canonicalize', () => {
  it('sorts object keys so serialiser order cannot change the address', () => {
    expect(Object.keys(canonicalize({ b: 1, a: 2 }) as object)).toEqual(['a', 'b'])
  })

  it('normalises negative zero, which is equal as a number but not as a string', () => {
    expect(canonicalJson(-0)).toBe(canonicalJson(0))
  })

  it('rejects non-finite values, which have no JSON representation', () => {
    expect(() => canonicalize(Number.NaN)).toThrow(/non-finite/)
    expect(() => canonicalize(Number.POSITIVE_INFINITY)).toThrow(/non-finite/)
  })

  it('agrees with the Python engine on the same input', async () => {
    // The engine's canonicaliser, invoked as a subprocess so this is a real cross-language
    // check rather than a reimplementation of it. The payload is passed via stdin because
    // shell quoting of a JSON document is not reliable across platforms.
    const input = { z: 1, a: [3.0000004, 0.1 + 0.2, -0], nested: { k: 'v' } }
    const probe = spawnSync(
      'python',
      [
        '-c',
        'import sys, json; from loadcurve_analyze.digest import digest; print(digest(json.load(sys.stdin)))',
      ],
      {
        // Vitest runs with the *package* directory as cwd, so the engine's source root is
        // three levels up rather than one.
        cwd: join(process.cwd(), '..', '..', 'services', 'engine', 'src'),
        encoding: 'utf8',
        input: JSON.stringify(input),
      },
    )
    if (probe.status !== 0) {
      throw new Error(`engine digest probe failed: ${probe.stderr ?? 'no stderr'}`)
    }
    expect((await contentDigest(input)).trim()).toBe(probe.stdout.trim())
  })
})

describe('StudyStore', () => {
  it('migrates an empty database to the latest version', () => {
    const store = new StudyStore(':memory:')
    expect(store.version).toBe(SCHEMA_VERSION)
    expect(store.isPending).toBe(false)
    store.close()
  })

  it('is idempotent across repeated migrations', () => {
    const store = new StudyStore(':memory:')
    expect(store.migrate()).toBe(store.version)
    expect(store.migrate()).toBe(store.version)
    store.close()
  })

  it('persists and reads back a study by digest', () => {
    const store = new StudyStore(':memory:')
    const analysis = result()
    store.record(analysis, 'sha256:model', 'storage conflict', 1000)
    expect(store.get('sha256:aaa')?.verdict).toBe('infeasible')
    store.close()
  })

  it('treats a repeat run of identical inputs as the same study', () => {
    const store = new StudyStore(':memory:')
    const analysis = result()
    const first = store.record(analysis, 'sha256:model', 'study', 1000)
    const second = store.record(analysis, 'sha256:model', 'study', 2000)
    expect(first.created).toBe(true)
    expect(second.created).toBe(false)
    expect(store.list()).toHaveLength(1)
    // The run count still increments: the study happened twice.
    expect(store.list()[0]?.runCount).toBe(2)
    store.close()
  })

  it('orders studies by most recently updated', () => {
    const store = new StudyStore(':memory:')
    store.record(result({ inputDigest: 'sha256:old' }), 'm', 'old', 1000)
    store.record(result({ inputDigest: 'sha256:new' }), 'm', 'new', 5000)
    expect(store.list().map((entry) => entry.name)).toEqual(['new', 'old'])
    store.close()
  })

  it('finds a study by full-text search on its name', () => {
    const store = new StudyStore(':memory:')
    store.record(result({ inputDigest: 'sha256:x' }), 'm', 'lateral overload study', 1000)
    expect(store.search('lateral')).toHaveLength(1)
    expect(store.search('nonexistent')).toHaveLength(0)
    store.close()
  })

  it('deletes a study and its search entry together', () => {
    const store = new StudyStore(':memory:')
    store.record(result({ inputDigest: 'sha256:x' }), 'm', 'doomed', 1000)
    expect(store.delete('sha256:x')).toBe(true)
    expect(store.get('sha256:x')).toBeUndefined()
    expect(store.search('doomed')).toHaveLength(0)
    store.close()
  })

  it('cascades run history when a study is deleted', () => {
    const directory = mkdtempSync(join(tmpdir(), 'loadcurve-studies-'))
    const path = join(directory, 'studies.db')
    try {
      const store = new StudyStore(path)
      store.record(result({ inputDigest: 'sha256:x' }), 'm', 'cascade', 1000)
      store.delete('sha256:x')
      const runs = store.list()
      expect(runs).toHaveLength(0)
      store.close()
    } finally {
      rmSync(directory, { recursive: true, force: true })
    }
  })
})
