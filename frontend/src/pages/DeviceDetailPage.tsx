import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { devicesApi, testRunsApi } from '@/lib/api'
import {
  ArrowLeft, Monitor, Wifi, WifiOff, Play, CheckCircle2, XCircle,
  AlertTriangle, Clock, Edit, Loader2
} from 'lucide-react'

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
        <p className="text-slate-500">Device not found</p>
        <Link to="/devices" className="text-brand-500 text-sm mt-2 inline-block">Back to devices</Link>
      </div>
    )
  }

  return (
    <div className="page-container">
      {/* Breadcrumb */}
      <Link to="/devices" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to Devices
      </Link>

      {/* Device header */}
      <div className="card p-5 mb-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
              device.status === 'online' ? 'bg-emerald-100' : 'bg-slate-100'
            }`}>
              {device.status === 'online' ? (
                <Wifi className="w-6 h-6 text-emerald-600" />
              ) : (
                <Monitor className="w-6 h-6 text-slate-500" />
              )}
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">{device.ip_address}</h1>
              <p className="text-sm text-slate-500">{device.hostname || 'No hostname'}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Link to={`/test-runs?device_id=${device.id}`} className="btn-primary text-sm">
              <Play className="w-4 h-4" /> Run Tests
            </Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Device Info */}
        <div className="lg:col-span-1 card p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Device Information</h2>
          <dl className="space-y-3">
            {[
              ['IP Address', device.ip_address],
              ['MAC Address', device.mac_address || '—'],
              ['Hostname', device.hostname || '—'],
              ['Manufacturer', device.manufacturer || '—'],
              ['Model', device.model || '—'],
              ['Firmware', device.firmware_version || '—'],
              ['Category', device.category?.replace('_', ' ') || 'Unknown'],
              ['Location', device.location || '—'],
              ['OUI Vendor', device.oui_vendor || '—'],
              ['Status', device.status],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between text-sm">
                <dt className="text-slate-500">{label}</dt>
                <dd className="text-slate-900 font-medium capitalize">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {/* Test History */}
        <div className="lg:col-span-2 card">
          <div className="p-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Test History</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {runs && runs.length > 0 ? (
              runs.map((run: any) => (
                <Link
                  key={run.id}
                  to={`/test-runs/${run.id}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors"
                >
                  <VerdictIcon verdict={run.overall_verdict} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900">Run {run.id.slice(0, 8)}</p>
                    <p className="text-xs text-slate-500">
                      {run.passed_tests} passed, {run.failed_tests} failed, {run.advisory_tests} advisories
                    </p>
                  </div>
                  <div className="text-right">
                    <span className={`badge text-[10px] ${
                      run.status === 'completed' ? 'badge-pass' :
                      run.status === 'running' ? 'badge-pending' : 'badge-na'
                    }`}>{run.status}</span>
                    <p className="text-xs text-slate-400 mt-1">
                      {new Date(run.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </Link>
              ))
            ) : (
              <div className="p-8 text-center">
                <Play className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-500">No test runs for this device</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function VerdictIcon({ verdict }: { verdict: string | null }) {
  if (verdict === 'pass') return <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
  if (verdict === 'fail') return <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
  if (verdict === 'advisory') return <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
  return <Clock className="w-5 h-5 text-blue-400 flex-shrink-0" />
}
