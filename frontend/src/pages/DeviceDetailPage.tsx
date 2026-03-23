import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { devicesApi, testRunsApi } from '@/lib/api'
import { ArrowLeft, Monitor, Play, Loader2 } from 'lucide-react'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: device, isLoading } = useQuery({
    queryKey: ['device', id],
    queryFn: () => devicesApi.get(id!).then(r => r.data),
    enabled: !!id,
  })
  const { data: runs } = useQuery({
    queryKey: ['device-runs', id],
    queryFn: () => testRunsApi.list({ device_id: id }).then(r => r.data),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="page-container flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!device) {
    return (
      <div className="page-container text-center py-20">
        <p className="text-zinc-500">Device not found</p>
        <Link to="/devices" className="text-brand-500 text-sm mt-2 inline-block">Back to devices</Link>
      </div>
    )
  }

  const infoFields = [
    ['IP Address', device.ip_address],
    ['MAC Address', device.mac_address],
    ['Hostname', device.hostname || device.name],
    ['Manufacturer', device.manufacturer],
    ['Model', device.model],
    ['Firmware', device.firmware_version],
    ['Serial Number', device.serial_number],
    ['Category', device.category?.replace(/_/g, ' ')],
    ['Location', device.location],
    ['OUI Vendor', device.oui_vendor],
  ]

  return (
    <div className="page-container">
      <Link to="/devices" className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to Devices
      </Link>

      <div className="card p-5 mb-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-zinc-100 flex items-center justify-center">
              <Monitor className="w-6 h-6 text-zinc-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-zinc-900">{device.hostname || device.name || device.ip_address}</h1>
              <p className="text-sm text-zinc-500">{device.ip_address} {device.manufacturer ? `· ${device.manufacturer}` : ''}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Link to={`/test-runs?device_id=${device.id}`} className="btn-primary text-sm">
              <Play className="w-4 h-4" /> Start New Test Run
            </Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-1 card p-5">
          <h2 className="font-semibold text-zinc-900 mb-4">Device Information</h2>
          <dl className="space-y-3">
            {infoFields.map(([label, value]) => (
              <div key={label} className="flex justify-between text-sm">
                <dt className="text-zinc-500">{label}</dt>
                <dd className="text-zinc-900 font-medium capitalize">{value || '—'}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between p-4 border-b border-zinc-100">
            <h2 className="font-semibold text-zinc-900">Test History</h2>
          </div>
          {runs && runs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100">
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500">Run</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500">Status</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500">Verdict</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 hidden sm:table-cell">Tests</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50">
                  {runs.map((run: any) => (
                    <tr key={run.id} className="hover:bg-zinc-50 transition-colors">
                      <td className="py-2.5 px-4">
                        <Link to={`/test-runs/${run.id}`} className="font-medium text-zinc-900 hover:text-brand-500">
                          {run.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="py-2.5 px-4"><StatusBadge status={run.status} /></td>
                      <td className="py-2.5 px-4">
                        {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                      </td>
                      <td className="py-2.5 px-4 text-xs text-zinc-500 hidden sm:table-cell">
                        {run.passed_tests ?? 0}P / {run.failed_tests ?? 0}F / {run.advisory_tests ?? 0}A
                      </td>
                      <td className="py-2.5 px-4 text-xs text-zinc-500">
                        {new Date(run.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center">
              <Play className="w-8 h-8 text-zinc-300 mx-auto mb-2" />
              <p className="text-sm text-zinc-500">No test runs for this device</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
