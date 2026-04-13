import { motion } from 'framer-motion'

interface SegmentedProgressBarProps {
  total: number
  segments: {
    pass: number
    fail: number
    advisory: number
    info?: number
    manual_pending?: number
    pending: number
    running: number
  }
  className?: string
}

export default function SegmentedProgressBar({ total, segments, className = '' }: SegmentedProgressBarProps) {
  if (total === 0) return null

  const pct = (n: number) => `${(n / total) * 100}%`

  const segmentConfig = [
    { key: 'pass', count: segments.pass, color: 'bg-emerald-500', label: 'Pass' },
    { key: 'fail', count: segments.fail, color: 'bg-red-500', label: 'Fail' },
    { key: 'advisory', count: segments.advisory, color: 'bg-amber-500', label: 'Advisory' },
    { key: 'info', count: segments.info || 0, color: 'bg-sky-400', label: 'Info/N/A' },
    { key: 'manual_pending', count: segments.manual_pending || 0, color: 'bg-yellow-500', label: 'Manual Pending' },
    { key: 'running', count: segments.running, color: 'bg-blue-500 animate-pulse', label: 'Running' },
    { key: 'pending', count: segments.pending, color: 'bg-zinc-200', label: 'Pending' },
  ]

  return (
    <div className={className}>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-zinc-100 gap-px">
        {segmentConfig.map(seg =>
          seg.count > 0 ? (
            <motion.div
              key={seg.key}
              className={`${seg.color} transition-all duration-500 ease-out first:rounded-l-full last:rounded-r-full`}
              animate={{ width: pct(seg.count) }}
              transition={{ type: 'tween', duration: 0.2 }}
              title={`${seg.label}: ${seg.count}`}
            />
          ) : null
        )}
      </div>
      <div className="flex items-center gap-3 mt-1.5 flex-wrap">
        {segmentConfig.map(seg =>
          seg.count > 0 ? (
            <span key={seg.key} className="flex items-center gap-1 text-[10px] text-zinc-500">
              <span className={`w-2 h-2 rounded-full ${seg.color.replace(' animate-pulse', '')}`} />
              {seg.label} ({seg.count})
            </span>
          ) : null
        )}
      </div>
    </div>
  )
}
