import { useState, useEffect } from 'react'
import { Shield, Plus, Trash2, ToggleLeft, ToggleRight, Network, AlertTriangle, Loader2 } from 'lucide-react'
import { authorizedNetworksApi } from '@/lib/api'
import { toLocalDateOnly } from '@/lib/testContracts'
import toast from 'react-hot-toast'

interface AuthorizedNetwork {
  id: string
  cidr: string
  label: string | null
  description: string | null
  is_active: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export default function AuthorizedNetworksPage() {
  const [networks, setNetworks] = useState<AuthorizedNetwork[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [cidr, setCidr] = useState('')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchNetworks = async () => {
    try {
      const res = await authorizedNetworksApi.list()
      setNetworks(res.data)
    } catch {
      toast.error('Failed to load authorized networks')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchNetworks() }, [])

  const handleAdd = async () => {
    if (!cidr.trim()) return
    setSaving(true)
    try {
      await authorizedNetworksApi.create({
        cidr: cidr.trim(),
        label: label.trim() || undefined,
        description: description.trim() || undefined,
      })
      toast.success(`Network ${cidr.trim()} authorized`)
      setCidr('')
      setLabel('')
      setDescription('')
      setShowAdd(false)
      fetchNetworks()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to add network')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (network: AuthorizedNetwork) => {
    try {
      await authorizedNetworksApi.update(network.id, { is_active: !network.is_active })
      toast.success(`Network ${network.cidr} ${network.is_active ? 'disabled' : 'enabled'}`)
      fetchNetworks()
    } catch {
      toast.error('Failed to update network')
    }
  }

  const handleDelete = async (network: AuthorizedNetwork) => {
    setDeletingId(network.id)
    try {
      await authorizedNetworksApi.delete(network.id)
      toast.success(`Network ${network.cidr} removed`)
      fetchNetworks()
    } catch {
      toast.error('Failed to delete network')
    } finally {
      setDeletingId(null)
    }
  }

  const cidrValid = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/.test(cidr.trim())
  const activeCount = networks.filter(n => n.is_active).length

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Authorized Networks</h1>
        <p className="section-subtitle">
          Manage which networks EDQ is allowed to scan. All scan targets must fall within an authorized range.
        </p>
      </div>

      {/* Warning banner when no active networks */}
      {!loading && activeCount === 0 && (
        <div className="mb-4 p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">No active authorized networks</p>
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              Network scanning is blocked until at least one network is authorized. Add your test subnets below.
            </p>
          </div>
        </div>
      )}

      {/* Add network form */}
      {showAdd ? (
        <div className="card p-5 mb-4">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-3 flex items-center gap-2">
            <Plus className="w-4 h-4" /> Add Authorized Network
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <div>
              <label className="label">CIDR Range *</label>
              <input
                type="text"
                value={cidr}
                onChange={e => setCidr(e.target.value)}
                placeholder="192.168.1.0/24"
                className={`input ${cidr && !cidrValid ? 'border-red-300 focus:border-red-400' : ''}`}
              />
              {cidr && !cidrValid && <p className="text-xs text-red-500 mt-1">Invalid CIDR format</p>}
            </div>
            <div>
              <label className="label">Label</label>
              <input
                type="text"
                value={label}
                onChange={e => setLabel(e.target.value)}
                placeholder="e.g. Office Lab"
                className="input"
              />
            </div>
            <div>
              <label className="label">Description</label>
              <input
                type="text"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Optional notes"
                className="input"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleAdd}
              disabled={!cidrValid || saving}
              className="btn-primary"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
              {saving ? 'Adding...' : 'Authorize Network'}
            </button>
            <button type="button" onClick={() => { setShowAdd(false); setCidr(''); setLabel(''); setDescription('') }} className="btn-secondary">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mb-4">
          <button type="button" onClick={() => setShowAdd(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Add Network
          </button>
        </div>
      )}

      {/* Networks list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : networks.length === 0 ? (
        <div className="card p-12 text-center">
          <Network className="w-12 h-12 text-zinc-300 dark:text-slate-600 mx-auto mb-3" />
          <p className="text-zinc-500 dark:text-slate-400 text-sm">No authorized networks yet</p>
          <p className="text-zinc-400 dark:text-slate-500 text-xs mt-1">
            Add your first network range to enable scanning
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {networks.map(network => (
            <div
              key={network.id}
              className={`card p-4 flex items-center gap-4 transition-opacity ${
                !network.is_active ? 'opacity-50' : ''
              }`}
            >
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                network.is_active
                  ? 'bg-emerald-50 dark:bg-emerald-950/30'
                  : 'bg-zinc-100 dark:bg-slate-800'
              }`}>
                <Shield className={`w-5 h-5 ${
                  network.is_active ? 'text-emerald-500' : 'text-zinc-400'
                }`} />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-semibold text-zinc-900 dark:text-slate-100">
                    {network.cidr}
                  </span>
                  {network.label && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-950/30 text-brand-600 dark:text-brand-400 font-medium">
                      {network.label}
                    </span>
                  )}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    network.is_active
                      ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400'
                      : 'bg-zinc-100 text-zinc-500 dark:bg-slate-800 dark:text-slate-500'
                  }`}>
                    {network.is_active ? 'Active' : 'Disabled'}
                  </span>
                </div>
                {network.description && (
                  <p className="text-xs text-zinc-500 dark:text-slate-400 mt-0.5 truncate">{network.description}</p>
                )}
                <p className="text-[10px] text-zinc-400 dark:text-slate-500 mt-0.5">
                  Added {toLocalDateOnly(network.created_at)}
                </p>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => handleToggle(network)}
                  className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors"
                  title={network.is_active ? 'Disable network' : 'Enable network'}
                >
                  {network.is_active
                    ? <ToggleRight className="w-5 h-5 text-emerald-500" />
                    : <ToggleLeft className="w-5 h-5 text-zinc-400" />
                  }
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(network)}
                  disabled={deletingId === network.id}
                  className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 text-zinc-400 hover:text-red-500 transition-colors"
                  title="Delete network"
                >
                  {deletingId === network.id
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Trash2 className="w-4 h-4" />
                  }
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Info footer */}
      <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800/50 rounded-xl">
        <p className="text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
          <strong>How it works:</strong> When an engineer starts a network scan, EDQ checks that the target subnet
          falls entirely within one of the authorized ranges above. Scans outside authorized ranges are blocked.
          Common ranges: <span className="font-mono">192.168.0.0/16</span>, <span className="font-mono">10.0.0.0/8</span>, <span className="font-mono">172.16.0.0/12</span>.
        </p>
      </div>
    </div>
  )
}
