/**
 * The study table with inline detail.
 *
 * The layout is dense-table-with-inline-detail: every constraint is a row, and selecting one
 * reveals its interval series and bound without leaving the table. That is the right shape for
 * this data because an operator's actual question is comparative — "which of these limits is
 * the binding one?" — and a card grid would hide that.
 *
 * Detail is rendered server-side from a query parameter, so the page stays a single server
 * component with no client state to get wrong. It also means the expanded row is in the HTML,
 * which is what a reader or crawler gets without pressing anything.
 */
import type { QuantitySeries, StudyResult } from './study'

function flag(verdict: QuantitySeries['verdict']): { tone: 'ok' | 'warn' | 'danger'; text: string } {
  if (verdict === 'violated') return { tone: 'danger', text: 'VIOLATED' }
  if (verdict === 'undetermined') return { tone: 'warn', text: 'UNDETERMINED' }
  return { tone: 'ok', text: 'SATISFIED' }
}

function detailFor(quantity: QuantitySeries) {
  const attained = quantity.series
    .map((point) => `${point.lower.toFixed(3)} … ${point.upper.toFixed(3)}`)
    .join('  |  ')
  const worstInterval = quantity.violations.length === 0 ? null : Math.min(...quantity.violations)
  return { attained, worstInterval }
}

export function StudyTable({ result, selected }: { result: StudyResult; selected: string | null }) {
  const quantities = result.propagation.quantities

  if (quantities.length === 0) {
    return (
      <p className="state" data-kind="empty">
        This study declared no constraints, so there is nothing to propagate. Add a<code> constraints </code>{' '}
        array to the study request.
      </p>
    )
  }

  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="dense">
          <caption>
            {quantities.length} constraint{quantities.length === 1 ? '' : 's'} ·{' '}
            {result.propagation.violations.length} violated · converged in {result.propagation.iterations}{' '}
            sweep{result.propagation.iterations === 1 ? '' : 's'}
          </caption>
          <thead>
            <tr>
              <th scope="col">Constraint</th>
              <th scope="col">Kind</th>
              <th scope="col">Target</th>
              <th scope="col">Band</th>
              <th scope="col" className="numeric">
                Worst excess
              </th>
              <th scope="col">Status</th>
              <th scope="col">
                <span className="visually-hidden">Detail</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {quantities.map((quantity) => {
              const status = flag(quantity.verdict)
              const isSelected = quantity.constraintId === selected
              return (
                <tr key={quantity.constraintId}>
                  <td className="mono">{quantity.constraintId}</td>
                  <td className="mono muted">{quantity.kind}</td>
                  <td className="mono">{quantity.target}</td>
                  <td className="numeric">
                    [{quantity.lower.toFixed(2)}, {quantity.upper.toFixed(2)}]
                  </td>
                  <td className="numeric">{quantity.excessMw === 0 ? '—' : quantity.excessMw.toFixed(3)}</td>
                  <td>
                    <span className="row-flag" data-tone={status.tone}>
                      {status.text}
                    </span>
                  </td>
                  <td>
                    <a href={`?detail=${encodeURIComponent(quantity.constraintId)}#constraints`}>
                      {isSelected ? 'Hide' : 'Detail'}
                    </a>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {selected !== null ? <InlineDetail quantities={quantities} selected={selected} /> : null}
    </div>
  )
}

function InlineDetail({ quantities, selected }: { quantities: readonly QuantitySeries[]; selected: string }) {
  const quantity = quantities.find((entry) => entry.constraintId === selected)

  if (quantity === undefined) {
    return (
      <div className="detail">
        <div className="state state-fallback">
          No constraint named <code className="mono">{selected}</code> in this study. It may belong to a
          different run — every study is identified by its content address.
        </div>
      </div>
    )
  }

  const { attained, worstInterval } = detailFor(quantity)

  return (
    <div className="detail">
      <h3>{quantity.constraintId}</h3>
      <dl>
        <dt>Label</dt>
        <dd>{quantity.label}</dd>
        <dt>Kind</dt>
        <dd>{quantity.kind}</dd>
        <dt>Target</dt>
        <dd>{quantity.target}</dd>
        <dt>Band</dt>
        <dd>
          [{quantity.lower}, {quantity.upper}]
        </dd>
        <dt>Attained</dt>
        <dd>{attained}</dd>
        <dt>Violated at</dt>
        <dd>{worstInterval === null ? 'no interval' : `interval ${worstInterval}`}</dd>
      </dl>
    </div>
  )
}
