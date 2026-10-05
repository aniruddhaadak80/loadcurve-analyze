/**
 * Tests for the product's tool definitions.
 *
 * These exercise the tools the way a surface does — through the registry, with a real context —
 * because that is the only path that proves the narrow waist holds. Two properties are checked
 * that a unit test of the handlers would miss: the registry rejects a duplicate name, and every
 * tool's schema is something MCP can actually carry.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ToolRegistry, type ToolContext } from '@loadcurveanalyze/core'
import { buildProductRegistry, discoveryTools, productTools } from './index.js'
import { EXAMPLE_REQUEST } from './example.js'

const ROOT = join(process.cwd(), '..', '..')

function context(): ToolContext {
  return {
    requestId: 'test',
    now: () => 0,
    log: () => {},
    dataDir: '.data',
  }
}

describe('tool registry', () => {
  it('registers the product tools with MCP-safe names', () => {
    const registry = buildProductRegistry({ root: ROOT })
    const names = registry.names()
    expect(names).toContain('grid_verify_plan')
    expect(names).toContain('grid_explain_infeasibility')
    expect(names).toContain('grid_screen_contingencies')
    for (const name of names) {
      expect(name).toMatch(/^[a-z][a-z0-9_]*$/)
    }
  })

  it('rejects a duplicate name and names both sources', () => {
    const registry = buildProductRegistry({ root: ROOT })
    const tools = productTools({ root: ROOT })
    expect(() => registry.register(tools[0]!, { source: 'a-duplicate' })).toThrow(/already registered/)
  })

  it('declares proc:spawn on every engine-backed tool and nothing else', () => {
    for (const tool of productTools({ root: ROOT })) {
      expect(tool.permissions).toEqual(['proc:spawn'])
      expect(tool.surface).toBe('core')
    }
  })

  it('gives every tool a non-empty description written for a model', () => {
    for (const tool of [...productTools({ root: ROOT }), ...discoveryTools({ root: ROOT })]) {
      expect(tool.description.length).toBeGreaterThan(80)
    }
  })

  it('refuses to invoke an engine tool without the permission it declares', async () => {
    const registry = buildProductRegistry({ root: ROOT })
    await expect(registry.invoke('grid_verify_plan', EXAMPLE_REQUEST, context(), [])).rejects.toThrow(
      /permissions/i,
    )
  })
})

describe('grid_verify_plan', () => {
  it('returns the engine verdict for the example study', async () => {
    const registry = buildProductRegistry({ root: ROOT })
    const result = (await registry.invoke('grid_verify_plan', EXAMPLE_REQUEST, context(), [
      'proc:spawn',
    ])) as { verdict: string; core: { constraintIds: string[] } }

    expect(result.verdict).toBe('infeasible')
    // The two constraints that only conflict together.
    expect(result.core.constraintIds.sort()).toEqual(['l45-lateral', 'soc-floor'])
  })

  it('is deterministic: two runs of the same study agree', async () => {
    const registry = buildProductRegistry({ root: ROOT })
    const run = async () =>
      (await registry.invoke('grid_verify_plan', EXAMPLE_REQUEST, context(), ['proc:spawn'])) as {
        inputDigest: string
      }
    expect((await run()).inputDigest).toBe((await run()).inputDigest)
  })

  it('rejects malformed input with a field-level message rather than a traceback', async () => {
    const registry = buildProductRegistry({ root: ROOT })
    await expect(
      registry.invoke('grid_verify_plan', { model: 'not a model' }, context(), ['proc:spawn']),
    ).rejects.toThrow(/invalid/)
  })
})

describe('grid_explain_infeasibility', () => {
  it('returns the core and the relaxation plan, not the whole study', async () => {
    const registry = buildProductRegistry({ root: ROOT })
    const result = (await registry.invoke('grid_explain_infeasibility', EXAMPLE_REQUEST, context(), [
      'proc:spawn',
    ])) as { core: { irredundant: boolean }; relaxation: { totalDelta: number } }

    expect(result.core.irredundant).toBe(true)
    expect(result.relaxation.totalDelta).toBeGreaterThan(0)
  })
})

describe('the shipped example', () => {
  it('is recorded at the digest a fresh engine run produces', async () => {
    // This is the anti-drift check for the demo page: the deployed site renders
    // `recorded-study.json` whenever Python is unavailable, so a stale file would show
    // different numbers than the CLI — and nothing else would catch it.
    const recorded = JSON.parse(
      readFileSync(join(ROOT, 'apps', 'web', 'lib', 'recorded-study.json'), 'utf8'),
    ) as { inputDigest: string; verdict: string }
    const registry = buildProductRegistry({ root: ROOT })
    const live = (await registry.invoke('grid_verify_plan', EXAMPLE_REQUEST, context(), ['proc:spawn'])) as {
      inputDigest: string
    }

    expect(recorded.inputDigest).toMatch(/^sha256:[0-9a-f]{64}$/)
    expect(recorded.inputDigest).toBe(live.inputDigest)
    expect(recorded.verdict).toBe('infeasible')
  })
})
