import { useState, useEffect } from 'react'
import {
  ListChecks, Plus, Copy, Trash2, Pencil, X, Save, Loader2,
  ChevronDown, ChevronRight, ToggleLeft, ToggleRight, Info
} from 'lucide-react'
import { testPlansApi, templatesApi } from '@/lib/api'
import { UNIVERSAL_TESTS } from '@/lib/universal-tests'
import type { UniversalTest } from '@/lib/universal-tests'
import toast from 'react-hot-toast'

const TIER_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'automatic', label: 'Automatic' },
  { value: 'guided_manual', label: 'Guided Manual' },
]

interface TestConfig {
  test_id: string
  enabled: boolean
  tier_override: string | null
  custom?: {
    name: string
    description: string
    tier: string
  } | null
}

interface TestPlan {
  id: string
  name: string
  description: string | null
  base_template_id: string | null
  test_configs: TestConfig[]
  created_by: string
  created_at: string
  updated_at: string | null
}

export default function TestPlansPage() {
  const [plans, setPlans] = useState<TestPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<TestPlan | null>(null)
  const [creating, setCreating] = useState(false)

  const fetchPlans = async () => {
    setLoading(true)
    try {
      const res = await testPlansApi.list()
      setPlans(res.data)
    } catch {
      toast.error('Failed to load test plans')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPlans() }, [])

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this test plan?')) return
    try {
      await testPlansApi.delete(id)
      toast.success('Test plan deleted')
      fetchPlans()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const handleClone = async (id: string) => {
    try {
      await testPlansApi.clone(id)
      toast.success('Test plan cloned')
      fetchPlans()
    } catch {
      toast.error('Failed to clone')
    }
  }

  if (editing || creating) {
    return (
      <TestPlanEditor
        plan={editing}
        onSave={() => { setEditing(null); setCreating(false); fetchPlans() }}
        onCancel={() => { setEditing(null); setCreating(false) }}
      />
    )
  }

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="section-title">Test Plans</h1>
          <p className="section-subtitle">Create custom test configurations with per-test toggles</p>
        </div>
        <button onClick={() => setCreating(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> Create Plan
        </button>
      </div>

      {loading ? (
        <div className="card p-12 text-center">
          <Loader2 className="w-6 h-6 animate-spin text-zinc-400 mx-auto" />
        </div>
      ) : plans.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="w-12 h-12 rounded-full bg-zinc-100 flex items-center justify-center mx-auto mb-3">
            <ListChecks className="w-6 h-6 text-zinc-400" />
          </div>
          <p className="text-sm font-medium text-zinc-700 mb-1">No test plans yet</p>
          <p className="text-xs text-zinc-500 mb-4">Create a custom plan to select which tests run and override their tiers.</p>
          <button onClick={() => setCreating(true)} className="btn-primary mx-auto">
            <Plus className="w-4 h-4" /> Create Plan
          </button>
        </div>
      ) : (
        <div className="card">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-200 bg-zinc-50">
                <th className="px-5 py-2.5">Name</th>
                <th className="px-3 py-2.5">Description</th>
                <th className="px-3 py-2.5 text-center">Enabled</th>
                <th className="px-3 py-2.5 text-center">Custom</th>
                <th className="px-3 py-2.5">Created</th>
                <th className="px-3 py-2.5 w-32"></th>
              </tr>
            </thead>
            <tbody>
              {plans.map(p => {
                const enabled = (p.test_configs || []).filter(c => c.enabled).length
                const custom = (p.test_configs || []).filter(c => c.custom).length
                return (
                  <tr key={p.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                    <td className="px-5 py-3">
                      <span className="font-medium text-zinc-800">{p.name}</span>
                    </td>
                    <td className="px-3 py-3 text-zinc-500 text-xs max-w-xs truncate">{p.description || '—'}</td>
                    <td className="px-3 py-3 text-center">
                      <span className="badge bg-brand-50 text-brand-600 border border-brand-100">{enabled}</span>
                    </td>
                    <td className="px-3 py-3 text-center">
                      {custom > 0 ? <span className="badge bg-purple-50 text-purple-600 border border-purple-100">{custom}</span> : <span className="text-zinc-400">—</span>}
                    </td>
                    <td className="px-3 py-3 text-xs text-zinc-400">{new Date(p.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => setEditing(p)} className="p-1.5 rounded hover:bg-zinc-100" title="Edit">
                          <Pencil className="w-3.5 h-3.5 text-zinc-500" />
                        </button>
                        <button onClick={() => handleClone(p.id)} className="p-1.5 rounded hover:bg-zinc-100" title="Clone">
                          <Copy className="w-3.5 h-3.5 text-zinc-500" />
                        </button>
                        <button onClick={() => handleDelete(p.id)} className="p-1.5 rounded hover:bg-red-50" title="Delete">
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function TestPlanEditor({ plan, onSave, onCancel }: { plan: TestPlan | null; onSave: () => void; onCancel: () => void }) {
  const [name, setName] = useState(plan?.name || '')
  const [description, setDescription] = useState(plan?.description || '')
  const [configs, setConfigs] = useState<TestConfig[]>(() => {
    if (plan?.test_configs?.length) return plan.test_configs
    return UNIVERSAL_TESTS.map(t => ({ test_id: t.id, enabled: true, tier_override: null, custom: null }))
  })
  const [saving, setSaving] = useState(false)
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(['Network']))
  const [customCounter, setCustomCounter] = useState(() => {
    const existing = configs.filter(c => c.test_id.startsWith('CUSTOM_'))
    return existing.length
  })

  const configMap = new Map(configs.map(c => [c.test_id, c]))
  const categories = ['Network', 'TLS', 'SSH', 'Web', 'Manual', 'Custom']

  const toggleEnabled = (testId: string) => {
    setConfigs(prev => prev.map(c => c.test_id === testId ? { ...c, enabled: !c.enabled } : c))
  }

  const setTierOverride = (testId: string, tier: string) => {
    setConfigs(prev => prev.map(c => c.test_id === testId ? { ...c, tier_override: tier || null } : c))
  }

  const addCustomTest = () => {
    const num = customCounter + 1
    setCustomCounter(num)
    const id = `CUSTOM_${String(num).padStart(2, '0')}`
    setConfigs(prev => [...prev, {
      test_id: id,
      enabled: true,
      tier_override: null,
      custom: { name: '', description: '', tier: 'guided_manual' },
    }])
    setExpandedCats(prev => new Set([...prev, 'Custom']))
  }

  const updateCustom = (testId: string, field: string, value: string) => {
    setConfigs(prev => prev.map(c => {
      if (c.test_id !== testId || !c.custom) return c
      return { ...c, custom: { ...c.custom, [field]: value } }
    }))
  }

  const removeCustom = (testId: string) => {
    setConfigs(prev => prev.filter(c => c.test_id !== testId))
  }

  const enableAll = () => setConfigs(prev => prev.map(c => ({ ...c, enabled: true })))
  const disableAll = () => setConfigs(prev => prev.map(c => ({ ...c, enabled: false })))

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const payload = { name, description: description || null, test_configs: configs, base_template_id: plan?.base_template_id || null }
      if (plan) {
        await testPlansApi.update(plan.id, payload)
        toast.success('Test plan updated')
      } else {
        await testPlansApi.create(payload)
        toast.success('Test plan created')
      }
      onSave()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const getTestsForCategory = (cat: string) => {
    if (cat === 'Custom') return configs.filter(c => c.custom)
    return UNIVERSAL_TESTS
      .filter(t => t.category === cat)
      .map(t => ({ test: t, config: configMap.get(t.id) }))
  }

  const enabledCount = configs.filter(c => c.enabled).length

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="section-title">{plan ? 'Edit Test Plan' : 'Create Test Plan'}</h1>
          <p className="section-subtitle">Configure which tests are enabled and their execution tiers</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onCancel} className="btn-secondary"><X className="w-4 h-4" /> Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saving ? 'Saving...' : 'Save Plan'}
          </button>
        </div>
      </div>

      <div className="space-y-4">
        <div className="card p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Plan Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)} className="input" placeholder="e.g. Quick Network Scan" />
            </div>
            <div>
              <label className="label">Description</label>
              <input type="text" value={description} onChange={e => setDescription(e.target.value)} className="input" placeholder="Optional description" />
            </div>
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-zinc-900">Test Configuration</h3>
              <span className="badge bg-brand-50 text-brand-600 border border-brand-100">{enabledCount} enabled</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={enableAll} className="text-xs text-brand-500 hover:text-brand-600 font-medium">Enable All</button>
              <button onClick={disableAll} className="text-xs text-zinc-500 hover:text-zinc-600 font-medium">Disable All</button>
            </div>
          </div>

          <div className="space-y-1">
            {categories.map(cat => {
              const expanded = expandedCats.has(cat)
              if (cat === 'Custom') {
                const customConfigs = configs.filter(c => c.custom)
                return (
                  <div key={cat} className="border border-zinc-200 rounded-lg overflow-hidden">
                    <button
                      onClick={() => {
                        const next = new Set(expandedCats)
                        expanded ? next.delete(cat) : next.add(cat)
                        setExpandedCats(next)
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 bg-purple-50 hover:bg-purple-100 transition-colors"
                    >
                      {expanded ? <ChevronDown className="w-4 h-4 text-purple-400" /> : <ChevronRight className="w-4 h-4 text-purple-400" />}
                      <span className="text-sm font-medium text-purple-700 flex-1 text-left">Custom Tests</span>
                      <span className="text-xs text-purple-400">{customConfigs.length}</span>
                    </button>
                    {expanded && (
                      <div className="p-3 space-y-3">
                        {customConfigs.map(c => (
                          <div key={c.test_id} className="border border-zinc-200 rounded-lg p-3">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-mono text-zinc-400">{c.test_id}</span>
                              <button onClick={() => removeCustom(c.test_id)} className="p-1 rounded hover:bg-red-50">
                                <Trash2 className="w-3.5 h-3.5 text-red-500" />
                              </button>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                              <input
                                type="text"
                                value={c.custom?.name || ''}
                                onChange={e => updateCustom(c.test_id, 'name', e.target.value)}
                                className="input text-sm"
                                placeholder="Test name"
                              />
                              <input
                                type="text"
                                value={c.custom?.description || ''}
                                onChange={e => updateCustom(c.test_id, 'description', e.target.value)}
                                className="input text-sm"
                                placeholder="Description"
                              />
                              <select
                                value={c.custom?.tier || 'guided_manual'}
                                onChange={e => updateCustom(c.test_id, 'tier', e.target.value)}
                                className="input text-sm"
                              >
                                <option value="guided_manual">Guided Manual</option>
                                <option value="automatic">Automatic</option>
                              </select>
                            </div>
                          </div>
                        ))}
                        <button
                          onClick={addCustomTest}
                          className="w-full py-2 border border-dashed border-purple-300 rounded-lg text-sm text-purple-500 hover:bg-purple-50 transition-colors flex items-center justify-center gap-1"
                        >
                          <Plus className="w-4 h-4" /> Add Custom Manual Test
                        </button>
                      </div>
                    )}
                  </div>
                )
              }

              const items = getTestsForCategory(cat) as { test: UniversalTest; config: TestConfig | undefined }[]
              const catEnabled = items.filter(i => i.config?.enabled).length

              return (
                <div key={cat} className="border border-zinc-200 rounded-lg overflow-hidden">
                  <button
                    onClick={() => {
                      const next = new Set(expandedCats)
                      expanded ? next.delete(cat) : next.add(cat)
                      setExpandedCats(next)
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 bg-zinc-50 hover:bg-zinc-100 transition-colors"
                  >
                    {expanded ? <ChevronDown className="w-4 h-4 text-zinc-400" /> : <ChevronRight className="w-4 h-4 text-zinc-400" />}
                    <span className="text-sm font-medium text-zinc-700 flex-1 text-left">{cat}</span>
                    <span className="text-xs text-zinc-400">{catEnabled}/{items.length}</span>
                  </button>
                  {expanded && (
                    <div className="divide-y divide-zinc-100">
                      {items.map(({ test, config }) => {
                        const enabled = config?.enabled ?? true
                        const tierOverride = config?.tier_override || ''
                        return (
                          <div
                            key={test.id}
                            className={`flex items-center gap-3 px-3 py-2 ${!enabled ? 'opacity-50' : ''}`}
                          >
                            <button onClick={() => toggleEnabled(test.id)} className="shrink-0">
                              {enabled
                                ? <ToggleRight className="w-5 h-5 text-brand-500" />
                                : <ToggleLeft className="w-5 h-5 text-zinc-300" />
                              }
                            </button>
                            <span className="text-xs font-mono text-zinc-400 w-8 shrink-0">{test.id}</span>
                            <span className={`text-sm flex-1 ${enabled ? 'text-zinc-700' : 'text-zinc-400 line-through'}`}>{test.name}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
                              test.tier === 'automatic' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
                            }`}>{test.tier === 'automatic' ? 'Auto' : 'Manual'}</span>
                            {test.essential && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium shrink-0">Essential</span>}
                            <select
                              value={tierOverride}
                              onChange={e => setTierOverride(test.id, e.target.value)}
                              disabled={!enabled}
                              className="text-xs border border-zinc-200 rounded px-2 py-1 bg-white w-28 shrink-0"
                            >
                              {TIER_OPTIONS.map(o => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </select>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <div className="mt-3 p-2.5 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-2">
            <Info className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
            <p className="text-xs text-blue-700">
              Override tier to reclassify tests. Setting an automatic test to "Guided Manual" will present it as a form
              instead of running the tool. Custom tests always appear as guided manual inputs.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
