#!/usr/bin/env node
/**
 * Refresh the recorded study the deployed demo renders.
 *
 *   node scripts/record-study.mjs
 *
 * On Vercel there is no Python runtime, so `apps/web` falls back to
 * `lib/recorded-study.json`. That file must be a real engine result, not a hand-written
 * approximation — this script produces it by actually running the engine, so it cannot drift
 * from the product's real output.
 *
 * It also strips the BOM: PowerShell's `Out-File -Encoding utf8` writes one, and
 * `JSON.parse` rejects it, which would break the demo page at runtime rather than at build.
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const TARGET = join(ROOT, 'apps', 'web', 'lib', 'recorded-study.json')

const raw = execFileSync(
  process.execPath,
  [join(ROOT, 'packages', 'cli', 'dist', 'bin.js'), 'verify', 'example', '--json'],
  {
    cwd: ROOT,
    encoding: 'utf8',
    maxBuffer: 32 * 1024 * 1024,
  },
)

const result = JSON.parse(raw.replace(/^\uFEFF/, ''))
if (typeof result.verdict !== 'string') {
  throw new Error(`engine output has no verdict; got ${JSON.stringify(result).slice(0, 200)}`)
}

writeFileSync(TARGET, `${JSON.stringify(result, null, 2)}\n`, 'utf8')

const digest = readFileSync(TARGET, 'utf8')
const verified = JSON.parse(digest)
if (verified.inputDigest !== result.inputDigest) {
  throw new Error('written file does not round-trip to the same digest')
}

process.stdout.write(
  `recorded ${result.verdict} study ${result.inputDigest} (${result.core.constraintIds.length} core members)\n`,
)
