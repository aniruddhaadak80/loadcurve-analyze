/**
 * The product's tool definitions.
 *
 * These are the capabilities themselves, declared once. The CLI, the MCP server and the web
 * API each register this same list, which is the whole point of the narrow waist: adding a
 * capability means adding a tool here, and it becomes reachable from every surface at once.
 *
 * Descriptions are written for a model reading a tool list: what it does, when to reach for
 * it, and what comes back. A vague description is the most common cause of an agent
 * misusing a tool, so each one says which question it answers.
 */
import type { JsonSchema, Tool, ToolRegistry } from '@loadcurveanalyze/core'
import { ToolRegistry as Registry } from '@loadcurveanalyze/core'
import { EngineClient, parseStudyRequest } from './client.js'

export interface BuildToolsOptions {
  /** Repository root. The engine subprocess path is derived from it. */
  readonly root: string
  readonly python?: string
}

const STUDY_INPUT_SCHEMA: JsonSchema = {
  type: 'object',
  properties: {
    model: {
      type: 'object',
      description: 'Network model: buses, branches (id, fromBus, toBus, reactancePu, ratingMw), storage.',
      properties: {
        name: { type: 'string' },
        baseMva: { type: 'number' },
        slackBus: { type: 'string' },
        buses: { type: 'array', items: { type: 'object' } },
        branches: { type: 'array', items: { type: 'object' } },
        storage: { type: 'array', items: { type: 'object' } },
      },
      required: ['name', 'baseMva', 'slackBus', 'buses', 'branches'],
    },
    plan: {
      type: 'object',
      description: 'Dispatch plan: per interval, the allowed net injection window per bus.',
      properties: {
        intervals: { type: 'array', items: { type: 'object' } },
        partial: {
          type: 'boolean',
          description:
            'If true, a bus absent from an interval is unconstrained and results may be undetermined.',
        },
      },
      required: ['intervals'],
    },
    constraints: {
      type: 'array',
      description:
        'Hard constraints. Kinds: line_thermal (branch), branch_group (sum of branches), poi_export (sum of bus injections), storage_soc (unit envelope), ramp (bus or unit).',
      items: { type: 'object' },
    },
    outages: {
      type: 'array',
      description: 'N-1 outages to screen, each naming a branch to take out of service.',
      items: { type: 'object' },
    },
    budget: { type: 'integer', description: 'Propagation sweep limit. Default 64.' },
    explain: {
      type: 'boolean',
      description: 'Compute a minimal core per violated outage. Default true.',
    },
  },
  required: ['model', 'plan'],
  additionalProperties: false,
}

function studyTool(options: BuildToolsOptions): Tool<unknown, unknown> {
  const client = new EngineClient({ root: options.root, python: options.python })
  return {
    name: 'grid_verify_plan',
    description:
      'Prove whether a grid operating plan is physically admissible. Runs bound propagation over every hard constraint to a fixed point, extracts the minimal unsatisfiable core when the plan fails, computes the cheapest bound relaxation that would fix it, and screens the declared N-1 outages. Returns a verdict (feasible / infeasible / undetermined), the violated constraints with their excess, the minimal core, the relaxation plan, and the contingency report. Use this before committing a dispatch or interconnection plan; do not hand-check flows against ratings.',
    inputSchema: STUDY_INPUT_SCHEMA,
    outputSchema: { type: 'object' },
    permissions: ['proc:spawn'],
    surface: 'core',
    handler: async (input: unknown) => {
      const request = parseStudyRequest(input)
      return await client.study(request)
    },
  }
}

function propagateTool(options: BuildToolsOptions): Tool<unknown, unknown> {
  const client = new EngineClient({ root: options.root, python: options.python })
  return {
    name: 'grid_propagate',
    description:
      'Propagate hard constraints over a dispatch plan to a fixed point and report which are violated and by how much. Cheaper than grid_verify_plan and the right tool when you already know the plan is feasible and only need the numbers.',
    inputSchema: STUDY_INPUT_SCHEMA,
    outputSchema: { type: 'object' },
    permissions: ['proc:spawn'],
    surface: 'core',
    handler: async (input: unknown) => {
      const request = parseStudyRequest(input)
      return await client.invoke('propagate', request)
    },
  }
}

function coreTool(options: BuildToolsOptions): Tool<unknown, unknown> {
  const client = new EngineClient({ root: options.root, python: options.python })
  return {
    name: 'grid_explain_infeasibility',
    description:
      'Find the smallest subset of constraints that is already contradictory, and report the minimum total bound change that would make that subset satisfiable. This is the tool for "why does this plan fail" when a violation list is not enough — a pair of limits can conflict jointly while neither is violated alone. The returned core is verified minimal, not merely plausible.',
    inputSchema: STUDY_INPUT_SCHEMA,
    outputSchema: { type: 'object' },
    permissions: ['proc:spawn'],
    surface: 'core',
    handler: async (input: unknown) => {
      const request = parseStudyRequest(input)
      const result = await client.study(request)
      return {
        verdict: result.verdict,
        core: result.core,
        relaxation: result.relaxation,
        propagation: result.propagation.quantities,
      }
    },
  }
}

function contingencyTool(options: BuildToolsOptions): Tool<unknown, unknown> {
  const client = new EngineClient({ root: options.root, python: options.python })
  return {
    name: 'grid_screen_contingencies',
    description:
      'Screen a dispatch plan against single-element outages (N-1). Re-solves the network with each declared branch out of service and classifies it secure, violated, or islanded. Islanding is reported separately from violation because a split network is a different operational problem from an overload. Use this for security assessment before a plan is committed.',
    inputSchema: STUDY_INPUT_SCHEMA,
    outputSchema: { type: 'object' },
    permissions: ['proc:spawn'],
    surface: 'core',
    handler: async (input: unknown) => {
      const request = parseStudyRequest(input)
      return await client.invoke('contingency', request)
    },
  }
}

function digestTool(options: BuildToolsOptions): Tool<unknown, unknown> {
  const client = new EngineClient({ root: options.root, python: options.python })
  return {
    name: 'grid_digest',
    description:
      'Return the content address (sha256) of a network model and of a full study input. Use this to detect whether a model has changed between runs, to key a cached result, or to prove in a filing that two studies used identical inputs. Identical inputs always produce the same address, independent of key order.',
    inputSchema: STUDY_INPUT_SCHEMA,
    outputSchema: { type: 'object' },
    permissions: ['proc:spawn'],
    surface: 'core',
    handler: async (input: unknown) => {
      const request = parseStudyRequest(input)
      return await client.invoke('digest', request)
    },
  }
}

/**
 * The product's capabilities, in one list.
 *
 * Kept in a function rather than a module constant so each tool gets its own `EngineClient`
 * with the caller's root — a module-level registry would silently pin one directory and break
 * the moment the CLI was run from elsewhere.
 */
export function productTools(options: BuildToolsOptions): readonly Tool<never, unknown>[] {
  return [
    studyTool(options),
    propagateTool(options),
    coreTool(options),
    contingencyTool(options),
    digestTool(options),
  ] as unknown as readonly Tool<never, unknown>[]
}

export function buildProductRegistry(options: BuildToolsOptions): ToolRegistry {
  return new Registry().registerAll(productTools(options), { source: 'core' })
}
