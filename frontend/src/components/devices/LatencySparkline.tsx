import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { devicesApi } from '@/lib/api'
import { Activity, Loader2, WifiOff } from 'lucide-react'

interface PingResponse {
  device_id: string
  ip_address: string
  reachable: boolean
  samples: { seq: number; time_ms: number }[]
  summary: {
    packets_sent: number
    packets_received: number
    packet_loss: number
    min_ms: number | null
    avg_ms: number | null
    max_ms: number | null
  }
}

function getLatencyColor(ms: number): string {
  if (ms < 20) return '#22c55e'
  if (ms < 50) return '#84cc16'
  if (ms < 100) return '#f59e0b'
  if (ms < 200) return '#f97316'
  return '#ef4444'
}

function getLatencyLabel(ms: number | null): string {
  if (ms === null) return '--'
  if (ms < 1) return '<1ms'
  return `${Math.round(ms)}ms`
}

export default function LatencySparkline({ deviceId, hasIp = true }: { deviceId: string; hasIp?: boolean }) {
  const [enabled, setEnabled] = useState(false)

  const { data, isLoading, isError } = useQuery<PingResponse>({
    queryKey: ['device-ping', deviceId],
    queryFn: () => devicesApi.ping(deviceId).then(r => r.data),
    enabled: enabled && hasIp,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: false,
  })

  if (!hasIp) {
    return <span className="text-[10px] text-zinc-300 dark:text-zinc-600">--</span>
  }

  if (!enabled) {
    return (
      <button
        type="button"
        onClick={() => setEnabled(true)}
        className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-brand-500 transition-colors"
        title="Check latency"
      >
        <Activity className="w-3 h-3" />
      </button>
    )
  }

  if (isLoading) {
    return <Loader2 className="w-3 h-3 animate-spin text-zinc-300" />
  }

  if (isError || !data) {
    return (
      <span className="text-[10px] text-zinc-400" title="Ping failed">
        <WifiOff className="w-3 h-3 text-zinc-300" />
      </span>
    )
  }

  if (!data.reachable) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-red-500" title="Device unreachable">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
        <WifiOff className="w-3 h-3" />
      </span>
    )
  }

  const samples = data.samples
  const avg = data.summary.avg_ms
  const color = avg !== null ? getLatencyColor(avg) : '#a1a1aa'

  const width = 56
  const height = 18

  let sparkline = null
  if (samples.length > 1) {
    const maxMs = Math.max(...samples.map(s => s.time_ms), 1)
    const minMs = Math.min(...samples.map(s => s.time_ms))
    const range = Math.max(maxMs - minMs, 0.1)

    const points = samples
      .map((s, i) => {
        const x = (i / (samples.length - 1)) * width
        const y = height - 2 - ((s.time_ms - minMs) / range) * (height - 4)
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')

    const lastSample = samples[samples.length - 1]
    const lastY = height - 2 - ((lastSample.time_ms - minMs) / range) * (height - 4)

    sparkline = (
      <svg width={width} height={height} className="flex-shrink-0">
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={width} cy={lastY} r={2} fill={color} />
      </svg>
    )
  }

  const tooltip = [
    `Min: ${getLatencyLabel(data.summary.min_ms)}`,
    `Avg: ${getLatencyLabel(avg)}`,
    `Max: ${getLatencyLabel(data.summary.max_ms)}`,
    `Loss: ${data.summary.packet_loss}%`,
  ].join(' | ')

  return (
    <span className="inline-flex items-center gap-1.5" title={tooltip}>
      {sparkline}
      <span
        className="text-[11px] font-medium tabular-nums whitespace-nowrap"
        style={{ color }}
      >
        {getLatencyLabel(avg)}
      </span>
    </span>
  )
}
