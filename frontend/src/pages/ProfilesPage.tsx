import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { profilesApi } from '@/lib/api'
import { Server, Plus, Loader2, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

const CATEGORIES = ['camera', 'controller', 'access_control', 'intercom', 'sensor', 'switch', 'gateway', 'other']

export default function ProfilesPage() {
  const [showCreate, setShowCreate] = useState(false)
  const { data: profiles, isLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => profilesApi.list().then(r => r.data),
  })

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Device Profiles</h1>
          <p className="section-subtitle">Manufacturer and model categorisation with default settings</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> New Profile
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : profiles && profiles.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {profiles.map((p: any) => (
            <div key={p.id} className="card-hover p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                  <Server className="w-5 h-5 text-purple-600" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{p.name}</h3>
                  <p className="text-xs text-slate-500">{p.manufacturer}</p>
                </div>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Category</span>
                  <span className="text-slate-700 capitalize">{p.category?.replace('_', ' ')}</span>
                </div>
                {p.model_pattern && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Model Pattern</span>
                    <span className="text-slate-700 font-mono">{p.model_pattern}</span>
                  </div>
                )}
                {p.description && (
                  <p className="text-slate-500 mt-2 pt-2 border-t border-slate-100">{p.description}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Server className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-700 mb-1">No device profiles</h3>
          <p className="text-sm text-slate-500 mb-4">Create profiles to auto-categorise discovered devices</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> New Profile
          </button>
        </div>
      )}

      <AnimatePresence>
        {showCreate && <CreateProfileModal onClose={() => setShowCreate(false)} />}
      </AnimatePresence>
    </div>
  )
}

function CreateProfileModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: '', manufacturer: '', model_pattern: '', category: 'camera', description: '' })
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await profilesApi.create(form)
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      toast.success('Profile created')
      onClose()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create profile')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-50" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="fixed inset-4 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2
                   sm:w-full sm:max-w-md bg-white rounded-xl shadow-2xl z-50"
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">New Device Profile</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100"><X className="w-5 h-5 text-slate-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="label">Profile Name</label>
            <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="input" placeholder="Axis P-Series Cameras" required />
          </div>
          <div>
            <label className="label">Manufacturer</label>
            <input type="text" value={form.manufacturer} onChange={(e) => setForm({ ...form, manufacturer: e.target.value })}
              className="input" placeholder="Axis Communications" required />
          </div>
          <div>
            <label className="label">Model Pattern (regex)</label>
            <input type="text" value={form.model_pattern} onChange={(e) => setForm({ ...form, model_pattern: e.target.value })}
              className="input font-mono text-sm" placeholder="P3[0-9]{3}.*" />
          </div>
          <div>
            <label className="label">Category</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="input">
              {CATEGORIES.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Description</label>
            <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="input" placeholder="Axis fixed dome cameras" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Profile
            </button>
          </div>
        </form>
      </motion.div>
    </>
  )
}
