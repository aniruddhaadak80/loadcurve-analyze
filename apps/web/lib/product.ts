/**
 * The product's data layer.
 *
 * Every page reads through here — never a `fetch` in a component — so there is one place that
 * knows how a study is obtained and one set of types for it. That is what lets the same
 * rendering code serve a locally-computed study and a Vercel deployment where Python is not
 * available.
 *
 * The important decision is in `getStudy`: on Vercel there is no Python runtime, so the Python
 * engine cannot run there. Rather than pretend, this falls back to a **recorded result** and
 * labels it as recorded. A deployed demo that quietly showed a stale number would be worse than
 * one that admits it is showing a recording.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { StudyResult } from '@loadcurveanalyze/engine-model'

export interface Surface {
  readonly id: string
  readonly title: string
  readonly summary: string
  readonly status: 'shipped' | 'omitted'
  readonly reason?: string
}

export const PRODUCT = {
  name: 'LoadCurve Analyze',
  slug: 'loadcurve-analyze',
  version: '0.1.0',
  tagline:
    'Prove a grid operating plan is physically admissible — and when it is not, name the smallest contradictory constraint set and the exact relaxation each constraint needs.',
} as const

/** The surfaces that ship, and the ones deliberately left out with the reason. */
export const SURFACES: readonly Surface[] = [
  {
    id: 'cli',
    title: 'CLI',
    summary:
      'The load-bearing entry point. `loadcurve verify example` runs a full study; `loadcurve explain` prints the core and the cheapest fix.',
    status: 'shipped',
  },
  {
    id: 'engine',
    title: 'Deterministic engine',
    summary:
      'Python. Bound propagation to a fixed point, minimal unsatisfiable core extraction, exact L1 relaxation, N-1 screen. No model call anywhere in the analysis path.',
    status: 'shipped',
  },
  {
    id: 'mcp',
    title: 'MCP server',
    summary:
      'Seven tools over stdio, so any MCP client can ask whether a plan is admissible. Stateless; MCP is a transport, never a second implementation.',
    status: 'shipped',
  },
  {
    id: 'skills',
    title: 'Skills catalog',
    summary:
      'Three workflows on disk with frontmatter validation and a version gate that fails CI when a body changes without a bump.',
    status: 'shipped',
  },
  {
    id: 'studies',
    title: 'Study store',
    summary:
      'SQLite keyed by content address. A re-run of unchanged inputs is the same study, not a duplicate.',
    status: 'shipped',
  },
  {
    id: 'plugins',
    title: 'Plugin registry',
    summary:
      'Manifest-driven adapters with priority-based conflict resolution and a report of why each was accepted or rejected.',
    status: 'shipped',
  },
  {
    id: 'desktop',
    title: 'Desktop shell',
    summary:
      'Omitted. This is a study tool that runs in CI and on an operator’s terminal; an Electron wrapper would add a 150 MB download to show a window around a web app.',
    status: 'omitted',
    reason: 'No remote or GUI-only workflow exists that the CLI and web app do not already cover.',
  },
  {
    id: 'channels',
    title: 'Channel adapters',
    summary: 'Omitted. The product has no remote surface — the only consumers are the CLI, JSON and MCP.',
    status: 'omitted',
    reason:
      'Shipping a channel layer for a local-first prover would be a second path to the same capabilities.',
  },
  {
    id: 'providers',
    title: 'LLM providers',
    summary:
      'Omitted deliberately. A model call in the analysis path would make a study non-reproducible, and reproducibility is the product.',
    status: 'omitted',
    reason: 'The parts that must be exactly right are code, not generation. See ADR-0004.',
  },
]

export type StudySource = 'computed' | 'recorded'

export interface StudyPayload {
  readonly result: StudyResult
  readonly source: StudySource
  readonly note: string
}

/**
 * Run the example study.
 *
 * On a machine with Python, this spawns the real engine and the numbers are live. On a runtime
 * without it, it loads a recorded result and says so — `source` is part of the payload so the
 * page can show which one it is rendering.
 *
 * **Async, and deliberately so.** The engine is a subprocess, so the call cannot be synchronous.
 * An earlier version of this function looked synchronous and returned an unresolved promise: the
 * page then read properties off a promise, which serialises to an object with no keys and
 * renders an error boundary. The `await` below is load-bearing, not decoration.
 */
export async function getStudy(): Promise<StudyPayload> {
  if (canRunEngine()) {
    try {
      const result = await runExampleStudy()
      return {
        result,
        source: 'computed',
        note: 'Computed live by the Python engine on this request.',
      }
    } catch (cause) {
      // A missing engine is a *warning*, not an error state. The page still has real content
      // to show, so this renders the recorded run with an explanation rather than the error
      // boundary — which is reserved for genuinely broken responses.
      return {
        result: recordedStudy(),
        source: 'recorded',
        note: `Engine unavailable on this host (${messageOf(cause)}). Showing the recorded run below.`,
      }
    }
  }
  return {
    result: recordedStudy(),
    source: 'recorded',
    note: 'No Python runtime on this host. Run `loadcurve verify example` locally for a live result.',
  }
}

function messageOf(cause: unknown): string {
  const text = cause instanceof Error ? cause.message : String(cause)
  // Spawn failures carry a long multi-line EACCES/ENOENT dump; the first line is the part a
  // reader needs.
  return text.split('\n')[0] ?? 'unknown error'
}

function canRunEngine(): boolean {
  // Vercel functions have no interpreter to spawn; probing once per cold start would be wasteful.
  if (process.env.VERCEL === '1') return false
  return true
}

/**
 * Compute the example study with the real engine.
 *
 * Imported dynamically so a runtime without the workspace still renders the page from the
 * recorded result instead of failing to load the module at all. The engine root is passed
 * explicitly rather than derived from cwd, because Next runs from `apps/web` while the engine
 * lives two levels up.
 */
async function runExampleStudy(): Promise<StudyResult> {
  const { EngineClient, EXAMPLE_REQUEST } = await import('@loadcurveanalyze/tools')
  const client = new EngineClient({ root: repoRoot() })
  return await client.study(EXAMPLE_REQUEST)
}

function repoRoot(): string {
  // `apps/web` at run time; the engine is under `<root>/services/engine/src`.
  return join(process.cwd(), '..', '..')
}

function recordedStudy(): StudyResult {
  const path = join(process.cwd(), 'lib', 'recorded-study.json')
  return JSON.parse(readFileSync(path, 'utf8')) as StudyResult
}

function packageVersion(): string {
  try {
    const raw = readFileSync(join(process.cwd(), 'package.json'), 'utf8')
    const parsed = JSON.parse(raw) as { version?: string }
    return parsed.version ?? '0.0.0'
  } catch {
    return '0.0.0'
  }
}

export function resolveVersion(): string {
  return packageVersion()
}
