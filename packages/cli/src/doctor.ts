import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { loadCatalog } from '@loadcurveanalyze/skills'
import { buildRegistry as buildPluginRegistry } from '@loadcurveanalyze/plugins'
import { buildToolRegistry, resolveRoot } from './bootstrap.js'

export type Status = 'ok' | 'warn' | 'fail'

export interface Check {
  readonly name: string
  readonly status: Status
  readonly detail: string
  readonly fix?: string
}

export interface DoctorReport {
  readonly ok: boolean
  readonly checks: readonly Check[]
}

const pkg = { name: 'loadcurve-analyze', version: '0.1.0' }

/**
 * The flagship command. An agent that mutates its own configuration must be able to
 * diagnose itself, and every failing row carries a fix hint rather than only a status.
 */
export async function doctor(cwd = process.cwd()): Promise<DoctorReport> {
  const checks: Check[] = []
  const registry = buildToolRegistry(cwd)

  const nodeMajor = Number(process.versions.node.split('.')[0])
  checks.push(
    nodeMajor >= 22
      ? { name: 'node', status: 'ok', detail: `v${process.versions.node}` }
      : {
          name: 'node',
          status: 'fail',
          detail: `v${process.versions.node} is below the required v22.12.0`,
          fix: 'install Node 22.12 or newer (see .nvmrc)',
        },
  )

  checks.push({
    name: 'package',
    status: 'ok',
    detail: `${pkg.name}@${pkg.version}`,
  })

  const skills = loadCatalog(join(cwd, 'skills'))
  checks.push(
    skills.issues.length === 0
      ? { name: 'skills', status: 'ok', detail: `${skills.skills.length} skills, 0 invalid` }
      : {
          name: 'skills',
          status: 'fail',
          detail: `${skills.skills.length} valid, ${skills.issues.length} invalid`,
          fix: skills.issues[0] ?? 'see npm run check:skill-version',
        },
  )

  const plugins = buildPluginRegistry(join(cwd, 'plugins'))
  checks.push(
    plugins.rejected.length === 0
      ? {
          name: 'plugins',
          status: 'ok',
          detail: `${plugins.active.length} active, ${plugins.disabled.length} disabled`,
        }
      : {
          name: 'plugins',
          status: 'warn',
          detail: `${plugins.rejected.length} rejected`,
          fix: plugins.rejected[0]?.issues[0] ?? 'inspect plugins/*/plugin.json',
        },
  )

  const configPath = join(cwd, 'product.config.json')
  checks.push(
    existsSync(configPath)
      ? { name: 'config', status: 'ok', detail: 'product.config.json found' }
      : {
          name: 'config',
          status: 'warn',
          detail: 'no product.config.json — using defaults',
          fix: 'run with defaults, or create product.config.json',
        },
  )

  // The engine is the product. If Python is missing or the engine cannot be imported, every
  // analysis tool is dead — so this probes the actual engine rather than checking that a
  // binary exists on PATH.
  checks.push(await probeEngine(cwd))

  const analysisTools = registry.list().filter((tool) => tool.permissions.includes('proc:spawn'))
  checks.push({
    name: 'tools',
    status: analysisTools.length >= 5 ? 'ok' : 'fail',
    detail: `${registry.size} registered, ${analysisTools.length} engine-backed`,
    ...(analysisTools.length >= 5
      ? {}
      : { fix: 'the registry should expose at least five engine-backed tools' }),
  })

  return { ok: checks.every((c) => c.status !== 'fail'), checks }
}

/**
 * Run the engine for real: one `digest` call over the built-in example model.
 *
 * A version check would pass on a machine where the engine is broken; an actual analysis
 * cannot. Cheap enough (one subprocess) to be worth doing on every `doctor`.
 */
async function probeEngine(cwd: string): Promise<Check> {
  const { EngineClient } = await import('@loadcurveanalyze/tools')
  const { EXAMPLE_REQUEST } = await import('@loadcurveanalyze/tools')
  try {
    const client = new EngineClient({ root: resolveRoot(cwd) })
    const result = await client.invoke('digest', EXAMPLE_REQUEST)
    const digest = (result as { studyDigest?: string }).studyDigest ?? ''
    return digest.startsWith('sha256:')
      ? { name: 'engine', status: 'ok', detail: `reachable, digest ${digest.slice(7, 19)}…` }
      : {
          name: 'engine',
          status: 'fail',
          detail: 'engine returned no content address',
          fix: 'run: python -m pytest services/engine -q',
        }
  } catch (cause) {
    return {
      name: 'engine',
      status: 'fail',
      detail: cause instanceof Error ? cause.message : String(cause),
      fix: 'check that python 3.11+ is on PATH, or set PYTHON=/path/to/python',
    }
  }
}

export function renderReport(report: DoctorReport): string {
  const width = Math.max(...report.checks.map((c) => c.name.length), 5)
  const icon = (status: Status): string => (status === 'ok' ? 'PASS' : status === 'warn' ? 'WARN' : 'FAIL')
  const lines = report.checks.map((c) => {
    const head = `  [${icon(c.status)}] ${c.name.padEnd(width)}  ${c.detail}`
    return c.fix === undefined ? head : `${head}\n         fix: ${c.fix}`
  })
  return [
    `${pkg.name} doctor`,
    ...lines,
    '',
    report.ok ? 'all required checks passed' : 'one or more checks failed',
  ].join('\n')
}
