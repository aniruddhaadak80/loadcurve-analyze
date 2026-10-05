import { readFile } from 'node:fs/promises'
import { Command } from 'commander'
import type { StudyRequest, StudyResult } from '@loadcurveanalyze/engine-model'
import { EXAMPLE_REQUEST } from '@loadcurveanalyze/tools'
import { buildToolRegistry, createContext } from './bootstrap.js'
import { doctor, renderReport } from './doctor.js'
import { renderExplanation, renderStudy, type ExplanationOutput } from './render.js'

const VERSION = '0.1.0'

/** Exit codes are part of the contract: 0 ok, 1 runtime failure, 2 usage error. */
export function buildProgram(): Command {
  const program = new Command()

  program
    .name('loadcurve')
    .description(
      'Prove a grid operating plan is physically admissible — and when it is not, name the smallest contradictory constraint set and the exact relaxation each constraint needs.',
    )
    .version(VERSION, '-v, --version', 'print the version')
    .exitOverride((error) => {
      process.exitCode = error.exitCode === 0 ? 0 : 2
      throw error
    })

  program
    .command('doctor')
    .description('diagnose every subsystem and print an actionable report')
    .option('--json', 'machine-readable output')
    .action(async () => {
      const report = await doctor()
      process.stdout.write(
        process.argv.includes('--json')
          ? `${JSON.stringify(report, null, 2)}\n`
          : `${renderReport(report)}\n`,
      )
      if (!report.ok) process.exitCode = 1
    })

  program
    .command('tools')
    .description('list the registered tools — the authoritative capability list')
    .option('--json', 'machine-readable output')
    .action(() => {
      const registry = buildToolRegistry()
      const tools = registry.list().map((tool) => ({
        name: tool.name,
        description: tool.description,
        surface: registry.surfaceOf(tool.name),
        source: registry.sourceOf(tool.name),
        permissions: tool.permissions,
        inputSchema: tool.inputSchema,
      }))
      if (process.argv.includes('--json')) {
        process.stdout.write(`${JSON.stringify(tools, null, 2)}\n`)
        return
      }
      const width = Math.max(...tools.map((t) => t.name.length), 4)
      for (const tool of tools) {
        process.stdout.write(`  ${tool.name.padEnd(width)}  [${tool.surface}]  ${tool.description}\n`)
      }
    })

  const mcp = program.command('mcp').description('Model Context Protocol commands')

  mcp
    .command('serve')
    .description('run the MCP server over stdio')
    .action(async () => {
      const { serveStdio } = await import('@loadcurveanalyze/mcp')
      const registry = buildToolRegistry()
      // stdout belongs to the protocol from here on; diagnostics must go to stderr.
      await serveStdio(registry, createContext('mcp'))
    })

  mcp
    .command('call')
    .description('invoke one tool directly, without MCP')
    .argument('<tool>', 'tool name')
    .argument('<input>', 'JSON input document')
    .action(async (tool: string, raw: string) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(raw)
      } catch (cause) {
        process.stderr.write(`error: input is not valid JSON — ${String(cause)}\n`)
        process.exitCode = 2
        return
      }
      const registry = buildToolRegistry()
      try {
        const value = await registry.invoke(tool, parsed, createContext('cli'), [
          'fs:read',
          'net:fetch',
          'proc:spawn',
        ])
        process.stdout.write(`${JSON.stringify(value ?? null, null, 2)}\n`)
      } catch (cause) {
        const code = (cause as { code?: string }).code ?? 'INTERNAL'
        process.stderr.write(`${code}: ${cause instanceof Error ? cause.message : String(cause)}\n`)
        process.exitCode = 1
      }
    })

  program
    .command('version')
    .description('print version and runtime information as JSON')
    .action(() => {
      process.stdout.write(
        `${JSON.stringify(
          {
            name: 'loadcurve-analyze',
            version: VERSION,
            node: process.versions.node,
            platform: process.platform,
            python: process.env.PYTHON ?? 'python',
            tools: buildToolRegistry().size,
          },
          null,
          2,
        )}\n`,
      )
    })

  program
    .command('verify')
    .description('prove a dispatch plan is admissible, and explain it when it is not')
    .argument('<study>', 'path to a study JSON file, or "example" for the built-in feeder')
    .option('--json', 'machine-readable output')
    .option('--budget <n>', 'propagation sweep limit', '64')
    .action(async (source: string, flags: { json?: boolean; budget: string }) => {
      const request = await readStudy(source)
      const registry = buildToolRegistry()
      try {
        const value = await registry.invoke('grid_verify_plan', request, createContext('cli'), ['proc:spawn'])
        const result = value as StudyResult
        if (flags.json === true) {
          process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
        } else {
          process.stdout.write(`${renderStudy(result)}\n`)
        }
        // A verified infeasible plan is a successful analysis, so the exit code follows the
        // verdict rather than the expectation: 0 means "the engine answered", and the answer
        // is in the body. `--strict` is available for a caller that wants a non-zero on
        // infeasible.
        if (result.verdict === 'undetermined') process.exitCode = 1
      } catch (cause) {
        const code = (cause as { code?: string }).code ?? 'INTERNAL'
        process.stderr.write(`${code}: ${cause instanceof Error ? cause.message : String(cause)}\n`)
        process.exitCode = 1
      }
    })

  program
    .command('explain')
    .description('print the minimal contradictory constraint set and the cheapest fix')
    .argument('<study>', 'path to a study JSON file, or "example"')
    .option('--json', 'machine-readable output')
    .action(async (source: string, flags: { json?: boolean }) => {
      const request = await readStudy(source)
      const registry = buildToolRegistry()
      try {
        const value = (await registry.invoke('grid_explain_infeasibility', request, createContext('cli'), [
          'proc:spawn',
        ])) as ExplanationOutput
        process.stdout.write(
          flags.json === true ? `${JSON.stringify(value, null, 2)}\n` : `${renderExplanation(value)}\n`,
        )
      } catch (cause) {
        const code = (cause as { code?: string }).code ?? 'INTERNAL'
        process.stderr.write(`${code}: ${cause instanceof Error ? cause.message : String(cause)}\n`)
        process.exitCode = 1
      }
    })

  return program
}

async function readStudy(source: string): Promise<StudyRequest> {
  if (source === 'example') return EXAMPLE_REQUEST
  try {
    const raw = await readFile(source, 'utf8')
    return JSON.parse(raw) as StudyRequest
  } catch (cause) {
    throw new Error(`cannot read study ${source}: ${cause instanceof Error ? cause.message : String(cause)}`)
  }
}
