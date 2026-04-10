import { useState, useMemo } from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

export interface TrendRun {
  date: string
  pass_rate: number
  verdict: string
}

export interface TrendData {
  runs: TrendRun[]
  trend: string
}

interface TrendChartProps {
  data: TrendData
}

const VERDICT_COLORS: Record<string, string> = {
  pass: '#22c55e',
  fail: '#ef4444',
  advisory: '#f59e0b',
}

const VERDICT_COLORS_HOVER: Record<string, string> = {
  pass: '#16a34a',
  fail: '#dc2626',
  advisory: '#d97706',
}

function getVerdictColor(verdict: string, hover = false): string {
  const key = verdict.toLowerCase()
  const map = hover ? VERDICT_COLORS_HOVER : VERDICT_COLORS
  return map[key] || '#a1a1aa'
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function TrendIndicator({ trend }: { trend: string }) {
  const normalized = trend.toLowerCase()
  if (normalized === 'improving' || normalized === 'up') {
    return (
      <span className="inline-flex items-center gap-1 text-sm font-medium text-green-600 dark:text-green-400">
        <TrendingUp className="w-4 h-4" />
        Improving
      </span>
    )
  }
  if (normalized === 'degrading' || normalized === 'down') {
    return (
      <span className="inline-flex items-center gap-1 text-sm font-medium text-red-600 dark:text-red-400">
        <TrendingDown className="w-4 h-4" />
        Degrading
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
      <Minus className="w-4 h-4" />
      Stable
    </span>
  )
}

export default function TrendChart({ data }: TrendChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  const runs = useMemo(
    () => data.runs
      .slice()
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .slice(-20),
    [data.runs],
  )

  if (runs.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-zinc-400">
        No trend data available
      </div>
    )
  }

  // Chart dimensions
  const chartWidth = 600
  const chartHeight = 200
  const paddingLeft = 40
  const paddingRight = 16
  const paddingTop = 16
  const paddingBottom = 48
  const plotWidth = chartWidth - paddingLeft - paddingRight
  const plotHeight = chartHeight - paddingTop - paddingBottom

  const barGap = 4
  const barWidth = Math.max(8, Math.min(32, (plotWidth - barGap * (runs.length - 1)) / runs.length))
  const totalBarsWidth = runs.length * barWidth + (runs.length - 1) * barGap
  const offsetX = paddingLeft + (plotWidth - totalBarsWidth) / 2

  // Y-axis ticks
  const yTicks = [0, 25, 50, 75, 100]

  // Build the line path for pass_rate
  const linePoints = runs.map((run, i) => {
    const cx = offsetX + i * (barWidth + barGap) + barWidth / 2
    const cy = paddingTop + plotHeight - (run.pass_rate / 100) * plotHeight
    return { x: cx, y: cy }
  })
  const linePath = linePoints
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
    .join(' ')

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Pass Rate Trend</h3>
        <TrendIndicator trend={data.trend} />
      </div>

      <div className="relative w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full h-auto min-w-[400px]"
          role="img"
          aria-label="Test history trend chart showing pass rate over time"
        >
          {/* Y-axis gridlines and labels */}
          {yTicks.map((tick) => {
            const y = paddingTop + plotHeight - (tick / 100) * plotHeight
            return (
              <g key={tick}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={chartWidth - paddingRight}
                  y2={y}
                  stroke="currentColor"
                  className="text-zinc-200 dark:text-zinc-700"
                  strokeWidth={1}
                  strokeDasharray={tick === 0 ? undefined : '4 4'}
                />
                <text
                  x={paddingLeft - 6}
                  y={y + 4}
                  textAnchor="end"
                  className="fill-zinc-400 dark:fill-zinc-500"
                  fontSize={10}
                >
                  {tick}%
                </text>
              </g>
            )
          })}

          {/* Bars */}
          {runs.map((run, i) => {
            const barHeight = (run.pass_rate / 100) * plotHeight
            const x = offsetX + i * (barWidth + barGap)
            const y = paddingTop + plotHeight - barHeight
            const isHovered = hoveredIndex === i
            const fill = getVerdictColor(run.verdict, isHovered)
            const opacity = isHovered ? 1 : 0.75

            return (
              <g
                key={`${run.date}-${i}`}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                style={{ cursor: 'pointer' }}
              >
                {/* Invisible wider hit area */}
                <rect
                  x={x - 2}
                  y={paddingTop}
                  width={barWidth + 4}
                  height={plotHeight + paddingBottom}
                  fill="transparent"
                />
                {/* Actual bar */}
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(barHeight, 1)}
                  rx={2}
                  fill={fill}
                  opacity={opacity}
                >
                  <title>{`${formatDate(run.date)}: ${run.pass_rate}% (${run.verdict})`}</title>
                </rect>
              </g>
            )
          })}

          {/* Trend line overlay */}
          {runs.length > 1 && (
            <path
              d={linePath}
              fill="none"
              stroke="currentColor"
              className="text-zinc-500 dark:text-zinc-400"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.6}
            />
          )}

          {/* Line dots */}
          {linePoints.map((p, i) => (
            <circle
              key={`dot-${i}`}
              cx={p.x}
              cy={p.y}
              r={hoveredIndex === i ? 4 : 2.5}
              fill={getVerdictColor(runs[i].verdict)}
              stroke="white"
              strokeWidth={1}
            />
          ))}

          {/* X-axis date labels */}
          {runs.map((run, i) => {
            // Show every label if few points, otherwise skip some
            const showLabel = runs.length <= 10 || i % Math.ceil(runs.length / 10) === 0 || i === runs.length - 1
            if (!showLabel) return null
            const x = offsetX + i * (barWidth + barGap) + barWidth / 2
            return (
              <text
                key={`label-${i}`}
                x={x}
                y={chartHeight - 6}
                textAnchor="middle"
                className="fill-zinc-400 dark:fill-zinc-500"
                fontSize={9}
              >
                {formatDate(run.date)}
              </text>
            )
          })}
        </svg>

        {/* Tooltip overlay */}
        {hoveredIndex !== null && (
          <div
            className="absolute pointer-events-none z-10 px-2.5 py-1.5 rounded-lg shadow-lg text-xs bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 whitespace-nowrap"
            style={{
              left: `${((linePoints[hoveredIndex].x / chartWidth) * 100).toFixed(1)}%`,
              top: `${((linePoints[hoveredIndex].y / chartHeight) * 100 - 12).toFixed(1)}%`,
              transform: 'translateX(-50%)',
            }}
          >
            <div className="font-medium">{formatDate(runs[hoveredIndex].date)}</div>
            <div>
              Pass rate: <span className="font-semibold">{runs[hoveredIndex].pass_rate}%</span>
            </div>
            <div className="capitalize">
              Verdict:{' '}
              <span style={{ color: getVerdictColor(runs[hoveredIndex].verdict) }}>
                {runs[hoveredIndex].verdict}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
