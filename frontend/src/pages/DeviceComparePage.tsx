import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { devicesApi, testRunsApi } from '@/lib/api'
import type { Device, TestRun } from '@/lib/types'
import { ArrowLeft, Loader2, AlertCircle } from 'lucide-react'
import VerdictBadge from '@/components/common/VerdictBadge'
import CategoryBadge from '@/components/common/CategoryBadge'
import { getPreferredDeviceName } from '@/lib/deviceLabels'

/** Returns the set of values for a given row across all devices. */
function uniqueValues(devices: Device[], accessor: (d: Device) => string): Set<string> {
  return new Set(devices.map(accessor))
}

/** True when not all devices share the same value for a field. */
function hasDifference(devices: Device[], accessor: (d: Device) => string): boolean {
  const values = uniqueValues(devices, accessor)
  return values.size > 1
}

/** Format open ports into a compact display string. */
function formatPorts(device: Device): string {
  if (!device.open_ports || device.open_ports.length === 0) return 'None'
  return [...device.open_ports]
    .sort((left, right) => left.port - right.port || left.protocol.localeCompare(right.protocol))
    .map((p) => `${p.port}/${p.protocol}`)
    .join(', ')
}

/** Compute pass rate from the most recent completed test run. */
function computePassRate(runs: TestRun[]): string | null {
  const completed = runs.find((r) => r.status === 'completed')
  if (!completed) return null
  const total = completed.total_tests ?? 0
  const passed = completed.passed_tests ?? 0
  if (total === 0) return null
  return `${Math.round((passed / total) * 100)}%`
}

/** Background highlight class when a row has differences. */
const DIFF_ROW_CLASS = 'bg-amber-50/60 dark:bg-amber-950/20'

interface RowDef {
  label: string
  accessor: (device: Device, extras: { passRate: string | null }) => string
  diffAccessor?: (device: Device) => string
  renderCell?: (device: Device, extras: { passRate: string | null }) => React.ReactNode
}

const rows: RowDef[] = [
  {
    label: 'IP Address',
    accessor: (d) => d.ip_address || '—',
    diffAccessor: (d) => d.ip_address || '',
  },
  {
    label: 'MAC Address',
    accessor: (d) => d.mac_address || '—',
    diffAccessor: (d) => d.mac_address || '',
  },
  {
    label: 'Manufacturer',
    accessor: (d) => d.manufacturer || '—',
    diffAccessor: (d) => d.manufacturer || '',
  },
  {
    label: 'Model',
    accessor: (d) => d.model || '—',
    diffAccessor: (d) => d.model || '',
  },
  {
    label: 'OS / Fingerprint',
    accessor: (d) => d.os_fingerprint || '—',
    diffAccessor: (d) => d.os_fingerprint || '',
  },
  {
    label: 'Category',
    accessor: (d) => d.category || 'unknown',
    diffAccessor: (d) => d.category || 'unknown',
    renderCell: (d) => <CategoryBadge category={d.category || 'unknown'} />,
  },
  {
    label: 'Open Ports',
    accessor: (d) => formatPorts(d),
    diffAccessor: (d) => formatPorts(d),
  },
  {
    label: 'Last Verdict',
    accessor: (d) => d.last_verdict || '—',
    diffAccessor: (d) => d.last_verdict || '',
    renderCell: (d) =>
      d.last_verdict ? (
        <VerdictBadge verdict={d.last_verdict} showIcon />
      ) : (
        <span className="text-xs text-zinc-400 dark:text-slate-500">&mdash;</span>
      ),
  },
  {
    label: 'Pass Rate',
    accessor: (_d, { passRate }) => passRate || '—',
    renderCell: (_d, { passRate }) => {
      if (!passRate) return <span className="text-xs text-zinc-400 dark:text-slate-500">&mdash;</span>
      const pct = parseInt(passRate, 10)
      let colorClass = 'text-zinc-600 dark:text-slate-400'
      if (pct >= 80) colorClass = 'text-emerald-600 dark:text-emerald-400'
      else if (pct >= 50) colorClass = 'text-amber-600 dark:text-amber-400'
      else colorClass = 'text-red-600 dark:text-red-400'
      return <span className={`text-sm font-semibold ${colorClass}`}>{passRate}</span>
    },
  },
]

