/**
 * Builds the one registry every surface shares.
 *
 * The five analysis tools come from `@loadcurveanalyze/tools` — they are the product. The two
 * discovery tools (skills, plugins) are declared here because they describe the local
 * installation rather than the domain, and they are what `loadcurve tools` prints so an
 * operator can see exactly what this checkout can do.
 *
 * Everything is registered under explicit source names: a duplicate registration fails loudly
 * naming both sources, which is the failure mode that would otherwise surface as "my tool
 * call silently did nothing".
 */
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { ToolRegistry, type ToolContext } from '@loadcurveanalyze/core'
import { buildProductRegistry, discoveryTools } from '@loadcurveanalyze/tools'

export const ENGINE_MODULE = 'loadcurve_analyze'

export function buildToolRegistry(cwd = process.cwd()): ToolRegistry {
  const root = resolveRoot(cwd)

  const registry = new ToolRegistry()
  for (const tool of buildProductRegistry({ root }).list()) {
    registry.register(tool, { source: 'core' })
  }
  for (const tool of discoveryTools({ root })) {
    registry.register(tool, { source: 'core' })
  }
  return registry
}

/**
 * Find the repository root from the caller's cwd.
 *
 * The engine and the skill catalog are addressed relative to the root, so a CLI invoked from
 * a subdirectory must still find them. Walking up to the nearest `package.json` is the
 * cheapest thing that works for both a checkout and an installed tree.
 */
export function resolveRoot(cwd = process.cwd()): string {
  let current = cwd
  for (let depth = 0; depth < 12; depth += 1) {
    if (existsSync(join(current, 'package.json'))) return current
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
  return cwd
}

/** A minimal, dependency-free logger for the tool context. Diagnostics go to stderr. */
export function createContext(requestId = 'cli'): ToolContext {
  return {
    requestId,
    now: () => Date.now(),
    log: (level, message, fields) => {
      process.stderr.write(`${JSON.stringify({ level, message, requestId, ...fields })}\n`)
    },
    dataDir: process.env.PRODUCT_DATA_DIR ?? '.data',
  }
}
