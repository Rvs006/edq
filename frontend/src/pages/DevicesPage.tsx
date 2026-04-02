import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { devicesApi, discoveryApi } from '@/lib/api'
import type { Device, DiscoveredDevice } from '@/lib/types'
import { Monitor, Plus, Search, Loader2, X, Radar, LayoutGrid, Network } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge from '@/components/common/VerdictBadge'
import CategoryBadge from '@/components/common/CategoryBadge'
import Callout from '@/components/common/Callout'
import NetworkTopology from '@/components/common/NetworkTopology'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'

const CATEGORIES = ['camera', 'controller', 'access_control', 'intercom', 'sensor', 'switch', 'gateway', 'other', 'unknown']

export default function DevicesPage() {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [showDiscoverModal, setShowDiscoverModal] = useState(false)
  const [viewMode, setViewMode] = useState<'table' | 'topology'>('table')

  const { data: devices, isLoading } = useQuery({
    queryKey: ['devices', search, categoryFilter],
    queryFn: () => devicesApi.list({ search: search || undefined, category: categoryFilter || undefined }).then(r => r.data),
  })

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
              onClick={() => setViewMode('table')}
              className={`p-2 ${viewMode === 'table' ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300'}`}
              title="Table view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('topology')}
              className={`p-2 ${viewMode === 'topology' ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/30 dark:text-brand-300' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300'}`}
              title="Topology view"
            >
              <Network className="w-4 h-4" />
            </button>
          </div>
          <button onClick={() => setShowDiscoverModal(true)} className="btn-secondary">
            <Radar className="w-4 h-4" /> Discover
          </button>
          <button onClick={() => setShowAddModal(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Add Device
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by IP, hostname, manufacturer..."
            className="input pl-9"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="input w-full sm:w-48"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => (
            <option key={c} value={c}>{c.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : devices && devices.length > 0 && viewMode === 'topology' ? (
        <div className="card p-4">
          <NetworkTopology
            devices={devices}
            onDeviceClick={(d) => window.location.href = `/devices/${d.id}`}
          />
        </div>
      ) : devices && devices.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
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
                  <tr key={device.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
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
                    <td className="py-3 px-4 font-mono text-xs text-zinc-600 dark:text-slate-400">{device.ip_address}</td>
                    <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 hidden md:table-cell">{device.manufacturer || '—'}</td>
                    <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 hidden md:table-cell">{device.model || '—'}</td>
                    <td className="py-3 px-4 text-zinc-500 dark:text-slate-400 text-xs hidden lg:table-cell">{device.firmware_version || '—'}</td>
                    <td className="py-3 px-4">
                      <CategoryBadge category={device.category || 'unknown'} />
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden lg:table-cell">
                      {device.last_tested ? new Date(device.last_tested).toLocaleDateString() : '—'}
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
            {search || categoryFilter ? 'Try adjusting your search or filters' : 'Add your first device to get started'}
          </p>
          {!search && !categoryFilter && (
            <div className="flex gap-2 justify-center">
              <button onClick={() => setShowDiscoverModal(true)} className="btn-secondary">
                <Radar className="w-4 h-4" /> Discover Devices
              </button>
              <button onClick={() => setShowAddModal(true)} className="btn-primary">
                <Plus className="w-4 h-4" /> Add Device
              </button>
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {showAddModal && <AddDeviceModal onClose={() => setShowAddModal(false)} />}
        {showDiscoverModal && <DiscoverModal onClose={() => setShowDiscoverModal(false)} />}
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
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Discovery failed — is the tools sidecar running?')
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
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
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

function AddDeviceModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    ip_address: '', hostname: '', mac_address: '', manufacturer: '',
    model: '', firmware_version: '', category: 'unknown', location: '',
  })
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([k, v]) => v !== '' && k !== 'location')
      )
      await devicesApi.create(payload as Parameters<typeof devicesApi.create>[0])
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success('Device added successfully')
      onClose()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Failed to add device')
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
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">IP Address *</label>
              <input type="text" value={form.ip_address}
                onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
                className="input" placeholder="192.168.1.100" required />
            </div>
            <div>
              <label className="label">Hostname</label>
              <input type="text" value={form.hostname}
                onChange={(e) => setForm({ ...form, hostname: e.target.value })}
                className="input" placeholder="cam-lobby-01" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">MAC Address</label>
              <input type="text" value={form.mac_address}
                onChange={(e) => setForm({ ...form, mac_address: e.target.value })}
                className="input" placeholder="AA:BB:CC:DD:EE:FF" />
            </div>
            <div>
              <label className="label">Category</label>
              <select value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
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
