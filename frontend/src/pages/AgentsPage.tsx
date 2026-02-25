import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi } from '@/lib/api'
import { Wifi, WifiOff, Plus, Trash2, Copy, Loader2, X, Clock, Activity } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

export default function AgentsPage() {
  const [showRegister, setShowRegister] = useState(false)
  const queryClient = useQueryClient()

  const { data: agents, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentsApi.list().then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => agentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.success('Agent removed')
    },
  })

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Agents</h1>
          <p className="section-subtitle">Manage distributed testing agents across network segments</p>
        </div>
        <button onClick={() => setShowRegister(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> Register Agent
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : agents && agents.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {agents.map((agent: any) => {
            const isOnline = agent.status === 'online'
            return (
              <div key={agent.id} className="card-hover p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      isOnline ? 'bg-emerald-100' : 'bg-slate-100'
                    }`}>
                      {isOnline ? (
                        <Wifi className="w-5 h-5 text-emerald-600" />
                      ) : (
                        <WifiOff className="w-5 h-5 text-slate-400" />
                      )}
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900">{agent.name}</h3>
                      <span className={`badge text-[10px] ${isOnline ? 'badge-pass' : 'badge-na'}`}>
                        {agent.status}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => deleteMutation.mutate(agent.id)}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-1.5 text-xs">
                  {agent.hostname && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Hostname</span>
                      <span className="text-slate-700">{agent.hostname}</span>
                    </div>
                  )}
                  {agent.ip_address && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">IP Address</span>
                      <span className="text-slate-700 font-mono">{agent.ip_address}</span>
                    </div>
                  )}
                  {agent.version && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Version</span>
                      <span className="text-slate-700">{agent.version}</span>
                    </div>
                  )}
                  {agent.last_heartbeat && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Last Seen</span>
                      <span className="text-slate-700">{new Date(agent.last_heartbeat).toLocaleString()}</span>
                    </div>
                  )}
                </div>

                {/* API Key */}
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">API Key</span>
                    <button
                      onClick={() => { navigator.clipboard.writeText(agent.api_key); toast.success('API key copied') }}
                      className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-600"
                    >
                      <Copy className="w-3 h-3" /> Copy
                    </button>
                  </div>
                  <p className="text-xs font-mono text-slate-400 truncate mt-0.5">{agent.api_key}</p>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Wifi className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-700 mb-1">No agents registered</h3>
          <p className="text-sm text-slate-500 mb-4">Register an agent to enable distributed testing</p>
          <button onClick={() => setShowRegister(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Register Agent
          </button>
        </div>
      )}

      <AnimatePresence>
        {showRegister && <RegisterAgentModal onClose={() => setShowRegister(false)} />}
      </AnimatePresence>
    </div>
  )
}

function RegisterAgentModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: '', hostname: '', ip_address: '', version: '1.0.0' })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const queryClient = useQueryClient()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await agentsApi.register(form)
      setResult(data)
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.success('Agent registered')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to register agent')
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
          <h2 className="text-lg font-semibold text-slate-900">Register Agent</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100"><X className="w-5 h-5 text-slate-500" /></button>
        </div>
        {result ? (
          <div className="p-4 space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
              <p className="text-sm font-medium text-emerald-800 mb-2">Agent registered successfully!</p>
              <p className="text-xs text-emerald-700 mb-3">Save this API key — it won't be shown again:</p>
              <div className="bg-white rounded-lg p-3 border border-emerald-200">
                <p className="text-xs font-mono text-slate-700 break-all">{result.api_key}</p>
              </div>
              <button
                onClick={() => { navigator.clipboard.writeText(result.api_key); toast.success('Copied') }}
                className="mt-2 text-xs text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
              >
                <Copy className="w-3 h-3" /> Copy to clipboard
              </button>
            </div>
            <button onClick={onClose} className="btn-primary w-full">Done</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            <div>
              <label className="label">Agent Name</label>
              <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="input" placeholder="office-agent-01" required />
            </div>
            <div>
              <label className="label">Hostname</label>
              <input type="text" value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })}
                className="input" placeholder="DESKTOP-ABC123" />
            </div>
            <div>
              <label className="label">IP Address</label>
              <input type="text" value={form.ip_address} onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
                className="input" placeholder="10.0.1.50" />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={loading} className="btn-primary">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Register
              </button>
            </div>
          </form>
        )}
      </motion.div>
    </>
  )
}
