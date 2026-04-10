import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { devicesApi, getApiErrorMessage } from '@/lib/api'
import { Route, Loader2, AlertTriangle, Server, Globe, ArrowDown } from 'lucide-react'
import toast from 'react-hot-toast'

interface Hop {
  ttl: number
  ip: string
  hostname: string | null
  rtt_ms: number | null
}

interface TracerouteResponse {
  device_id: string
  ip_address: string
  hops: Hop[]
  total_hops: number
}

function getHopLatencyColor(ms: number | null): string {
  if (ms === null) return 'text-zinc-400 dark:text-zinc-500'
  if (ms < 10) return 'text-green-600 dark:text-green-400'
  if (ms < 50) return 'text-lime-600 dark:text-lime-400'
  if (ms < 100) return 'text-amber-600 dark:text-amber-400'
  if (ms < 200) return 'text-orange-600 dark:text-orange-400'
  return 'text-red-600 dark:text-red-400'
}

function getHopBarWidth(ms: number | null, maxMs: number): number {
  if (ms === null || maxMs <= 0) return 0
  return Math.max(4, Math.min(100, (ms / maxMs) * 100))
}

function getHopBarColor(ms: number | null): string {
  if (ms === null) return 'bg-zinc-200 dark:bg-zinc-700'
  if (ms < 10) return 'bg-green-500'
  if (ms < 50) return 'bg-lime-500'
  if (ms < 100) return 'bg-amber-500'
  if (ms < 200) return 'bg-orange-500'
  return 'bg-red-500'
}

export default function NetworkPath({ deviceId, deviceIp }: { deviceId: string; deviceIp: string | null }) {
  const [data, setData] = useState<TracerouteResponse | null>(null)

  const traceMutation = useMutation({
    mutationFn: () => devicesApi.traceroute(deviceId).then(r => r.data),
    onSuccess: (result: TracerouteResponse) => setData(result),
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, 'Traceroute failed. The device may be unreachable.'))
    },
  })

  if (!deviceIp) {
    return (
      <div className="card p-5">
        <h2 className="font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2 mb-3">
          <Route className="w-4 h-4 text-indigo-500" />
          Network Path
        </h2>
        <p className="text-sm text-zinc-400 text-center py-4">
          No IP address assigned. Discover the IP first to trace the network path.
        </p>
      </div>
    )
  }

  const maxRtt = data ? Math.max(...data.hops.map(h => h.rtt_ms ?? 0), 1) : 1

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
          <Route className="w-4 h-4 text-indigo-500" />
          Network Path
        </h2>
        <button
          type="button"
          onClick={() => traceMutation.mutate()}
          disabled={traceMutation.isPending}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
        >
          {traceMutation.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Route className="w-3 h-3" />
          )}
          Trace Route
        </button>
      </div>

      {traceMutation.isPending && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
          <span className="ml-2 text-sm text-zinc-500">Tracing route to {deviceIp}...</span>
        </div>
      )}

      {traceMutation.isError && !data && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          Traceroute failed. Check that the device is reachable and the tools sidecar is running.
        </div>
      )}

      {data && !traceMutation.isPending && (
        <div className="space-y-0">
          {/* Source */}
          <div className="flex items-center gap-3 py-2">
            <div className="w-7 h-7 rounded-full bg-brand-50 dark:bg-brand-950/30 flex items-center justify-center flex-shrink-0">
              <Server className="w-3.5 h-3.5 text-brand-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">EDQ Server</p>
              <p className="text-xs text-zinc-400">Source</p>
            </div>
          </div>

          {data.hops.length === 0 ? (
            <div className="py-4 text-center">
              <p className="text-sm text-zinc-500">No intermediate hops detected (device may be on the same subnet).</p>
            </div>
          ) : (
            data.hops.map((hop, idx) => {
              const isLast = idx === data.hops.length - 1
              return (
                <div key={`hop-${hop.ttl}-${idx}`}>
                  {/* Connector line */}
                  <div className="flex items-center gap-3 py-0.5">
                    <div className="w-7 flex justify-center">
                      <ArrowDown className="w-3 h-3 text-zinc-300 dark:text-zinc-600" />
                    </div>
                    <div className="flex-1 h-px bg-zinc-100 dark:bg-zinc-800" />
                  </div>
                  {/* Hop */}
                  <div className="flex items-center gap-3 py-2">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                      isLast
                        ? 'bg-green-50 dark:bg-green-950/30'
                        : 'bg-zinc-100 dark:bg-zinc-800'
                    }`}>
                      {isLast ? (
                        <Globe className="w-3.5 h-3.5 text-green-500" />
                      ) : (
                        <span className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400">{hop.ttl}</span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-mono text-zinc-900 dark:text-zinc-100 truncate">
                          {hop.ip || '* * *'}
                        </p>
                        {hop.hostname && (
                          <span className="text-xs text-zinc-400 dark:text-zinc-500 truncate hidden sm:inline">
                            ({hop.hostname})
                          </span>
                        )}
                      </div>
                      {/* Latency bar */}
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 h-1.5 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden max-w-[200px]">
                          <div
                            className={`h-full rounded-full transition-all ${getHopBarColor(hop.rtt_ms)}`}
                            style={{ width: `${getHopBarWidth(hop.rtt_ms, maxRtt)}%` }}
                          />
                        </div>
                        <span className={`text-xs font-medium tabular-nums ${getHopLatencyColor(hop.rtt_ms)}`}>
                          {hop.rtt_ms !== null ? `${hop.rtt_ms}ms` : 'timeout'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          )}

          {/* Summary */}
          {data.hops.length > 0 && (
            <div className="mt-3 pt-3 border-t border-zinc-100 dark:border-zinc-800 flex items-center gap-4 text-xs text-zinc-500">
              <span>{data.total_hops} hop{data.total_hops !== 1 ? 's' : ''}</span>
              <span>Destination: {data.ip_address}</span>
              {data.hops.length > 0 && data.hops[data.hops.length - 1].rtt_ms !== null && (
                <span>Total latency: {data.hops[data.hops.length - 1].rtt_ms}ms</span>
              )}
            </div>
          )}
        </div>
      )}

      {!data && !traceMutation.isPending && !traceMutation.isError && (
        <p className="text-sm text-zinc-400 text-center py-4">
          Click &ldquo;Trace Route&rdquo; to visualize the network path to this device
        </p>
      )}
    </div>
  )
}
