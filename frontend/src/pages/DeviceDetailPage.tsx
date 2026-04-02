import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { devicesApi, testRunsApi, cveApi, discoveryApi } from '@/lib/api'
import type { TestRun, CVELookupResponse } from '@/lib/types'
import {
  ArrowLeft, Monitor, Play, Loader2, Shield, Search,
  ExternalLink, AlertTriangle, Radar, RefreshCw,
} from 'lucide-react'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-100 text-red-800',
    HIGH: 'bg-orange-100 text-orange-800',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    LOW: 'bg-green-100 text-green-800',
    UNKNOWN: 'bg-zinc-100 text-zinc-600',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${colors[severity] || colors.UNKNOWN}`}>
      {severity}
    </span>
  )
}

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [cveData, setCveData] = useState<CVELookupResponse | null>(null)

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

  const cveMutation = useMutation({
    mutationFn: () => cveApi.lookup({ device_id: id!, max_results: 5 }),
    onSuccess: (res) => setCveData(res.data as CVELookupResponse),
  })

  const autoDetectMutation = useMutation({
    mutationFn: () => discoveryApi.scan({ ip_address: device!.ip_address }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['device', id] })
    },
  })

  useEffect(() => {
    setCveData(null)
    cveMutation.reset()
    autoDetectMutation.reset()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

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
            <div className="w-12 h-12 rounded-lg bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center">
              <Monitor className="w-6 h-6 text-zinc-500 dark:text-zinc-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100">{getPreferredDeviceName(device)}</h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">{getDeviceMetaSummary(device, { includeIp: true, includeMac: true }) || device.ip_address}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => autoDetectMutation.mutate()}
              disabled={autoDetectMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
              title="Re-scan device to auto-detect manufacturer, model, and open ports"
            >
              {autoDetectMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Radar className="w-4 h-4" />
              )}
              Auto-Detect
            </button>
            <Link to={`/test-runs?device_id=${device.id}`} className="btn-primary text-sm">
              <Play className="w-4 h-4" /> Start New Test Run
            </Link>
          </div>
        </div>
        {autoDetectMutation.isSuccess && (
          <div className="mt-3 p-3 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-400 flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Device re-scanned successfully. Information updated.
          </div>
        )}
        {autoDetectMutation.isError && (
          <div className="mt-3 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Auto-detect failed. Make sure the tools sidecar is running and the device is reachable.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-1 space-y-5">
          <div className="card p-5">
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100 mb-4">Device Information</h2>
            <dl className="space-y-3">
              {infoFields.map(([label, value]) => (
                <div key={label} className="flex justify-between text-sm">
                  <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
                  <dd className="text-zinc-900 dark:text-zinc-100 font-medium capitalize">{value || '—'}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* CVE Vulnerability Lookup */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                <Shield className="w-4 h-4 text-red-500" />
                CVE Vulnerabilities
              </h2>
              <button
                onClick={() => cveMutation.mutate()}
                disabled={cveMutation.isPending}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
              >
                {cveMutation.isPending ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Search className="w-3 h-3" />
                )}
                Scan NVD
              </button>
            </div>

            {cveMutation.isPending && (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
                <span className="ml-2 text-sm text-zinc-500">Querying NVD database...</span>
              </div>
            )}

            {cveMutation.isError && (
              <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg p-3">
                Failed to query NVD. The device may not have open ports scanned yet.
              </div>
            )}

            {cveData && !cveMutation.isPending && !cveMutation.isError && (
              <>
                {cveData.total_cves === 0 ? (
                  <div className="text-center py-4">
                    <Shield className="w-8 h-8 text-green-400 mx-auto mb-2" />
                    <p className="text-sm text-zinc-500">No known CVEs found</p>
                    <p className="text-xs text-zinc-400 mt-1">
                      {device.open_ports?.length
                        ? `Checked ${device.open_ports.length} service(s)`
                        : 'No open ports detected \u2014 run a scan first'}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-zinc-500">
                      Found {cveData.total_cves} CVE(s) across {cveData.results.length} service(s)
                    </p>
                    {cveData.results.map((svc) => (
                      <div key={`${svc.port}-${svc.service}`} className="border border-zinc-100 dark:border-zinc-700 rounded-lg p-3">
                        <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                          Port {svc.port} \u2014 {svc.service} ({svc.version})
                        </p>
                        <div className="space-y-2">
                          {svc.cves.map((cve) => (
                            <div key={cve.id} className="flex items-start gap-2">
                              <SeverityBadge severity={cve.severity} />
                              <div className="flex-1 min-w-0">
                                <a
                                  href={cve.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs font-mono text-brand-600 hover:underline flex items-center gap-1"
                                >
                                  {cve.id} <ExternalLink className="w-3 h-3" />
                                </a>
                                <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{cve.description}</p>
                                {cve.cvss_score !== null && (
                                  <p className="text-xs text-zinc-400 mt-0.5">CVSS: {cve.cvss_score}</p>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {!cveData && !cveMutation.isPending && !cveMutation.isError && (
              <p className="text-sm text-zinc-400 text-center py-4">
                Click &ldquo;Scan NVD&rdquo; to check for known vulnerabilities
              </p>
            )}
          </div>
        </div>

        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between p-4 border-b border-zinc-100 dark:border-zinc-800">
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">Test History</h2>
          </div>
          {runs && runs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Run</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Status</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Verdict</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">Tests</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {runs.map((run: TestRun) => (
                    <tr key={run.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors">
                      <td className="py-2.5 px-4">
                        <Link to={`/test-runs/${run.id}`} className="font-medium text-zinc-900 dark:text-zinc-100 hover:text-brand-500">
                          {run.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="py-2.5 px-4"><StatusBadge status={run.status} /></td>
                      <td className="py-2.5 px-4">
                        {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                      </td>
                      <td className="py-2.5 px-4 text-xs text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">
                        {run.passed_tests ?? 0}P / {run.failed_tests ?? 0}F / {run.advisory_tests ?? 0}A
                      </td>
                      <td className="py-2.5 px-4 text-xs text-zinc-500 dark:text-zinc-400">
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
