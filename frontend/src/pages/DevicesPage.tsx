import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { devicesApi, discoveryApi, projectsApi, getApiErrorMessage } from '@/lib/api'
import type { Device, DiscoveredDevice } from '@/lib/types'
import { Monitor, Plus, Search, Loader2, X, Radar, LayoutGrid, Network, Upload, Download, FileText, CheckCircle2, AlertCircle, GitCompare, Trash2 } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge from '@/components/common/VerdictBadge'
import { toLocalDateOnly } from '@/lib/testContracts'
import CategoryBadge from '@/components/common/CategoryBadge'
import Callout from '@/components/common/Callout'
import TopologyMap from '@/components/devices/TopologyMap'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'
import { useAuth } from '@/contexts/AuthContext'

const CATEGORIES = ['camera', 'controller', 'intercom', 'access_panel', 'lighting', 'hvac', 'iot_sensor', 'meter', 'unknown']

export default function DevicesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlSearch = searchParams.get('search') || ''
  const urlCategory = searchParams.get('category') || ''
  const projectIdFilter = searchParams.get('project_id') || ''
  const [searchInput, setSearchInput] = useState(urlSearch)
  const [search, setSearch] = useState(urlSearch)
  const [categoryFilter, setCategoryFilter] = useState(urlCategory)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (searchInput !== urlSearch) setSearchInput(urlSearch)
    if (search !== urlSearch) setSearch(urlSearch)
    if (categoryFilter !== urlCategory) setCategoryFilter(urlCategory)
  }, [categoryFilter, search, searchInput, urlCategory, urlSearch])

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput)
      setSearchParams((prev) => {
        const params = new URLSearchParams(prev)
        if (searchInput) params.set('search', searchInput); else params.delete('search')
        if (categoryFilter) params.set('category', categoryFilter); else params.delete('category')
        return params
      }, { replace: true })
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput, categoryFilter, setSearchParams])
  const [showAddModal, setShowAddModal] = useState(false)
  const [showDiscoverModal, setShowDiscoverModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [viewMode, setViewMode] = useState<'table' | 'topology'>('table')
  const canDeleteDevices = user?.role === 'admin'

  const { data: devices, isLoading, isError } = useQuery({
    queryKey: ['devices', search, categoryFilter, projectIdFilter],
    queryFn: () => devicesApi.list({
      search: search || undefined,
      category: categoryFilter || undefined,
      project_id: projectIdFilter || undefined,
    }).then(r => r.data),
  })

  useEffect(() => {
    const visibleIds = new Set((devices || []).map((device: Device) => device.id))
    setSelectedIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => visibleIds.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [devices])

  const deleteMutation = useMutation({
    mutationFn: (id: string) => devicesApi.delete(id),
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: ['devices'] })
      const prevQueries = queryClient.getQueriesData<Device[]>({ queryKey: ['devices'] })
      queryClient.setQueriesData<Device[]>({ queryKey: ['devices'] }, (old) =>
        old ? old.filter((d) => d.id !== id) : old
      )
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(id); return next })
      return { prevQueries }
    },
    onError: (_err, _id, context) => {
      if (context?.prevQueries) {
        for (const [key, data] of context.prevQueries) {
          queryClient.setQueryData(key, data)
        }
      }
      toast.error('Failed to delete device')
    },
    onSuccess: () => {
      toast.success('Device deleted')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })

  const handleBulkDelete = async () => {
    if (!canDeleteDevices) return
    if (!confirm(`Delete ${selectedIds.size} device(s)? This cannot be undone.`)) return
    const idsToDelete = Array.from(selectedIds)
    for (const id of idsToDelete) {
      try {
        await deleteMutation.mutateAsync(id)
      } catch {
        break
      }
    }
  }

  return (
    <div className="page-container">
      <div data-tour="devices-toolbar" className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Devices</h1>
          <p className="section-subtitle">Manage known devices first, then use discovery when the address is unknown</p>
        </div>
        <div className="flex gap-2">
          <div className="flex border border-zinc-200 dark:border-slate-700/50 rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`p-2 ${viewMode === 'table' ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300'}`}
              title="Table view"
              aria-label="Table view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('topology')}
              className={`p-2 ${viewMode === 'topology' ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300'}`}
              title="Topology view"
              aria-label="Topology view"
            >
              <Network className="w-4 h-4" />
            </button>
          </div>
          <button type="button" onClick={() => setShowDiscoverModal(true)} className="btn-secondary">
            <Radar className="w-4 h-4" /> Discover
          </button>
          <button type="button" onClick={() => setShowImportModal(true)} className="btn-secondary">
            <Upload className="w-4 h-4" /> Import CSV
          </button>
          <button type="button" onClick={() => setShowAddModal(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Add Device
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by IP, hostname, manufacturer..."
            aria-label="Search devices"
            className="input pl-9"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          aria-label="Filter by category"
          className="input w-full sm:w-48"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => (
            <option key={c} value={c}>{c.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {isError ? (
        <Callout variant="error">Failed to load devices. Please try again.</Callout>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : devices && devices.length > 0 && viewMode === 'topology' ? (
        <div className="card p-4">
          <TopologyMap
            devices={devices}
            onDeviceClick={(d) => navigate(`/devices/${d.id}`)}
          />
        </div>
      ) : devices && devices.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                  <th className="w-10 py-3 px-2">
                    <input type="checkbox" aria-label="Select all devices"
                      checked={devices.length > 0 && selectedIds.size === devices.length}
                      onChange={(e) => setSelectedIds(e.target.checked ? new Set(devices.map((d: Device) => d.id)) : new Set())}
                      className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500" />
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Name</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">IP Address</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Manufacturer</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Model</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden lg:table-cell">Firmware</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Category</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden lg:table-cell">Last Tested</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                {devices.map((device: Device) => (
                  <tr key={device.id} className={`hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors ${selectedIds.has(device.id) ? 'bg-brand-50/50 dark:bg-brand-950/20' : ''}`}>
                    <td className="py-3 px-2">
                      <input type="checkbox" aria-label={`Select ${getPreferredDeviceName(device)}`}
                        checked={selectedIds.has(device.id)}
                        onChange={(e) => {
                          const next = new Set(selectedIds)
                          if (e.target.checked) next.add(device.id); else next.delete(device.id)
                          setSelectedIds(next)
                        }}
                        className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500" />
                    </td>
                    <td className="py-3 px-4">
                      <Link to={`/devices/${device.id}`} className="font-medium text-zinc-900 dark:text-slate-100 hover:text-brand-500">
                        {getPreferredDeviceName(device)}
                      </Link>
                      {getDeviceMetaSummary(device, { includeMac: true }) && (
                        <p className="text-[11px] text-zinc-500 dark:text-slate-400 mt-0.5">
                          {getDeviceMetaSummary(device, { includeMac: true })}
                        </p>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-zinc-600 dark:text-slate-400">
                      {device.ip_address ? device.ip_address : (
                        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-sans">
                          <Loader2 className="w-3 h-3" />
                          Awaiting DHCP
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 hidden md:table-cell">{device.manufacturer || '—'}</td>
                    <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 hidden md:table-cell">{device.model || '—'}</td>
                    <td className="py-3 px-4 text-zinc-500 dark:text-slate-400 text-xs hidden lg:table-cell">{device.firmware_version || '—'}</td>
                    <td className="py-3 px-4">
                      <CategoryBadge category={device.category || 'unknown'} />
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden lg:table-cell">
                      {device.last_tested ? toLocalDateOnly(device.last_tested) : '—'}
                    </td>
                    <td className="py-3 px-4 hidden sm:table-cell">
                      {device.last_verdict ? (
                        <VerdictBadge verdict={device.last_verdict} />
                      ) : (
                        <span className="text-xs text-zinc-400">&mdash;</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Monitor className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">No devices found</h3>
          <p className="text-sm text-zinc-500 mb-4">
            {searchInput || categoryFilter ? 'Try adjusting your search or filters' : 'Add your first device to get started'}
          </p>
          {!searchInput && !categoryFilter && (
            <div className="flex gap-2 justify-center">
              <button type="button" onClick={() => setShowDiscoverModal(true)} className="btn-secondary">
                <Radar className="w-4 h-4" /> Discover Devices
              </button>
              <button type="button" onClick={() => setShowAddModal(true)} className="btn-primary">
                <Plus className="w-4 h-4" /> Add Device
              </button>
            </div>
          )}
        </div>
      )}

      {/* Floating action bar */}
      {selectedIds.size >= 1 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-brand-600 text-white px-5 py-3 rounded-xl shadow-xl flex items-center gap-4 animate-fade-in">
          <span className="text-sm font-medium">{selectedIds.size} device{selectedIds.size !== 1 ? 's' : ''} selected</span>
          {selectedIds.size >= 2 && selectedIds.size <= 5 && (
            <button
              type="button"
              onClick={() => navigate(`/devices/compare?ids=${Array.from(selectedIds).join(',')}`)}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-white text-brand-600 rounded-lg text-sm font-semibold hover:bg-brand-50 transition-colors"
            >
              <GitCompare className="w-4 h-4" /> Compare ({selectedIds.size})
            </button>
          )}
          {canDeleteDevices && (
            <button
              type="button"
              onClick={() => { void handleBulkDelete() }}
              disabled={deleteMutation.isPending}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-red-500 text-white rounded-lg text-sm font-semibold hover:bg-red-600 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" /> Delete
            </button>
          )}
          <button type="button" onClick={() => setSelectedIds(new Set())} className="text-white/70 hover:text-white text-sm">
            Clear
          </button>
        </div>
      )}

      <AnimatePresence>
        {showAddModal && <AddDeviceModal projectId={projectIdFilter || undefined} onClose={() => setShowAddModal(false)} />}
        {showDiscoverModal && <DiscoverModal onClose={() => setShowDiscoverModal(false)} />}
        {showImportModal && <ImportCsvModal initialProjectId={projectIdFilter} onClose={() => setShowImportModal(false)} />}
      </AnimatePresence>
    </div>
  )
}

function DiscoverModal({ onClose }: { onClose: () => void }) {
  const [target, setTarget] = useState('')
  const [mode, setMode] = useState<'ip' | 'subnet'>('ip')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<DiscoveredDevice[] | null>(null)
  const queryClient = useQueryClient()

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResults(null)
    try {
      const payload = mode === 'ip' ? { ip_address: target } : { subnet: target }
      const resp = await discoveryApi.scan(payload)
      setResults(resp.data.devices || [])
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success(`Found ${resp.data.devices_found} device(s)`)
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Discovery failed — is the tools sidecar running?'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-lg bg-white dark:bg-dark-card rounded-lg shadow-2xl overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Discover by IP or Subnet</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleDiscover} className="p-4 space-y-4">
          <Callout variant="info">
            Single IP is best for one directly connected device. Use subnet scan only when the IP is unknown or you are surveying multiple devices.
          </Callout>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('ip')}
              className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                mode === 'ip' ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'border-zinc-200 dark:border-slate-700/50 text-zinc-600 dark:text-slate-400 hover:border-zinc-300 dark:hover:border-slate-600'
              }`}
            >
              Single IP
            </button>
            <button
              type="button"
              onClick={() => setMode('subnet')}
              className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                mode === 'subnet' ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'border-zinc-200 dark:border-slate-700/50 text-zinc-600 dark:text-slate-400 hover:border-zinc-300 dark:hover:border-slate-600'
              }`}
            >
              Subnet Scan
            </button>
          </div>

          <div>
            <label className="label">{mode === 'ip' ? 'IP Address' : 'Subnet (CIDR)'}</label>
            <input
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="input"
              placeholder={mode === 'ip' ? '192.168.1.100' : '192.168.1.0/24'}
              required
            />
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <Radar className="w-4 h-4" />
                Start Discovery
              </>
            )}
          </button>

          {results && results.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-zinc-700 dark:text-slate-300">Discovered Devices</h3>
              {results.map((dev, idx: number) => (
                <div key={idx} className="flex items-center gap-3 p-2.5 bg-zinc-50 dark:bg-slate-800 rounded-lg border border-zinc-100 dark:border-slate-700/50">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${dev.is_new ? 'bg-emerald-500' : 'bg-blue-500'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-800 dark:text-slate-200 truncate">
                      {getPreferredDeviceName(dev)}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {getDeviceMetaSummary(dev, { includeIp: true }) || dev.ip_address} · {dev.category}
                    </p>
                  </div>
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                    dev.is_new ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-300' : 'bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-300'
                  }`}>
                    {dev.is_new ? 'New' : 'Updated'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {results && results.length === 0 && (
            <Callout variant="warning">No devices found at this address. Check the IP and ensure the device is powered on.</Callout>
          )}
        </form>
      </motion.div>
    </div>
  )
}

function isValidIp(ip: string): boolean {
  return /^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$/.test(ip)
}

function isValidMac(mac: string): boolean {
  return /^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/.test(mac)
}

function AddDeviceModal({ onClose, projectId }: { onClose: () => void; projectId?: string }) {
  const [isDhcp, setIsDhcp] = useState(false)
  const [form, setForm] = useState({
    ip_address: '', hostname: '', mac_address: '', manufacturer: '',
    model: '', firmware_version: '', category: 'unknown', location: '',
  })
  const [loading, setLoading] = useState(false)
  const [formErrors, setFormErrors] = useState<{ ip_address?: string; mac_address?: string }>({})
  const queryClient = useQueryClient()

  const validate = (): boolean => {
    const errors: { ip_address?: string; mac_address?: string } = {}
    if (isDhcp) {
      if (!form.mac_address.trim()) {
        errors.mac_address = 'MAC address is required for DHCP devices'
      } else if (!isValidMac(form.mac_address.trim())) {
        errors.mac_address = 'Invalid MAC address (e.g. AA:BB:CC:DD:EE:FF)'
      }
    } else {
      if (!form.ip_address.trim()) {
        errors.ip_address = 'IP address is required'
      } else if (!isValidIp(form.ip_address.trim())) {
        errors.ip_address = 'Invalid IP address format'
      }
      if (form.mac_address.trim() && !isValidMac(form.mac_address.trim())) {
        errors.mac_address = 'Invalid MAC address (e.g. AA:BB:CC:DD:EE:FF)'
      }
    }
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    setLoading(true)
    try {
      const entries = Object.entries(form).filter(([, v]) => v !== '')
      const payload: Record<string, string> = Object.fromEntries(entries)
      if (isDhcp) {
        payload.addressing_mode = 'dhcp'
        delete payload.ip_address
      } else {
        payload.addressing_mode = 'static'
      }
      if (projectId) {
        payload.project_id = projectId
      }
      await devicesApi.create(payload as Parameters<typeof devicesApi.create>[0])
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success('Device added successfully')
      onClose()
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to add device'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-lg bg-white dark:bg-dark-card rounded-lg shadow-2xl overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Add New Device</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {projectId && (
            <Callout variant="info">
              This device will be added to the active project filter.
            </Callout>
          )}
          {/* DHCP toggle */}
          <label className="flex items-center gap-3 p-3 rounded-lg border border-zinc-200 dark:border-slate-700/50 cursor-pointer hover:bg-zinc-50 dark:hover:bg-slate-800/50 transition-colors">
            <input
              type="checkbox"
              checked={isDhcp}
              onChange={(e) => {
                setIsDhcp(e.target.checked)
                setFormErrors({})
              }}
              className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500"
            />
            <div>
              <span className="text-sm font-medium text-zinc-900 dark:text-slate-100">Device uses DHCP (no IP yet)</span>
              <p className="text-xs text-zinc-500 dark:text-slate-400 mt-0.5">
                Add by MAC address only. Discover the IP later when the device comes online.
              </p>
            </div>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {!isDhcp && (
              <div>
                <label className="label">IP Address *</label>
                <input type="text" value={form.ip_address}
                  onChange={(e) => { setForm({ ...form, ip_address: e.target.value }); setFormErrors(prev => ({ ...prev, ip_address: undefined })) }}
                  className={`input ${formErrors.ip_address ? 'border-red-500' : ''}`} placeholder="192.168.1.100" />
                {formErrors.ip_address && <p className="text-xs text-red-500 mt-1">{formErrors.ip_address}</p>}
              </div>
            )}
            <div>
              <label className="label">Hostname</label>
              <input type="text" value={form.hostname}
                onChange={(e) => setForm({ ...form, hostname: e.target.value })}
                className="input" placeholder="cam-lobby-01" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">MAC Address {isDhcp ? '*' : ''}</label>
              <input type="text" value={form.mac_address}
                onChange={(e) => { setForm({ ...form, mac_address: e.target.value }); setFormErrors(prev => ({ ...prev, mac_address: undefined })) }}
                className={`input ${formErrors.mac_address ? 'border-red-500' : ''}`} placeholder="AA:BB:CC:DD:EE:FF" />
              {formErrors.mac_address && <p className="text-xs text-red-500 mt-1">{formErrors.mac_address}</p>}
            </div>
            <div>
              <label className="label">Category</label>
              <select value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                aria-label="Device category"
                className="input">
                {CATEGORIES.map(c => (
                  <option key={c} value={c}>{c.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Manufacturer</label>
              <input type="text" value={form.manufacturer}
                onChange={(e) => setForm({ ...form, manufacturer: e.target.value })}
                className="input" placeholder="Axis, Hikvision..." />
            </div>
            <div>
              <label className="label">Model</label>
              <input type="text" value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                className="input" placeholder="P3245-V" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Firmware Version</label>
              <input type="text" value={form.firmware_version}
                onChange={(e) => setForm({ ...form, firmware_version: e.target.value })}
                className="input" placeholder="10.12.114" />
            </div>
            <div>
              <label className="label">Location</label>
              <input type="text" value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                className="input" placeholder="Building A, Floor 2" />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Add Device
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}

const CSV_TEMPLATE = 'ip_address,hostname,mac_address,manufacturer,model,firmware_version,category,location\n192.168.1.100,cam-lobby-01,AA:BB:CC:DD:EE:FF,Axis,P3245-V,10.12.114,camera,Building A Floor 2\n'

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let inQuotes = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]

    if (inQuotes) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          cell += '"'
          index += 1
        } else {
          inQuotes = false
        }
      } else {
        cell += char
      }
      continue
    }

    if (char === '"') {
      inQuotes = true
    } else if (char === ',') {
      row.push(cell)
      cell = ''
    } else if (char === '\n') {
      row.push(cell)
      if (row.some((value) => value.trim() !== '')) {
        rows.push(row)
      }
      row = []
      cell = ''
    } else if (char !== '\r') {
      cell += char
    }
  }

  if (cell !== '' || row.length > 0) {
    row.push(cell)
    if (row.some((value) => value.trim() !== '')) {
      rows.push(row)
    }
  }

  return rows
}

function parseCsvPreview(text: string): { headers: string[]; rows: string[][] } {
  const parsedRows = parseCsvRows(text)
  if (parsedRows.length === 0) return { headers: [], rows: [] }
  const headers = parsedRows[0].map((header) => header.trim())
  const rows = parsedRows.slice(1, 6)
  return { headers, rows }
}

interface ImportResult {
  imported: number
  skipped: number
  errors: number
  details?: string[]
}

function ImportCsvModal({ onClose, initialProjectId }: { onClose: () => void; initialProjectId?: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<{ headers: string[]; rows: string[][] } | null>(null)
  const [projectId, setProjectId] = useState(initialProjectId || '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const queryClient = useQueryClient()

  const { data: projectsData } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const projects = projectsData?.items || projectsData || []

  const handleFile = (f: File) => {
    if (!f.name.endsWith('.csv')) {
      toast.error('Please select a CSV file')
      return
    }
    setFile(f)
    setResult(null)
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      setPreview(parseCsvPreview(text))
    }
    reader.readAsText(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) handleFile(dropped)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleImport = async () => {
    if (!file) return
    setLoading(true)
    try {
      const resp = await devicesApi.importDevices(file, projectId || undefined)
      const data = resp.data
      const rawErrors = Array.isArray(data.errors) ? data.errors : []
      const errorCount = rawErrors.length > 0
        ? rawErrors.length
        : typeof data.errors === 'number'
          ? data.errors
          : (data.error_count ?? 0)
      setResult({
        imported: data.imported ?? data.created ?? 0,
        skipped: data.skipped ?? 0,
        errors: errorCount,
        details: rawErrors.length > 0
          ? rawErrors.map((entry: Record<string, unknown>) => {
            const parts = [
              entry.row ? `Row ${entry.row}` : null,
              typeof entry.ip_address === 'string' ? entry.ip_address : null,
              typeof entry.error === 'string' ? entry.error : null,
            ].filter(Boolean)
            return parts.join(': ')
          })
          : data.details ?? data.error_details ?? [],
      })
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success(`Import complete: ${data.imported ?? data.created ?? 0} device(s) imported`)
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to import devices'))
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadTemplate = () => {
    const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'edq-device-import-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-lg bg-white dark:bg-dark-card rounded-lg shadow-2xl overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Import Devices from CSV</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Template download */}
          <button
            type="button"
            onClick={handleDownloadTemplate}
            className="flex items-center gap-2 text-sm text-brand-600 dark:text-brand-400 hover:underline"
          >
            <Download className="w-4 h-4" />
            Download CSV template
          </button>

          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={() => setDragOver(false)}
            className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer ${
              dragOver
                ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/20'
                : file
                  ? 'border-emerald-300 bg-emerald-50/50 dark:border-emerald-700 dark:bg-emerald-950/20'
                  : 'border-zinc-300 dark:border-slate-600 hover:border-zinc-400 dark:hover:border-slate-500'
            }`}
            onClick={() => {
              const input = document.createElement('input')
              input.type = 'file'
              input.accept = '.csv'
              input.onchange = (e) => {
                const f = (e.target as HTMLInputElement).files?.[0]
                if (f) handleFile(f)
              }
              input.click()
            }}
          >
            {file ? (
              <div className="flex items-center justify-center gap-2 text-emerald-700 dark:text-emerald-300">
                <FileText className="w-5 h-5" />
                <span className="text-sm font-medium">{file.name}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setFile(null)
                    setPreview(null)
                    setResult(null)
                  }}
                  className="ml-2 p-0.5 rounded hover:bg-emerald-100 dark:hover:bg-emerald-900/30"
                  aria-label="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <Upload className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
                <p className="text-sm text-zinc-600 dark:text-slate-400">
                  Drop a CSV file here, or click to browse
                </p>
                <p className="text-xs text-zinc-400 dark:text-slate-500 mt-1">
                  Accepts .csv files
                </p>
              </>
            )}
          </div>

          {/* Preview table */}
          {preview && preview.rows.length > 0 && (
            <div className="overflow-x-auto">
              <p className="text-xs font-medium text-zinc-500 dark:text-slate-400 mb-2">
                Preview (first {preview.rows.length} row{preview.rows.length !== 1 ? 's' : ''})
              </p>
              <table className="w-full text-xs border border-zinc-200 dark:border-slate-700 rounded-lg overflow-hidden">
                <thead>
                  <tr className="bg-zinc-50 dark:bg-slate-800/50">
                    {preview.headers.map((h, i) => (
                      <th key={i} className="text-left py-1.5 px-2 font-medium text-zinc-500 dark:text-slate-400 whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                  {preview.rows.map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <td key={ci} className="py-1.5 px-2 text-zinc-600 dark:text-slate-400 whitespace-nowrap max-w-[120px] truncate">
                          {cell || '\u2014'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Project selector */}
          <div>
            <label className="label">Assign to Project (optional)</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="input"
              aria-label="Assign to project"
            >
              <option value="">No project</option>
              {(Array.isArray(projects) ? projects : []).map((p: { id: string; name: string }) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          {/* Results summary */}
          {result && (
            <div className="rounded-lg border border-zinc-200 dark:border-slate-700/50 p-3 space-y-2">
              <h3 className="text-sm font-medium text-zinc-700 dark:text-slate-300">Import Results</h3>
              <div className="flex gap-4 text-sm">
                <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  {result.imported} imported
                </span>
                {result.skipped > 0 && (
                  <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                    <AlertCircle className="w-4 h-4" />
                    {result.skipped} skipped
                  </span>
                )}
                {result.errors > 0 && (
                  <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                    <AlertCircle className="w-4 h-4" />
                    {result.errors} error{result.errors !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              {result.details && result.details.length > 0 && (
                <ul className="text-xs text-zinc-500 dark:text-slate-400 space-y-0.5 max-h-24 overflow-y-auto">
                  {result.details.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">
              {result ? 'Close' : 'Cancel'}
            </button>
            {!result && (
              <button
                type="button"
                onClick={handleImport}
                disabled={!file || loading}
                className="btn-primary"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Importing...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    Import
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
