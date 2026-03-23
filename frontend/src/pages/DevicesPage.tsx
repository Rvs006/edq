import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { devicesApi } from '@/lib/api'
import { Monitor, Plus, Search, Loader2, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge from '@/components/common/VerdictBadge'

const CATEGORIES = ['camera', 'controller', 'access_control', 'intercom', 'sensor', 'switch', 'gateway', 'other', 'unknown']

export default function DevicesPage() {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  const { data: devices, isLoading } = useQuery({
    queryKey: ['devices', search, categoryFilter],
    queryFn: () => devicesApi.list({ search: search || undefined, category: categoryFilter || undefined }).then(r => r.data),
  })

  return (
    <div className="page-container">
      <div data-tour="devices-toolbar" className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Devices</h1>
          <p className="section-subtitle">Manage network devices for qualification testing</p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> Add Device
        </button>
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
      ) : devices && devices.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Name</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">IP Address</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden md:table-cell">Manufacturer</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden md:table-cell">Model</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden lg:table-cell">Firmware</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Category</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden lg:table-cell">Last Tested</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden sm:table-cell">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {devices.map((device: any) => (
                  <tr key={device.id} className="hover:bg-zinc-50 transition-colors">
                    <td className="py-3 px-4">
                      <Link to={`/devices/${device.id}`} className="font-medium text-zinc-900 hover:text-brand-500">
                        {device.hostname || device.name || device.ip_address}
                      </Link>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-zinc-600">{device.ip_address}</td>
                    <td className="py-3 px-4 text-zinc-600 hidden md:table-cell">{device.manufacturer || '—'}</td>
                    <td className="py-3 px-4 text-zinc-600 hidden md:table-cell">{device.model || '—'}</td>
                    <td className="py-3 px-4 text-zinc-500 text-xs hidden lg:table-cell">{device.firmware_version || '—'}</td>
                    <td className="py-3 px-4">
                      <span className="badge text-[10px] bg-zinc-100 text-zinc-600 capitalize">
                        {device.category?.replace(/_/g, ' ') || 'Unknown'}
                      </span>
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
          <h3 className="text-base font-semibold text-zinc-700 mb-1">No devices found</h3>
          <p className="text-sm text-zinc-500 mb-4">
            {search || categoryFilter ? 'Try adjusting your search or filters' : 'Add your first device to get started'}
          </p>
          {!search && !categoryFilter && (
            <button onClick={() => setShowAddModal(true)} className="btn-primary">
              <Plus className="w-4 h-4" /> Add Device
            </button>
          )}
        </div>
      )}

      <AnimatePresence>
        {showAddModal && <AddDeviceModal onClose={() => setShowAddModal(false)} />}
      </AnimatePresence>
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
      await devicesApi.create(form)
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success('Device added successfully')
      onClose()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to add device')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-50" onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="fixed inset-4 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2
                   sm:w-full sm:max-w-lg bg-white rounded-lg shadow-2xl z-50 overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200">
          <h2 className="text-lg font-semibold text-zinc-900">Add New Device</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100">
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
    </>
  )
}
