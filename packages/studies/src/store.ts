/**
 * Studies: the persisted record of an analysis.
 *
 * Both the model and the analysis output are **content-addressed** by the SHA-256 of their
 * canonical JSON, and that choice is what makes a study reproducible rather than merely
 * stored. Re-running an unchanged study yields the same digest and updates one row instead of
 * appending a duplicate; two analysts who independently produce the same inputs produce the
 * same study id, so "did you run the same study?" is answerable without trusting either
 * party's filenames.
 *
 * SQLite is the right store here and the choice is argued in
 * `docs/adr/0003-content-addressed-storage.md`. WAL plus FTS5, numbered idempotent
 * migrations, and every write through one `transaction()` helper.
 */
import Database from 'better-sqlite3'
import type { StudyResult } from '@loadcurveanalyze/engine-model'

export interface StudyRow {
  readonly digest: string
  readonly model_digest: string
  readonly name: string
  readonly verdict: string
  readonly engine_version: string
  readonly created_at: number
  readonly updated_at: number
  readonly result: string
}

export interface StudySummary {
  readonly digest: string
  readonly name: string
  readonly verdict: string
  readonly createdAt: number
  readonly updatedAt: number
  readonly runCount: number
}

export const SCHEMA_VERSION = 1

const MIGRATIONS: readonly { version: number; up: readonly string[] }[] = [
  {
    version: 1,
    up: [
      `CREATE TABLE studies (
         digest        TEXT PRIMARY KEY,
         model_digest  TEXT NOT NULL,
         name          TEXT NOT NULL,
         verdict       TEXT NOT NULL,
         engine_version TEXT NOT NULL,
         created_at    INTEGER NOT NULL,
         updated_at    INTEGER NOT NULL,
         result        TEXT NOT NULL
       )`,
      `CREATE TABLE study_runs (
         id        INTEGER PRIMARY KEY AUTOINCREMENT,
         digest    TEXT NOT NULL REFERENCES studies(digest) ON DELETE CASCADE,
         ran_at    INTEGER NOT NULL,
         verdict   TEXT NOT NULL
       )`,
      'CREATE INDEX study_runs_digest ON study_runs (digest)',
      `CREATE VIRTUAL TABLE studies_fts USING fts5 (digest UNINDEXED, name, verdict)`,
    ],
  },
]

export class StudyStore {
  readonly #db: Database.Database

  constructor(path = ':memory:') {
    this.#db = new Database(path)
    this.#db.pragma('journal_mode = WAL')
    this.#db.pragma('foreign_keys = ON')
    this.migrate()
  }

  get version(): number {
    return (this.#db.pragma('user_version', { simple: true }) as number) ?? 0
  }

  get isPending(): boolean {
    return this.version < SCHEMA_VERSION
  }

  migrate(): number {
    for (const migration of MIGRATIONS) {
      if (migration.version <= this.version) continue
      this.transaction(() => {
        for (const statement of migration.up) this.#db.exec(statement)
        this.#db.pragma(`user_version = ${migration.version}`)
      })
    }
    return this.version
  }

  transaction<T>(fn: () => T): T {
    return this.#db.transaction(fn)()
  }

  /**
   * Record one analysis run.
   *
   * Idempotent on `digest`: a repeat run of unchanged inputs increments `runCount` rather than
   * inserting a second study, which is the whole reason the table is keyed by content address
   * rather than by an autoincrement id.
   */
  record(
    result: StudyResult,
    modelDigest: string,
    name: string,
    now: number,
  ): { digest: string; created: boolean } {
    return this.transaction(() => {
      const existing = this.#db
        .prepare('SELECT digest FROM studies WHERE digest = ?')
        .get(result.inputDigest) as { digest: string } | undefined

      if (existing === undefined) {
        this.#db
          .prepare(
            `INSERT INTO studies (digest, model_digest, name, verdict, engine_version,
                                  created_at, updated_at, result)
             VALUES (@digest, @modelDigest, @name, @verdict, @engineVersion, @now, @now, @result)`,
          )
          .run({
            digest: result.inputDigest,
            modelDigest,
            name,
            verdict: result.verdict,
            engineVersion: result.engineVersion,
            now,
            result: JSON.stringify(result),
          })
        this.#db.prepare('DELETE FROM studies_fts WHERE digest = ?').run(result.inputDigest)
        this.#db
          .prepare('INSERT INTO studies_fts (digest, name, verdict) VALUES (?, ?, ?)')
          .run(result.inputDigest, name, result.verdict)
      } else {
        this.#db
          .prepare('UPDATE studies SET updated_at = ?, result = ? WHERE digest = ?')
          .run(now, JSON.stringify(result), result.inputDigest)
      }

      this.#db
        .prepare('INSERT INTO study_runs (digest, ran_at, verdict) VALUES (?, ?, ?)')
        .run(result.inputDigest, now, result.verdict)

      return { digest: result.inputDigest, created: existing === undefined }
    })
  }

  get(digest: string): StudyResult | undefined {
    const row = this.#db.prepare('SELECT result FROM studies WHERE digest = ?').get(digest) as
      { result: string } | undefined
    return row === undefined ? undefined : (JSON.parse(row.result) as StudyResult)
  }

  list(limit = 50): readonly StudySummary[] {
    const rows = this.#db
      .prepare(
        `SELECT s.digest, s.name, s.verdict, s.created_at, s.updated_at,
                (SELECT COUNT(*) FROM study_runs r WHERE r.digest = s.digest) AS run_count
           FROM studies s ORDER BY s.updated_at DESC LIMIT ?`,
      )
      .all(limit) as {
      digest: string
      name: string
      verdict: string
      created_at: number
      updated_at: number
      run_count: number
    }[]
    return rows.map((row) => ({
      digest: row.digest,
      name: row.name,
      verdict: row.verdict,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      runCount: row.run_count,
    }))
  }

  /** Full-text search over study names. */
  search(query: string, limit = 50): readonly StudySummary[] {
    const rows = this.#db
      .prepare(
        `SELECT s.digest, s.name, s.verdict, s.created_at, s.updated_at,
                (SELECT COUNT(*) FROM study_runs r WHERE r.digest = s.digest) AS run_count
           FROM studies_fts f JOIN studies s ON s.digest = f.digest
          WHERE studies_fts MATCH ? ORDER BY s.updated_at DESC LIMIT ?`,
      )
      .all(query, limit) as {
      digest: string
      name: string
      verdict: string
      created_at: number
      updated_at: number
      run_count: number
    }[]
    return rows.map((row) => ({
      digest: row.digest,
      name: row.name,
      verdict: row.verdict,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      runCount: row.run_count,
    }))
  }

  delete(digest: string): boolean {
    return this.transaction(() => {
      const changes = this.#db.prepare('DELETE FROM studies WHERE digest = ?').run(digest).changes
      this.#db.prepare('DELETE FROM studies_fts WHERE digest = ?').run(digest)
      return changes > 0
    })
  }

  close(): void {
    this.#db.close()
  }
}
