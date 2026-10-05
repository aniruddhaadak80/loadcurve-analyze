import Link from 'next/link'
import { LoadStaircase } from '@/lib/staircase'
import { StudyTable } from '@/lib/study-table'
import { shortDigest, toneFor } from '@/lib/study'
import { PRODUCT, SURFACES, getStudy, type StudyPayload } from '@/lib/product'

/**
 * `force-dynamic` is load-bearing here, not a default.
 *
 * Without it Next prerenders this route at build time, and because the page's content is a
 * Python subprocess call the prerender cannot await it — the result is a build that succeeds
 * and a page that streams a skeleton forever. This forces the study to be computed per request.
 */
export const dynamic = 'force-dynamic'

/** No client component is needed: the whole page renders from one server-side call. */
export const dynamicParams = true

/**
 * The study page.
 *
 * Server-rendered on every request: the numbers below are computed by the Python engine during
 * the render, so there is no loading state to show and nothing to hydrate. `force-dynamic` is
 * what guarantees that — without it Next would prerender a page whose entire content is a
 * subprocess call, and ship a permanent skeleton to production.
 */
export default async function StudyPage({ searchParams }: { searchParams: Promise<{ detail?: string }> }) {
  // `getStudy` is awaited: it spawns the Python engine, and reading its properties without
  // awaiting yields a promise, which serialises to an empty object and renders an error boundary.
  const [{ detail }, payload] = await Promise.all([searchParams, getStudy()])
  return (
    <StudyView result={payload.result} source={payload.source} note={payload.note} detail={detail ?? null} />
  )
}

function StudyView({
  result,
  source,
  note,
  detail,
}: {
  result: StudyPayload['result']
  source: 'computed' | 'recorded'
  note: string
  detail: string | null
}) {
  return (
    <>
      <section className="hero">
        <span className="eyebrow">
          v{PRODUCT.version} · {PRODUCT.slug}
        </span>
        <h1>{PRODUCT.name}</h1>
        <p className="hero-lede">{PRODUCT.tagline}</p>
        <div className="hero-actions">
          <a className="button" data-variant="primary" href="#constraints">
            The study below
          </a>
          <a className="button" href="#surfaces">
            Surfaces
          </a>
          <Link className="button" href="/health">
            Health
          </Link>
        </div>
      </section>

      <section className="section" aria-labelledby="finding">
        <h2 className="section-heading" id="finding">
          The finding
          <span className="section-note">
            {source === 'computed' ? 'computed live' : 'recorded run'} · {note}
          </span>
        </h2>

        <div className="verdict">
          <div className="verdict-cell">
            <span className="verdict-key">Verdict</span>
            <span className="verdict-value" data-tone={toneFor(result.verdict)}>
              {result.verdict}
            </span>
          </div>
          <div className="verdict-cell">
            <span className="verdict-key">Core</span>
            <span className="verdict-value">
              {result.core.constraintIds.length === 0
                ? 'none'
                : `${result.core.constraintIds.length} constraints`}
            </span>
          </div>
          <div className="verdict-cell">
            <span className="verdict-key">Cheapest fix</span>
            <span className="verdict-value">
              {result.relaxation.totalDelta === 0 ? '—' : `${result.relaxation.totalDelta.toFixed(3)} MW`}
            </span>
          </div>
          <div className="verdict-cell">
            <span className="verdict-key">N-1 screen</span>
            <span className="verdict-value">
              {result.security.secure}/{result.security.contingencies.length} secure
            </span>
          </div>
          <div className="verdict-cell">
            <span className="verdict-key">Input digest</span>
            <span className="verdict-value">{shortDigest(result.inputDigest)}</span>
          </div>
        </div>

        <LoadStaircase series={worstQuantity(result)} />
      </section>

      <section className="section" id="constraints" aria-labelledby="constraints-heading">
        <h2 className="section-heading" id="constraints-heading">
          Constraints
          <span className="section-note">
            {result.propagation.violations.length} violated of {result.propagation.quantities.length}
          </span>
        </h2>
        <StudyTable result={result} selected={detail} />
      </section>

      <section className="section" aria-labelledby="core-heading">
        <h2 className="section-heading" id="core-heading">
          Minimal unsatisfiable core
        </h2>
        {result.core.feasible ? (
          <p className="state">The plan is admissible as declared; no contradiction exists.</p>
        ) : (
          <>
            <div className="table-wrap">
              <div className="table-scroll">
                <table className="dense">
                  <caption>
                    Every member is necessary — the engine removed each in turn and re-checked (
                    {result.core.checks} satisfiability checks)
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Member</th>
                      <th scope="col">Kind</th>
                      <th scope="col">Target</th>
                      <th scope="col">Bound</th>
                      <th scope="col" className="numeric">
                        Cheapest move
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.core.constraintIds.map((id) => {
                      const quantity = result.propagation.quantities.find(
                        (entry) => entry.constraintId === id,
                      )
                      const move = result.relaxation.relaxations.find((entry) => entry.constraintId === id)
                      return (
                        <tr key={id}>
                          <td className="mono">{id}</td>
                          <td className="mono muted">{quantity?.kind ?? '—'}</td>
                          <td className="mono">{quantity?.target ?? '—'}</td>
                          <td className="numeric">
                            {quantity ? `[${quantity.lower.toFixed(2)}, ${quantity.upper.toFixed(2)}]` : '—'}
                          </td>
                          <td className="numeric">
                            {move
                              ? `${move.side} → ${move.toBound.toFixed(3)} (Δ${move.delta.toFixed(3)})`
                              : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="detail">
              <h3>Why these two conflict together</h3>
              <p className="muted">
                BESS1 starts at 50% charge with 8 MWh of usable energy, so reaching a 70% floor by the second
                hour needs at least (0.70 − 0.50) × 8 ÷ 0.95 = 1.684 MW of charging at B5. L45 is the only
                path to B5 and is rated 1 MW. Neither limit is violated on its own — the floor is reachable if
                the lateral is upgraded, the lateral is fine if the floor is dropped — and the pair admits no
                dispatch at all. That is the smallest explanation of the failure, and a violation list cannot
                produce it.
              </p>
            </div>
          </>
        )}
      </section>

      <section className="section" aria-labelledby="surfaces">
        <h2 className="section-heading" id="surfaces">
          Surfaces
        </h2>
        <div className="grid">
          {SURFACES.map((surface) => (
            <article className="card" key={surface.id} data-omitted={surface.status === 'omitted'}>
              <span className="badge" data-tone={surface.status === 'shipped' ? 'ok' : 'warn'}>
                {surface.status}
              </span>
              <h3>{surface.title}</h3>
              <p>{surface.summary}</p>
              {surface.reason ? <p className="card-reason">{surface.reason}</p> : null}
            </article>
          ))}
        </div>
      </section>
    </>
  )
}

/** The constraint with the largest excess — the one worth drawing. */
function worstQuantity(result: StudyPayload['result']) {
  const quantities = result.propagation.quantities
  const worst = quantities.reduce(
    (best, entry) => (entry.excessMw > best.excessMw ? entry : best),
    quantities[0]!,
  )
  return worst
}
