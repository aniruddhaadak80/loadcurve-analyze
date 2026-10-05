/**
 * The single typed client for the Python engine.
 *
 * Every surface — CLI, MCP server, web API — reaches the engine through this one function.
 * That is what makes the narrow waist narrow: there is exactly one place that knows the wire
 * format, and it validates in both directions.
 *
 * Three things are enforced here rather than trusted:
 *
 * 1. **Input** is parsed by `StudyRequestSchema` before a process is spawned, so a malformed
 *    tool call fails with a field-level message instead of a Python traceback.
 * 2. **Output** is parsed by the operation's response schema before it is returned, so a
 *    changed engine field surfaces as a validation error naming the field.
 * 3. **Timestamps and randomness never enter the engine.** Nothing here passes `Date.now()`
 *    or a random seed; the same request always produces the same bytes, which is what makes
 *    the content address in a study result meaningful.
 */
import { ValidationError, UpstreamError } from '@loadcurveanalyze/core'
import { EngineBridge } from '@loadcurveanalyze/engine-client'
import {
  ENGINE_MODULE,
  RESPONSE_SCHEMAS,
  StudyRequestSchema,
  type Operation,
  type StudyRequest,
  type StudyResult,
} from '@loadcurveanalyze/engine-model'

export interface EngineClientOptions {
  /** Absolute path to the repository root. The engine lives under `services/engine/src`. */
  readonly root: string
  /** Interpreter override. Defaults to `python`, or `$PYTHON` when set. */
  readonly python?: string | undefined
  readonly timeoutMs?: number | undefined
}

/** One place that knows how to turn a request into a typed result. */
export interface CallOptions {
  readonly budget?: number
  readonly explain?: boolean
}

export class EngineClient {
  readonly #bridge: EngineBridge

  constructor(options: EngineClientOptions) {
    // `$PYTHON` wins over the default so the same CLI works against a virtualenv without a
    // config file — which is how a grid engineer actually runs it.
    const python = options.python ?? process.env.PYTHON ?? 'python'
    this.#bridge = new EngineBridge({
      module: ENGINE_MODULE,
      python,
      cwd: `${options.root}/services/engine/src`,
      timeoutMs: options.timeoutMs ?? 30_000,
    })
  }

  /** Run the full study: propagation, core, relaxation, and the N-1 screen. */
  async study(request: StudyRequest, options: CallOptions = {}): Promise<StudyResult> {
    const payload = withOptions(request, options)
    const value = await this.#call('study', payload)
    return RESPONSE_SCHEMAS.study.parse(value)
  }

  /**
   * Raw envelope access, for `doctor` and the CLI's engine smoke test.
   *
   * Returns the unvalidated value so a caller can report *why* an engine call failed instead
   * of masking it behind a schema error.
   */
  async invoke(operation: Operation, request: StudyRequest, options: CallOptions = {}): Promise<unknown> {
    return await this.#call(operation, withOptions(request, options))
  }

  async #call(operation: Operation, payload: unknown): Promise<unknown> {
    const envelope = await this.#bridge.invoke({ op: operation, input: payload })
    if (!envelope.ok) {
      throw new UpstreamError(envelope.error?.message ?? 'engine returned an unknown error', {
        op: operation,
        code: envelope.error?.code,
      })
    }
    return envelope.value
  }
}

function withOptions(request: StudyRequest, options: CallOptions): unknown {
  const budget = options.budget ?? request.budget ?? 64
  const explain = options.explain ?? request.explain ?? true
  return { ...request, budget, explain }
}

/**
 * Parse untrusted JSON as a study request.
 *
 * Split out so the CLI, the MCP server, and the web API all produce the same message for the
 * same bad input — a caller that hand-rolls this gets a different error per surface.
 */
export function parseStudyRequest(input: unknown): StudyRequest {
  const result = StudyRequestSchema.safeParse(input)
  if (!result.success) {
    const first = result.error.issues[0]
    const path = first?.path.join('.') ?? '(root)'
    throw new ValidationError(`study request is invalid at ${path}: ${first?.message ?? 'unknown'}`, { path })
  }
  return result.data
}