export default function DeviceComparePage() {
  const [searchParams] = useSearchParams()
  const ids = useMemo(() => {
    const raw = searchParams.get('ids') || ''
    return Array.from(new Set(raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)))
  }, [searchParams])
  const validationMessage = ids.length < 2
    ? 'Select between 2 and 5 unique devices to compare.'
    : ids.length > 5
      ? 'You can compare up to 5 devices at a time.'
      : null

  // Fetch each device in parallel
  const deviceQueries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['device', id],
      queryFn: () => devicesApi.get(id).then((r) => r.data),
      enabled: !validationMessage,
    })),
  })

  // Fetch the latest test runs per device for pass-rate calculation
  const runQueries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['test-runs', { device_id: id, status: 'completed', limit: 1 }],
      queryFn: () =>
        testRunsApi.list({ device_id: id, status: 'completed', limit: 1 }).then((r) => r.data as unknown as TestRun[]),
      enabled: !validationMessage,
    })),
  })

  const isLoading = deviceQueries.some((q) => q.isLoading) || runQueries.some((q) => q.isLoading)
  const hasError = deviceQueries.some((q) => q.isError) || runQueries.some((q) => q.isError)

  const devices = deviceQueries
    .filter((q) => q.data)
    .map((q) => q.data as Device)

  const passRates = useMemo(() => {
    const map: Record<string, string | null> = {}
    ids.forEach((id, idx) => {
      const runs = (runQueries[idx]?.data as TestRun[] | undefined) || []
      map[id] = computePassRate(runs)
    })
    return map
  }, [ids, runQueries])

  if (validationMessage) {
    return (
      <div className="page-container">
        <div className="card p-12 text-center">
          <AlertCircle className="w-10 h-10 text-zinc-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">
            Invalid comparison
          </h3>
          <p className="text-sm text-zinc-500 dark:text-slate-400 mb-4">
            {validationMessage}
          </p>
          <Link to="/devices" className="btn-primary inline-flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" />
            Back to Devices
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Device Comparison</h1>
          <p className="section-subtitle">
            Comparing {devices.length} device{devices.length !== 1 ? 's' : ''} side by side
          </p>
        </div>
        <Link
          to="/devices"
          className="btn-secondary inline-flex items-center gap-2 self-start"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Devices
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : hasError ? (
        <div className="card p-8 text-center">
          <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-red-600 dark:text-red-400">
            Failed to load one or more comparison datasets. Check the IDs and try again.
          </p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 whitespace-nowrap sticky left-0 bg-zinc-50/50 dark:bg-slate-800/50 z-10">
                    Property
                  </th>
                  {devices.map((device) => (
                    <th
                      key={device.id}
                      className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 min-w-[180px]"
                    >
                      <Link
                        to={`/devices/${device.id}`}
                        className="text-brand-600 dark:text-brand-400 hover:underline font-semibold text-sm"
                      >
                        {getPreferredDeviceName(device)}
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                {rows.map((row) => {
                  const isDiff =
                    row.diffAccessor && devices.length > 1
                      ? hasDifference(devices, row.diffAccessor)
                      : false

                  return (
                    <tr
                      key={row.label}
                      className={`${isDiff ? DIFF_ROW_CLASS : ''} transition-colors`}
                    >
                      <td className="py-3 px-4 font-medium text-zinc-700 dark:text-slate-300 whitespace-nowrap sticky left-0 bg-white dark:bg-dark-card z-10">
                        <span className="flex items-center gap-2">
                          {row.label}
                          {isDiff && (
                            <span
                              className="inline-block w-2 h-2 rounded-full bg-amber-400 dark:bg-amber-500"
                              title="Values differ across devices"
                            />
                          )}
                        </span>
                      </td>
                      {devices.map((device) => {
                        const extras = { passRate: passRates[device.id] ?? null }
                        return (
                          <td
                            key={device.id}
                            className="py-3 px-4 text-zinc-600 dark:text-slate-400"
                          >
                            {row.renderCell
                              ? row.renderCell(device, extras)
                              : row.accessor(device, extras)}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
