import type { Metadata } from 'next'
import { SURFACES } from '@/lib/product'

export const metadata: Metadata = { title: 'Surfaces' }

export const dynamic = 'force-static'

/** `shipped` is a proof obligation; `omitted` is a design decision. They read differently. */
const TONE = { shipped: 'ok', omitted: 'warn' } as const

export default function SurfacesPage() {
  const shipped = SURFACES.filter((surface) => surface.status === 'shipped')
  const omitted = SURFACES.filter((surface) => surface.status === 'omitted')

  return (
    <>
      <section className="hero">
        <span className="eyebrow">Capability</span>
        <h1>Surfaces</h1>
        <p className="hero-lede">
          Every capability is a <span className="mono">Tool</span> in one registry, reachable identically from
          each surface below. The omitted ones are listed with the reason, because a surface left out silently
          is indistinguishable from one that was forgotten.
        </p>
      </section>

      {shipped.length === 0 ? (
        <p className="state" data-kind="empty">
          No surfaces are registered.
        </p>
      ) : (
        <>
          <section className="section" aria-labelledby="shipped-heading">
            <h2 className="section-heading" id="shipped-heading">
              Ships
              <span className="section-note">{shipped.length} surfaces</span>
            </h2>
            <div className="grid">
              {shipped.map((surface) => (
                <article className="card" key={surface.id}>
                  <span className="badge" data-tone={TONE[surface.status]}>
                    {surface.status}
                  </span>
                  <h3>{surface.title}</h3>
                  <p>{surface.summary}</p>
                  <code className="mono muted">{surface.id}</code>
                </article>
              ))}
            </div>
          </section>

          {omitted.length === 0 ? (
            <p className="state" data-kind="empty">
              Nothing was deliberately omitted.
            </p>
          ) : (
            <section className="section" aria-labelledby="omitted-heading">
              <h2 className="section-heading" id="omitted-heading">
                Deliberately omitted
                <span className="section-note">{omitted.length} surfaces, with reasons</span>
              </h2>
              <div className="grid">
                {omitted.map((surface) => (
                  <article className="card" key={surface.id} data-omitted="true">
                    <span className="badge" data-tone={TONE[surface.status]}>
                      {surface.status}
                    </span>
                    <h3>{surface.title}</h3>
                    <p>{surface.summary}</p>
                    {surface.reason ? <p className="card-reason">{surface.reason}</p> : null}
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </>
  )
}
