import { z } from 'zod'

/**
 * The single source of truth for configuration. The settings UI in apps/web derives its
 * form from `configJsonSchema()` — that schema is never hand-written, so the two cannot drift.
 */
/**
 * The single source of truth for configuration. The settings UI in apps/web derives its
 * form from `configJsonSchema()` — that schema is never hand-written, so the two cannot drift.
 *
 * Scope note: only settings the product actually reads appear here. There is deliberately no
 * `providers` or `channels` block — those surfaces were omitted, and a config key for a
 * capability that does not exist is a promise the product does not keep. See ADR-0004.
 */
export const ConfigSchema = z.object({
  productEnv: z.enum(['development', 'test', 'production']).default('development'),
  /** Where the study store keeps its database. */
  dataDir: z.string().min(1).default('.data'),
  engine: z
    .object({
      /** Interpreter used to spawn the deterministic engine. */
      python: z.string().min(1).default('python'),
      /**
       * Subprocess timeout. A large N-1 screen with core extraction is the slow case; 30 s is
       * comfortable for the networks this product handles and still bounds a hung engine.
       */
      timeoutMs: z.number().int().positive().max(120_000).default(30_000),
      /** Propagation sweep ceiling for `grid_verify_plan`. */
      budget: z.number().int().min(1).max(4096).default(64),
    })
    .default({ python: 'python', timeoutMs: 30_000, budget: 64 }),
  logLevel: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
})

export type Config = z.infer<typeof ConfigSchema>

export const defaultConfig = (): Config => ConfigSchema.parse({})

/** JSON Schema for the settings UI, derived from the zod schema. */
export function configJsonSchema(): Record<string, unknown> {
  return z.toJSONSchema(ConfigSchema, { io: 'input' }) as Record<string, unknown>
}
