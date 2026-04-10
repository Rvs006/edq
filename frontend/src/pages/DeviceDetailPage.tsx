import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { devicesApi, testRunsApi, cveApi, discoveryApi, getApiErrorMessage } from '@/lib/api'
import type { Device, TestRun, CVELookupResponse } from '@/lib/types'
import {
  ArrowLeft, Monitor, Play, Loader2, Shield, Search,
  ExternalLink, AlertTriangle, Radar, RefreshCw, Pencil, Trash2, X, Check,
  BarChart3,
} from 'lucide-react'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'
import TrendChart from '@/components/devices/TrendChart'
import type { TrendData } from '@/components/devices/TrendChart'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'
import { toLocalDateOnly } from '@/lib/testContracts'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

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

const CATEGORIES = ['camera', 'controller', 'intercom', 'access_panel', 'lighting', 'hvac', 'iot_sensor', 'meter', 'unknown']

const getDeviceField = (device: Device, key: string): string => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const val = (device as any)[key]
  return typeof val === 'string' ? val : val == null ? '' : String(val)
}

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [cveData, setCveData] = useState<CVELookupResponse | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [isSaving, setIsSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const canDeleteDevice = user?.role === 'admin'

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
  const { data: trendData, isLoading: isTrendLoading, isError: isTrendError } = useQuery<TrendData>({
    queryKey: ['device-trends', id],
    queryFn: () => devicesApi.trends(id!).then(r => r.data),
    enabled: !!id,
  })

  const cveMutation = useMutation({
    mutationFn: () => cveApi.lookup({ device_id: id!, max_results: 5 }),
    onSuccess: (res) => setCveData(res.data as CVELookupResponse),
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, 'Failed to query NVD. The device may not have open ports scanned yet.'))
    },
  })

  const autoDetectMutation = useMutation({
    mutationFn: () => discoveryApi.scan({ ip_address: device!.ip_address! }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['device', id] })
      toast.success('Device scan complete')
    },
    onError: (err: unknown) => {
      const message = getApiErrorMessage(err, 'Auto-detect failed. The device may be unreachable — check your network connection.')
      toast.error(message)
    },
  })

  const discoverIpMutation = useMutation({
    mutationFn: () => devicesApi.discoverIp(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['device', id] })
      toast.success('IP address discovered successfully!')
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, 'Failed to discover IP. Ensure the device is on the network.'))
    },
  })

  useEffect(() => {
    setCveData(null)
    cveMutation.reset()
    autoDetectMutation.reset()
    discoverIpMutation.reset()
    setIsEditing(false)
    setShowDeleteConfirm(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const startEditing = () => {
    if (!device) return
    setEditForm({
      hostname: device.hostname || '',
      manufacturer: device.manufacturer || '',
      model: device.model || '',
      firmware_version: device.firmware_version || '',
      category: device.category || 'unknown',
      location: device.location || '',
      mac_address: device.mac_address || '',
      serial_number: device.serial_number || '',
    })
    setIsEditing(true)
  }

  const handleSaveEdit = async () => {
    if (!device) return
    setIsSaving(true)
    try {
      const updates: Record<string, string> = {}
      for (const [key, value] of Object.entries(editForm)) {
        const currentVal = getDeviceField(device, key)
        if (value !== currentVal) {
          updates[key] = value
        }
      }
      if (Object.keys(updates).length > 0) {
        await devicesApi.update(id!, updates)
        queryClient.invalidateQueries({ queryKey: ['device', id] })
        toast.success('Device updated')
      }
      setIsEditing(false)
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to update device'))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!canDeleteDevice) return
    setIsDeleting(true)
    try {
      await devicesApi.delete(id!)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success('Device deleted')
      navigate('/devices')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to delete device'))
    } finally {
      setIsDeleting(false)
      setShowDeleteConfirm(false)
    }
  }

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

  const isDhcpWithoutIp = device.addressing_mode === 'dhcp' && !device.ip_address

  const infoFields = [
    ['IP Address', device.ip_address || (device.addressing_mode === 'dhcp' ? 'Awaiting DHCP assignment' : null)],
    ['Addressing', device.addressing_mode === 'dhcp' ? 'DHCP' : device.addressing_mode === 'static' ? 'Static' : null],
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
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-sm text-zinc-500 mb-4" aria-label="Breadcrumb">
        <Link to="/devices" className="hover:text-zinc-700 dark:hover:text-zinc-300">Devices</Link>
        <span className="text-zinc-300 dark:text-zinc-600">/</span>
        <span className="text-zinc-900 dark:text-zinc-100 font-medium">{getPreferredDeviceName(device)}</span>
      </nav>

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
            {isDhcpWithoutIp && (
              <button
                type="button"
                onClick={() => discoverIpMutation.mutate()}
                disabled={discoverIpMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-amber-400 dark:border-amber-600 bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-950/50 transition-colors disabled:opacity-50"
                title="Scan the network to discover this device's IP address via ARP"
              >
                {discoverIpMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Search className="w-4 h-4" />
                )}
                Discover IP
              </button>
            )}
            <button
              type="button"
              onClick={() => autoDetectMutation.mutate()}
              disabled={autoDetectMutation.isPending || isDhcpWithoutIp}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
              title={isDhcpWithoutIp ? 'Discover the IP first before auto-detecting' : 'Re-scan device to auto-detect manufacturer, model, and open ports'}
            >
              {autoDetectMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Radar className="w-4 h-4" />
              )}
              Auto-Detect
            </button>
            {!isEditing && (
              <button type="button" onClick={startEditing} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors">
                <Pencil className="w-4 h-4" /> Edit
              </button>
            )}
            {canDeleteDevice && (
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                title="Delete device"
                aria-label="Delete device"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
            {isDhcpWithoutIp ? (
              <span className="btn-primary text-sm opacity-50 cursor-not-allowed" title="Discover the device IP before starting tests">
                <Play className="w-4 h-4" /> Start New Test Run
              </span>
            ) : (
              <Link to={`/test-runs?device_id=${device.id}`} className="btn-primary text-sm">
                <Play className="w-4 h-4" /> Start New Test Run
              </Link>
            )}
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
        {isDhcpWithoutIp && (
          <div className="mt-3 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <div>
              <span className="font-medium">Awaiting IP assignment.</span>{' '}
              This DHCP device has no IP address yet. Click &ldquo;Discover IP&rdquo; to scan the network for MAC {device.mac_address}, or wait until the device obtains an address.
            </div>
          </div>
        )}
        {discoverIpMutation.isError && (
          <div className="mt-3 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            IP discovery failed. Ensure the device is powered on and connected to the network.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-1 space-y-5">
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">Device Information</h2>
              {isEditing && (
                <div className="flex gap-2">
                  <button type="button" onClick={() => setIsEditing(false)} className="btn-secondary text-xs py-1 px-2">
                    <X className="w-3 h-3" /> Cancel
                  </button>
                  <button type="button" onClick={handleSaveEdit} disabled={isSaving} className="btn-primary text-xs py-1 px-2">
                    {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Save
                  </button>
                </div>
              )}
            </div>
            {isEditing ? (
              <div className="space-y-3">
                {([
                  ['IP Address', 'ip_address', device.ip_address, true],
                  ['MAC Address', 'mac_address'],
                  ['Hostname', 'hostname'],
                  ['Manufacturer', 'manufacturer'],
                  ['Model', 'model'],
                  ['Firmware', 'firmware_version'],
                  ['Serial Number', 'serial_number'],
                  ['Category', 'category'],
                  ['Location', 'location'],
                ] as [string, string, string?, boolean?][]).map(([label, key, fixedValue, readOnly]) => (
                  <div key={key} className="flex items-center justify-between gap-3 text-sm">
                    <label className="text-zinc-500 dark:text-zinc-400 flex-shrink-0 w-28">{label}</label>
                    {readOnly ? (
                      <span className="text-zinc-900 dark:text-zinc-100 font-medium font-mono text-xs">{fixedValue}</span>
                    ) : key === 'category' ? (
                      <select
                        value={editForm[key] || ''}
                        onChange={(e) => setEditForm({ ...editForm, [key]: e.target.value })}
                        aria-label={label}
                        className="input text-sm flex-1"
                      >
                        {CATEGORIES.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={editForm[key] || ''}
                        onChange={(e) => setEditForm({ ...editForm, [key]: e.target.value })}
                        aria-label={label}
                        className="input text-sm flex-1"
                      />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <dl className="space-y-3">
                {infoFields.map(([label, value]) => (
                  <div key={label} className="flex justify-between text-sm">
                    <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
                    <dd className="text-zinc-900 dark:text-zinc-100 font-medium capitalize">{value || '—'}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>

          {/* Open Ports */}
          <div className="card p-5">
            <h2 className="font-semibold text-zinc-900 dark:text-zinc-100 mb-3 flex items-center gap-2">
              <Shield className="w-4 h-4 text-blue-500" />
              Open Ports {device.open_ports && device.open_ports.length > 0 ? `(${device.open_ports.length})` : ''}
            </h2>
            {device.open_ports && device.open_ports.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-100 dark:border-zinc-800">
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">Port</th>
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">Protocol</th>
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">Service</th>
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">State</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                    {device.open_ports.map((port: { port?: number; protocol?: string; service?: string; state?: string; version?: string }, idx: number) => (
                      <tr key={idx}>
                        <td className="py-1.5 font-mono text-xs text-zinc-900 dark:text-zinc-100">{port.port ?? '—'}</td>
                        <td className="py-1.5 text-xs text-zinc-600 dark:text-zinc-400 uppercase">{port.protocol ?? 'tcp'}</td>
                        <td className="py-1.5 text-xs text-zinc-600 dark:text-zinc-400">{port.service ?? '—'}{port.version ? ` (${port.version})` : ''}</td>
                        <td className="py-1.5">
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-green-50 text-green-600 dark:bg-green-950/30 dark:text-green-400">
                            {port.state ?? 'open'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-zinc-400 dark:text-zinc-500 text-center py-4">
                No port data available. Run Auto-Detect or a network scan to discover open ports.
              </p>
            )}
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
                          {device.hostname || device.manufacturer || 'Device'} – {toLocalDateOnly(run.created_at, { day: 'numeric', month: 'short' })} – Test #{(runs as TestRun[]).indexOf(run) + 1}
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
                        {toLocalDateOnly(run.created_at)}
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

      {/* Test History Trend */}
      <div className="card p-5 mt-5">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-4 h-4 text-brand-500" />
          <h2 className="font-semibold text-zinc-900 dark:text-zinc-100">Test History Trend</h2>
        </div>
        {isTrendLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
            <span className="ml-2 text-sm text-zinc-500">Loading trend data...</span>
          </div>
        ) : isTrendError ? (
          <div className="text-center py-6">
            <AlertTriangle className="w-8 h-8 text-red-300 dark:text-red-500 mx-auto mb-2" />
            <p className="text-sm text-red-600 dark:text-red-400">
              Failed to load trend data. Try refreshing this device.
            </p>
          </div>
        ) : trendData && trendData.runs.length > 0 ? (
          <div>
            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
              <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-lg p-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Total Runs</p>
                <p className="text-lg font-bold text-zinc-900 dark:text-zinc-100">{trendData.runs.length}</p>
              </div>
              <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-lg p-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Best Pass Rate</p>
                <p className="text-lg font-bold text-green-600 dark:text-green-400">
                  {Math.max(...trendData.runs.map(r => r.pass_rate))}%
                </p>
              </div>
              <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-lg p-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Worst Pass Rate</p>
                <p className="text-lg font-bold text-red-600 dark:text-red-400">
                  {Math.min(...trendData.runs.map(r => r.pass_rate))}%
                </p>
              </div>
              <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-lg p-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Current Trend</p>
                <p className="text-lg font-bold capitalize text-zinc-900 dark:text-zinc-100">{trendData.trend}</p>
              </div>
            </div>
            {/* Chart */}
            <TrendChart data={trendData} />
          </div>
        ) : (
          <div className="text-center py-6">
            <BarChart3 className="w-8 h-8 text-zinc-300 dark:text-zinc-600 mx-auto mb-2" />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No trend data yet. Complete test runs to see pass rate trends.
            </p>
          </div>
        )}
      </div>

      {canDeleteDevice && showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowDeleteConfirm(false)} />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-dialog-title"
            aria-describedby="delete-dialog-desc"
            className="relative w-full max-w-sm bg-white dark:bg-dark-card rounded-lg shadow-2xl p-6"
            onKeyDown={(e) => { if (e.key === 'Escape') setShowDeleteConfirm(false) }}
            tabIndex={-1}
            ref={(el) => el?.focus()}
          >
            <h3 id="delete-dialog-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">Delete Device?</h3>
            <p id="delete-dialog-desc" className="text-sm text-zinc-500 mb-4">
              This will permanently delete <strong>{getPreferredDeviceName(device)}</strong> ({device.ip_address}).
              Any test runs associated with this device will become orphaned.
            </p>
            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => setShowDeleteConfirm(false)} className="btn-secondary text-sm">Cancel</button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isDeleting}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
