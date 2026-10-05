/**
 * Discovery tools: what this product can do, and where its study history lives.
 *
 * These are the two things an agent needs before it can plan anything — the capability list
 * and the record of past analyses. Kept separate from the analysis tools in `registry.ts`
 * because they do not spawn the engine.
 */
import type { Tool } from '@loadcurveanalyze/core'

export interface DiscoveryOptions {
  readonly root: string
}

function skillsTool(options: DiscoveryOptions): Tool<never, unknown> {
  return {
    name: 'list_skills',
    description:
      'List the skill catalog with each workflow name, version and description. Use this to discover which grid analysis procedures are documented before choosing a tool.',
    inputSchema: {
      type: 'object',
      properties: {
        includeBodies: { type: 'boolean', description: 'Include each skill body.' },
      },
      additionalProperties: false,
    },
    outputSchema: { type: 'object' },
    permissions: ['fs:read'],
    surface: 'core',
    handler: async (input: unknown) => {
      const { loadCatalog } = await import('@loadcurveanalyze/skills')
      const { skills, issues } = loadCatalog(`${options.root}/skills`)
      const includeBodies = (input as { includeBodies?: boolean }).includeBodies === true
      return {
        count: skills.length,
        issues: [...issues],
        skills: skills.map((skill) => ({
          name: skill.name,
          version: skill.version,
          description: skill.description,
          ...(includeBodies ? { body: skill.body } : {}),
        })),
      }
    },
  } as unknown as Tool<never, unknown>
}

function pluginsTool(options: DiscoveryOptions): Tool<never, unknown> {
  return {
    name: 'list_plugins',
    description:
      'List the resolved plugin registry, including plugins that were shadowed, disabled or rejected and why. Use this to explain why an expected capability is missing.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    outputSchema: { type: 'object' },
    permissions: ['fs:read'],
    surface: 'core',
    handler: async () => {
      const { buildRegistry } = await import('@loadcurveanalyze/plugins')
      const result = buildRegistry(`${options.root}/plugins`)
      return {
        active: result.active.map((entry) => ({
          name: entry.manifest.name,
          version: entry.manifest.version,
          capabilities: entry.manifest.capabilities,
          shadowed: entry.shadowed,
        })),
        disabled: result.disabled.map((entry) => entry.manifest.name),
        rejected: result.rejected.map((entry) => ({ path: entry.path, issues: entry.issues })),
      }
    },
  } as unknown as Tool<never, unknown>
}

export function discoveryTools(options: DiscoveryOptions): readonly Tool<never, unknown>[] {
  return [skillsTool(options), pluginsTool(options)]
}
