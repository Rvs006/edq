import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { devicesApi } from '@/lib/api'
import {
  Monitor, Plus, Search, Filter, MoreVertical, Wifi, WifiOff,
  ChevronRight, Loader2, X
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

const CATEGORIES = ['camera', 'controller', 'access_control', 'intercom', 'sensor', 'switch', 'gateway', 'other', 'unknown']

export default function DevicesPage() {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const queryClient = useQueryClient()

  const { data: devices, isLoading } = useQuery({
    queryKey: ['devices', search, categoryFilter],
    queryFn: () => devicesApi.list({ search: search || undefined, category: categoryFilter || undefined }).then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => devicesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success('Device deleted')
    },
  })

  return (
    <div className="page-container">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Devices</h1>
          <p className="section-subtitle">Manage network devices for qualification testing</p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> Add Device
        </button>
      </div>

      {/* Search & Filter bar */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
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

      {/* Device list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : devices && devices.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {devices.map((device: any, i: number) => (
            <motion.div
              key={device.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
            >
              <Link to={`/devices/${device.id}`} className="card-hover block p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      device.status === 'online' ? 'bg-emerald-100' : 'bg-slate-100'
                    }`}>
                      {device.status === 'online' ? (
                        <Wifi className="w-4.5 h-4.5 text-emerald-600" />
                      ) : (
                        <Monitor className="w-4.5 h-4.5 text-slate-500" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{device.ip_address}</p>
                      <p className="text-xs text-slate-500">{device.hostname || 'No hostname'}</p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400" />
                </div>

                <div className="space-y-1.5">
                  {device.manufacturer && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Manufacturer</span>
                      <span className="text-slate-700 font-medium">{device.manufacturer}</span>
                    </div>
                  )}
                  {device.model && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Model</span>
                      <span className="text-slate-700 font-medium">{device.model}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500">Category</span>
                    <span className="badge text-[10px] bg-slate-100 text-slate-600 capitalize">
                      {device.category?.replace('_', ' ') || 'Unknown'}
                    </span>
                  </div>
                </div>

                {device.mac_address && (
                  <p className="text-[11px] text-slate-400 font-mono mt-2 pt-2 border-t border-slate-100">
                    MAC: {device.mac_address}
                  </p>
                )}
              </Link>
            </motion.div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Monitor className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-700 mb-1">No devices found</h3>
          <p className="text-sm text-slate-500 mb-4">
            {search || categoryFilter ? 'Try adjusting your search or filters' : 'Add your first device to get started'}
          </p>
          {!search && !categoryFilter && (
            <button onClick={() => setShowAddModal(true)} className="btn-primary">
              <Plus className="w-4 h-4" /> Add Device
            </button>
          )}
        </div>
      )}

      {/* Add Device Modal */}
      <AnimatePresence>
        {showAddModal && (
          <AddDeviceModal onClose={() => setShowAddModal(false)} />
        )}
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
                   sm:w-full sm:max-w-lg bg-white rounded-xl shadow-2xl z-50 overflow-y-auto max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">Add New Device</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100">
            <X className="w-5 h-5 text-slate-500" />
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
                {['camera', 'controller', 'access_control', 'intercom', 'sensor', 'switch', 'gateway', 'other', 'unknown'].map(c => (
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
