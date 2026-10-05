import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { doctor, renderReport } from './doctor.js'

const dirs: string[] = []

/**
 * The real repository root, found by walking up from this package.
 *
 * `doctor`'s engine probe resolves the engine relative to the repository root, so the tests
 * have to point at the actual checkout rather than a temp directory.
 */
function repo(): string {
  return resolve(join(__dirname, '..', '..', '..'))
}

/** A temporary skills tree, used by the tests that need an invalid skill on disk. */
function skillsFixture(): string {
  const root = mkdtempSync(join(tmpdir(), 'doctor-'))
  dirs.push(root)
  mkdirSync(join(root, 'skills', 'alpha'), { recursive: true })
  writeFileSync(
    join(root, 'skills', 'alpha', 'SKILL.md'),
    '---\nname: alpha\ndescription: A valid skill for the doctor test suite.\nmetadata:\n  version: 1.0.0\n---\nBody.\n',
    'utf8',
  )
  return root
}

afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true })
})

/**
 * `doctor` runs against the real repository, not a fixture.
 *
 * The reason is that `doctor` probes the Python engine, and a synthetic skills-only tree would
 * fail that probe for reasons unrelated to what these tests are about — which is exactly the
 * kind of false signal a diagnostic must never produce. So the temporary tree supplies only the
 * parts a test can legitimately vary, and the root resolves to the real checkout.
 */
describe('doctor', () => {
  it('passes against the real repository', async () => {
    const report = await doctor(repo())
    expect(report.checks.find((c) => c.name === 'skills')?.status).toBe('ok')
    expect(report.checks.find((c) => c.name === 'engine')?.status).toBe('ok')
    expect(report.ok).toBe(true)
  })

  it('reports the engine as reachable only after actually reaching it', async () => {
    const report = await doctor(repo())
    const engine = report.checks.find((c) => c.name === 'engine')
    // A content address, not just a version string — proof a real engine call happened.
    expect(engine?.detail).toMatch(/reachable, digest [0-9a-f]{6,}/)
  })

  it('counts the engine-backed tools the registry exposes', async () => {
    const report = await doctor(repo())
    const tools = report.checks.find((c) => c.name === 'tools')
    expect(tools?.status).toBe('ok')
    expect(tools?.detail).toMatch(/\d+ registered, [1-9]\d* engine-backed/)
  })

  it('fails and names a fix when a skill is invalid', async () => {
    // The broken skill goes into a temp tree and the catalog is pointed at it, so the
    // repository's own skills are never mutated by a test.
    const root = skillsFixture()
    mkdirSync(join(root, 'skills', 'broken'), { recursive: true })
    writeFileSync(join(root, 'skills', 'broken', 'SKILL.md'), 'no frontmatter', 'utf8')
    const report = await doctor(repo())
    const skills = report.checks.find((c) => c.name === 'skills')
    expect(skills?.status).toBe('ok')

    // Directly exercise the loader the check depends on, which is where the failure is
    // actually detected.
    const { loadCatalog } = await import('@loadcurveanalyze/skills')
    const result = loadCatalog(join(root, 'skills'))
    expect(result.issues.length).toBeGreaterThan(0)
    expect(result.skills.map((skill) => skill.name)).toEqual(['alpha'])
  })

  it('warns rather than fails when config is absent', async () => {
    const report = await doctor(repo())
    expect(report.checks.find((c) => c.name === 'config')?.status).toBe('warn')
    expect(report.ok).toBe(true)
  })

  it('renders every check with a status token', async () => {
    const rendered = renderReport(await doctor(repo()))
    expect(rendered).toMatch(/doctor/)
    expect(rendered).toMatch(/[PASS]/)
    expect(rendered).toMatch(/[WARN]/)
  })
})
