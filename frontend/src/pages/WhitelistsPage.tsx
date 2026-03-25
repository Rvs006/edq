import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { whitelistsApi } from '@/lib/api'
import type { Whitelist, WhitelistEntry } from '@/lib/types'
import { Shield, Plus, Copy, Pencil, Trash2, Loader2, X, ChevronDown, ChevronUp } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'

export default function WhitelistsPage() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editingWhitelist, setEditingWhitelist] = useState<Whitelist | null>(null)
  const queryClient = useQueryClient()

  const { data: whitelists, isLoading } = useQuery({
    queryKey: ['whitelists'],
    queryFn: () => whitelistsApi.list().then(r => r.data),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => whitelistsApi.duplicate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelists'] })
      toast.success('Whitelist duplicated')
    },
  })

  const handleDelete = async (id: string, name: string) => {
    if (!confirm('Delete whitelist "' + name + '"?')) return
    try {
      await whitelistsApi.delete(id)
      queryClient.invalidateQueries({ queryKey: ['whitelists'] })
      toast.success('Whitelist deleted')
    } catch {
      toast.error('Failed to delete whitelist')
    }
  }

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Protocol Whitelists</h1>
          <p className="section-subtitle">Define allowed ports and services for compliance checking</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> New Whitelist
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : whitelists && whitelists.length > 0 ? (
        <div className="space-y-3">
          {whitelists.map((wl: Whitelist) => (
            <div key={wl.id} className="card">
              <button
                onClick={() => setExpanded(expanded === wl.id ? null : wl.id)}
                className="w-full flex items-center justify-between p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Shield className="w-5 h-5 text-brand-500" />
                  <div className="text-left">
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{wl.name}</h3>
                    <p className="text-xs text-zinc-500">{wl.entries?.length || 0} entries &middot; {wl.description || 'No description'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {wl.is_default && <span className="badge text-[10px] bg-blue-50 text-blue-700 border border-blue-200">Default</span>}
                  <button onClick={(e) => { e.stopPropagation(); setEditingWhitelist(wl) }}
                    className="p-1.5 rounded-lg hover:bg-zinc-100" title="Edit">
                    <Pencil className="w-4 h-4 text-zinc-400" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); duplicateMutation.mutate(wl.id) }}
                    className="p-1.5 rounded-lg hover:bg-zinc-100" title="Duplicate">
                    <Copy className="w-4 h-4 text-zinc-400" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(wl.id, wl.name) }}
                    className="p-1.5 rounded-lg hover:bg-red-50" title="Delete">
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </button>
                  {expanded === wl.id ? <ChevronUp className="w-4 h-4 text-zinc-400" /> : <ChevronDown className="w-4 h-4 text-zinc-400" />}
                </div>
              </button>
              <AnimatePresence>
                {expanded === wl.id && (
                  <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
                    <div className="px-4 pb-4">
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-zinc-200 dark:border-zinc-700">
                              <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">Port</th>
                              <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">Protocol</th>
                              <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">Service</th>
                              <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">Required Version</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                            {wl.entries?.map((entry: WhitelistEntry, i: number) => (
                              <tr key={i} className="hover:bg-zinc-50 dark:hover:bg-zinc-800">
                                <td className="py-2 px-2 font-mono text-xs text-zinc-700 dark:text-zinc-300">{entry.port}</td>
                                <td className="py-2 px-2 text-zinc-600 dark:text-zinc-400">{entry.protocol}</td>
                                <td className="py-2 px-2 text-zinc-900 dark:text-zinc-100">{entry.service}</td>
                                <td className="py-2 px-2 text-zinc-500 hidden sm:table-cell">{entry.required_version || '\u2014'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Shield className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-zinc-300 mb-1">No whitelists</h3>
          <p className="text-sm text-zinc-500 mb-4">Create a protocol whitelist for compliance checking</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> New Whitelist
          </button>
        </div>
      )}

      <AnimatePresence>
        {showCreate && <WhitelistModal onClose={() => setShowCreate(false)} />}
        {editingWhitelist && <WhitelistModal whitelist={editingWhitelist} onClose={() => setEditingWhitelist(null)} />}
      </AnimatePresence>
    </div>
  )
}

function WhitelistModal({ whitelist, onClose }: { whitelist?: Whitelist; onClose: () => void }) {
  const isEdit = !!whitelist
  const [name, setName] = useState(whitelist?.name || '')
  const [description, setDescription] = useState(whitelist?.description || '')
  const [entries, setEntries] = useState<{ port: string; protocol: string; service: string; required_version: string }[]>(
    whitelist?.entries?.map(e => ({ port: String(e.port), protocol: e.protocol, service: e.service, required_version: e.required_version || '' }))
    || [{ port: '', protocol: 'TCP', service: '', required_version: '' }]
  )
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const addEntry = () => setEntries([...entries, { port: '', protocol: 'TCP', service: '', required_version: '' }])
  const removeEntry = (i: number) => setEntries(entries.filter((_, idx) => idx !== i))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const validEntries = entries.filter(e => e.port && e.service).map(e => ({
        ...e, port: parseInt(e.port)
      }))
      if (isEdit && whitelist) {
        await whitelistsApi.update(whitelist.id, { name, description, entries: validEntries })
        toast.success('Whitelist updated')
      } else {
        await whitelistsApi.create({ name, description, entries: validEntries })
        toast.success('Whitelist created')
      }
      queryClient.invalidateQueries({ queryKey: ['whitelists'] })
      onClose()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to save whitelist')
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
        className="fixed inset-2 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2
                   sm:w-full sm:max-w-2xl bg-white dark:bg-zinc-900 rounded-lg shadow-2xl z-50 flex flex-col max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{isEdit ? 'Edit' : 'New'} Protocol Whitelist</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="label">Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                  className="input" placeholder="Electracom Default" required />
              </div>
              <div>
                <label className="label">Description</label>
                <input type="text" value={description} onChange={(e) => setDescription(e.target.value)}
                  className="input" placeholder="Standard protocol whitelist" />
              </div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Entries</span>
              <button type="button" onClick={addEntry} className="text-xs text-brand-500 hover:text-brand-600">+ Add Entry</button>
            </div>
            <div className="space-y-2">
              {entries.map((entry, i) => (
                <div key={i} className="flex gap-2 items-end">
                  <div className="w-20">
                    <input type="number" value={entry.port} placeholder="Port"
                      onChange={(e) => { const n = [...entries]; n[i].port = e.target.value; setEntries(n) }}
                      className="input text-xs" />
                  </div>
                  <div className="w-24">
                    <select value={entry.protocol}
                      onChange={(e) => { const n = [...entries]; n[i].protocol = e.target.value; setEntries(n) }}
                      className="input text-xs">
                      <option>TCP</option><option>UDP</option><option>TCP/UDP</option>
                    </select>
                  </div>
                  <div className="flex-1">
                    <input type="text" value={entry.service} placeholder="Service name"
                      onChange={(e) => { const n = [...entries]; n[i].service = e.target.value; setEntries(n) }}
                      className="input text-xs" />
                  </div>
                  <button type="button" onClick={() => removeEntry(i)} className="p-1.5 text-zinc-400 hover:text-red-500">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-3 p-4 border-t border-zinc-200 dark:border-zinc-700">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : isEdit ? <Pencil className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {isEdit ? 'Save Changes' : 'Create Whitelist'}
            </button>
          </div>
        </form>
      </motion.div>
    </>
  )
}
