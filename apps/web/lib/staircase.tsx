/**
 * The load staircase — this app's signature visual.
 *
 * It is a data treatment, not decoration: each bar is the *attained* range of one quantity
 * across the intervals of the study, the shaded band behind it is the permitted range, and the
 * gap between them is the violation. That gap is the entire finding of a study, so the hero
 * shows the finding rather than a slogan.
 *
 * Rendered as inline SVG with `currentColor`-free token fills, and every bar is labelled, so
 * the chart is readable without colour perception and without a legend.
 */
import type { QuantitySeries } from './study'

const WIDTH = 720
const HEIGHT = 168
const PAD_LEFT = 44
const PAD_RIGHT = 12
const PAD_TOP = 14
const PAD_BOTTOM = 26

interface TracePoint {
  readonly label: string
  readonly attained: readonly [number, number]
  readonly band: readonly [number, number]
  readonly excess: number
}

function points(series: QuantitySeries): readonly TracePoint[] {
  return series.series.map((point) => ({
    label: `t${point.interval}`,
    attained: [point.lower, point.upper] as const,
    band: [series.lower, series.upper] as const,
    excess: point.excessMw,
  }))
}

/** Widest absolute value across both the bands and the attained ranges, rounded up. */
function scaleFor(items: readonly TracePoint[]): number {
  let extent = 1
  for (const item of items) {
    for (const value of [item.attained[0], item.attained[1], item.band[0], item.band[1]]) {
      extent = Math.max(extent, Math.abs(value))
    }
  }
  return Math.ceil(extent)
}

export function LoadStaircase({ series }: { series: QuantitySeries }) {
  const items = points(series)
  if (items.length === 0) {
    return (
      <p className="state" data-kind="empty">
        This constraint produces no quantities: it has no applicable interval window.
      </p>
    )
  }

  const extent = scaleFor(items)
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM
  const step = plotWidth / items.length
  const barWidth = Math.max(6, step * 0.44)

  const toY = (value: number): number => PAD_TOP + plotHeight * (1 - (value + extent) / (2 * extent))

  const zeroY = toY(0)
  const hasViolation = items.some((item) => item.excess > 0)

  return (
    <figure style={{ margin: 0 }}>
      <svg
        className="trace"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={
          hasViolation
            ? `Load staircase for ${series.constraintId}: the attained range leaves the permitted band in at least one interval.`
            : `Load staircase for ${series.constraintId}: the attained range stays inside the permitted band.`
        }
      >
        {/* Zero line and the horizontal mid-lines, so a bar's magnitude is readable. */}
        <line className="trace-axis" x1={PAD_LEFT} y1={zeroY} x2={WIDTH - PAD_RIGHT} y2={zeroY} />
        <line className="trace-axis" x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={HEIGHT - PAD_BOTTOM} />

        <text className="trace-label" x={4} y={toY(extent) + 8}>
          +{extent}
        </text>
        <text className="trace-label" x={4} y={zeroY + 3}>
          0
        </text>
        <text className="trace-label" x={4} y={toY(-extent)}>
          −{extent}
        </text>

        {items.map((item, index) => {
          const centre = PAD_LEFT + step * index + step / 2
          const top = Math.min(toY(item.attained[0]), toY(item.attained[1]))
          const bottom = Math.max(toY(item.attained[0]), toY(item.attained[1]))
          const bandTop = Math.min(toY(item.band[0]), toY(item.band[1]))
          const bandBottom = Math.max(toY(item.band[0]), toY(item.band[1]))
          const violated = item.excess > 0
          const height = Math.max(1.5, bottom - top)

          return (
            <g key={item.label} style={{ animationDelay: `${index * 45}ms` }}>
              {/* The permitted band, drawn behind the bar. */}
              <rect
                className="trace-band"
                x={centre - barWidth}
                y={bandTop}
                width={barWidth * 2}
                height={Math.max(1, bandBottom - bandTop)}
                rx={1}
              />
              <rect
                className="trace-bar"
                data-violated={violated}
                x={centre - barWidth / 2}
                y={top}
                width={barWidth}
                height={height}
                rx={1}
              />
              <text className="trace-label" x={centre} y={HEIGHT - PAD_BOTTOM + 12} textAnchor="middle">
                {item.label}
              </text>
              <text
                className="trace-value"
                data-violated={violated}
                x={centre}
                y={bottom + 11}
                textAnchor="middle"
              >
                {item.attained[1].toFixed(2)}
              </text>
            </g>
          )
        })}

        <text className="trace-label" x={PAD_LEFT} y={HEIGHT - 4}>
          {series.constraintId} · band [{series.lower.toFixed(2)}, {series.upper.toFixed(2)}] · MW
        </text>
      </svg>
      <figcaption className="visually-hidden">
        Permitted band for {series.constraintId} is {series.lower} to {series.upper} MW across {items.length}{' '}
        intervals. Values above each bar are the attained upper bound in MW.
      </figcaption>
    </figure>
  )
}
