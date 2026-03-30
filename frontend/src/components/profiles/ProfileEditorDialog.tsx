import { useState, useEffect } from 'react'
import { X, Fingerprint, Plus, Trash2, Loader2 } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'

interface FingerprintRules {
  required_ports: number[]
  optional_ports?: number[]
  vendors: string[]
  services?: string[]
  skip_test_ids: string[]
}

interface ProfileData {
  id?: string
  name: string
  manufacturer: string
  model_pattern: string
  category: string
  description: string
  fingerprint_rules: FingerprintRules
}

interface ProfileEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: ProfileData) => Promise<void>
  profile?: ProfileData | null
}

const CATEGORIES = [
  { value: 'camera', label: 'IP Camera' },
  { value: 'controller', label: 'BAS Controller' },
  { value: 'intercom', label: 'Intercom / VoIP' },
  { value: 'access_panel', label: 'Access Control' },
  { value: 'lighting', label: 'Lighting' },
  { value: 'hvac', label: 'HVAC' },
  { value: 'iot_sensor', label: 'IoT Sensor' },
  { value: 'meter', label: 'Meter' },
  { value: 'unknown', label: 'Unknown / Generic' },
]

const ALL_TEST_IDS = Array.from({ length: 43 }, (_, i) => `U${String(i + 1).padStart(2, '0')}`)

const COMMON_SKIP_GROUPS = [
  { label: 'TLS tests (U10-U13)', ids: ['U10', 'U11', 'U12', 'U13'] },
  { label: 'SSH audit (U15)', ids: ['U15'] },
  { label: 'HTTP tests (U14, U16-U18, U35)', ids: ['U14', 'U16', 'U17', 'U18', 'U35'] },
  { label: 'SNMP (U31)', ids: ['U31'] },
  { label: 'UPnP (U32)', ids: ['U32'] },
  { label: 'mDNS (U33)', ids: ['U33'] },
  { label: 'RTSP (U37)', ids: ['U37'] },
]

const DEFAULT_RULES: FingerprintRules = {
  required_ports: [],
  optional_ports: [],
  vendors: [],
  services: [],
  skip_test_ids: [],
}

export default function ProfileEditorDialog({
  open,
  onOpenChange,
  onSave,
  profile,
}: ProfileEditorDialogProps) {
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [modelPattern, setModelPattern] = useState('')
  const [category, setCategory] = useState('unknown')
  const [description, setDescription] = useState('')
  const [rules, setRules] = useState<FingerprintRules>({ ...DEFAULT_RULES })

  // Port input states
  const [newRequiredPort, setNewRequiredPort] = useState('')
  const [newOptionalPort, setNewOptionalPort] = useState('')
  const [newVendor, setNewVendor] = useState('')
  const [newService, setNewService] = useState('')

  useEffect(() => {
    if (profile) {
      setName(profile.name)
      setManufacturer(profile.manufacturer)
      setModelPattern(profile.model_pattern || '')
      setCategory(profile.category)
      setDescription(profile.description || '')
      setRules({ ...DEFAULT_RULES, ...profile.fingerprint_rules })
    } else {
      setName('')
      setManufacturer('')
      setModelPattern('')
      setCategory('unknown')
      setDescription('')
      setRules({ ...DEFAULT_RULES })
    }
  }, [profile, open])

  const handleSubmit = async () => {
    if (!name.trim() || !manufacturer.trim()) return
    setSaving(true)
    try {
      await onSave({
        id: profile?.id,
        name: name.trim(),
        manufacturer: manufacturer.trim(),
        model_pattern: modelPattern.trim() || '*',
        category,
        description: description.trim(),
        fingerprint_rules: rules,
      })
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  const addPort = (type: 'required_ports' | 'optional_ports', value: string, clear: () => void) => {
    const port = parseInt(value, 10)
    if (!port || port < 1 || port > 65535) return
    if (rules[type]?.includes(port)) return
    setRules({ ...rules, [type]: [...(rules[type] || []), port].sort((a, b) => a - b) })
    clear()
  }

  const removePort = (type: 'required_ports' | 'optional_ports', port: number) => {
    setRules({ ...rules, [type]: (rules[type] || []).filter((p) => p !== port) })
  }

  const addVendor = () => {
    const v = newVendor.trim().toLowerCase()
    if (!v || rules.vendors.includes(v)) return
    setRules({ ...rules, vendors: [...rules.vendors, v] })
    setNewVendor('')
  }

  const removeVendor = (v: string) => {
    setRules({ ...rules, vendors: rules.vendors.filter((x) => x !== v) })
  }

  const addService = () => {
    const s = newService.trim().toLowerCase()
    if (!s || rules.services?.includes(s)) return
    setRules({ ...rules, services: [...(rules.services || []), s] })
    setNewService('')
  }

  const removeService = (s: string) => {
    setRules({ ...rules, services: (rules.services || []).filter((x) => x !== s) })
  }

  const toggleSkipTest = (testId: string) => {
    const current = new Set(rules.skip_test_ids)
    if (current.has(testId)) current.delete(testId)
    else current.add(testId)
    setRules({ ...rules, skip_test_ids: Array.from(current).sort() })
  }

  const toggleSkipGroup = (ids: string[]) => {
    const current = new Set(rules.skip_test_ids)
    const allPresent = ids.every((id) => current.has(id))
    if (allPresent) {
      ids.forEach((id) => current.delete(id))
    } else {
      ids.forEach((id) => current.add(id))
    }
    setRules({ ...rules, skip_test_ids: Array.from(current).sort() })
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-50 animate-fade-in" />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <Dialog.Content className="w-[90vw] max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-dark-card rounded-xl shadow-xl animate-fade-in">
            {/* Header */}
            <div className="sticky top-0 bg-white dark:bg-dark-card p-5 border-b border-zinc-100 dark:border-slate-700/50 z-10">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Fingerprint className="w-5 h-5 text-indigo-500" />
                  <Dialog.Title className="text-base font-semibold text-zinc-900 dark:text-slate-100">
                    {profile?.id ? 'Edit Device Profile' : 'New Device Profile'}
                  </Dialog.Title>
                </div>
                <Dialog.Close className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors">
                  <X className="w-4 h-4 text-zinc-400" />
                </Dialog.Close>
              </div>
              <Dialog.Description className="text-sm text-zinc-500 dark:text-slate-400 mt-1">
                Configure how this device type is detected and which tests to skip.
              </Dialog.Description>
            </div>

            <div className="p-5 space-y-5">
              {/* Basic Info */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-zinc-700 dark:text-slate-300 mb-1.5 block">
                    Profile Name *
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Axis P-Series Camera"
                    className="input"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-zinc-700 dark:text-slate-300 mb-1.5 block">
                    Manufacturer *
                  </label>
                  <input
                    type="text"
                    value={manufacturer}
                    onChange={(e) => setManufacturer(e.target.value)}
                    placeholder="e.g. Axis Communications"
                    className="input"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-zinc-700 dark:text-slate-300 mb-1.5 block">
                    Model Pattern
                  </label>
                  <input
                    type="text"
                    value={modelPattern}
                    onChange={(e) => setModelPattern(e.target.value)}
                    placeholder="e.g. P-* or FW-14"
                    className="input"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-zinc-700 dark:text-slate-300 mb-1.5 block">
                    Category
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="input"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-zinc-700 dark:text-slate-300 mb-1.5 block">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="Brief description of this device profile..."
                  className="input resize-y text-sm"
                />
              </div>

              {/* Fingerprint Rules */}
              <div className="border-t border-zinc-100 dark:border-slate-700/50 pt-5">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-3">
                  Fingerprint Rules
                </h3>

                {/* Required Ports */}
                <div className="mb-4">
                  <label className="text-xs font-medium text-zinc-600 dark:text-slate-400 mb-1.5 block">
                    Required Ports — all must be open to match
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {(rules.required_ports || []).map((port) => (
                      <span key={port} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 text-xs font-mono">
                        {port}
                        <button onClick={() => removePort('required_ports', port)} className="hover:text-red-500">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={newRequiredPort}
                      onChange={(e) => setNewRequiredPort(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addPort('required_ports', newRequiredPort, () => setNewRequiredPort(''))}
                      placeholder="Port number"
                      min={1}
                      max={65535}
                      className="input w-32 text-sm"
                    />
                    <button
                      onClick={() => addPort('required_ports', newRequiredPort, () => setNewRequiredPort(''))}
                      className="btn-secondary text-xs px-2 py-1"
                    >
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>
                </div>

                {/* Optional Ports */}
                <div className="mb-4">
                  <label className="text-xs font-medium text-zinc-600 dark:text-slate-400 mb-1.5 block">
                    Optional Ports — boost match score if open
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {(rules.optional_ports || []).map((port) => (
                      <span key={port} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-slate-800 text-zinc-600 dark:text-slate-400 text-xs font-mono">
                        {port}
                        <button onClick={() => removePort('optional_ports', port)} className="hover:text-red-500">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={newOptionalPort}
                      onChange={(e) => setNewOptionalPort(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addPort('optional_ports', newOptionalPort, () => setNewOptionalPort(''))}
                      placeholder="Port number"
                      min={1}
                      max={65535}
                      className="input w-32 text-sm"
                    />
                    <button
                      onClick={() => addPort('optional_ports', newOptionalPort, () => setNewOptionalPort(''))}
                      className="btn-secondary text-xs px-2 py-1"
                    >
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>
                </div>

                {/* Vendor Strings */}
                <div className="mb-4">
                  <label className="text-xs font-medium text-zinc-600 dark:text-slate-400 mb-1.5 block">
                    Vendor Strings — matched against OUI vendor (case-insensitive)
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {rules.vendors.map((v) => (
                      <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 text-xs">
                        {v}
                        <button onClick={() => removeVendor(v)} className="hover:text-red-500">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newVendor}
                      onChange={(e) => setNewVendor(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addVendor()}
                      placeholder="e.g. axis"
                      className="input w-48 text-sm"
                    />
                    <button onClick={addVendor} className="btn-secondary text-xs px-2 py-1">
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>
                </div>

                {/* Service Strings */}
                <div className="mb-4">
                  <label className="text-xs font-medium text-zinc-600 dark:text-slate-400 mb-1.5 block">
                    Service Strings — matched against nmap service names
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {(rules.services || []).map((s) => (
                      <span key={s} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 text-xs">
                        {s}
                        <button onClick={() => removeService(s)} className="hover:text-red-500">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newService}
                      onChange={(e) => setNewService(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addService()}
                      placeholder="e.g. rtsp, http, ssh"
                      className="input w-48 text-sm"
                    />
                    <button onClick={addService} className="btn-secondary text-xs px-2 py-1">
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>
                </div>
              </div>

              {/* Skip Tests */}
              <div className="border-t border-zinc-100 dark:border-slate-700/50 pt-5">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-1">
                  Default Skip Tests
                </h3>
                <p className="text-xs text-zinc-500 dark:text-slate-400 mb-3">
                  Tests that should always be skipped for this device type, regardless of port detection.
                </p>

                {/* Quick group toggles */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {COMMON_SKIP_GROUPS.map((group) => {
                    const allSkipped = group.ids.every((id) => rules.skip_test_ids.includes(id))
                    return (
                      <button
                        key={group.label}
                        onClick={() => toggleSkipGroup(group.ids)}
                        className={`text-[11px] px-2 py-1 rounded-md border transition-colors ${
                          allSkipped
                            ? 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
                            : 'border-zinc-200 dark:border-slate-700/50 text-zinc-600 dark:text-slate-400 hover:bg-zinc-50 dark:hover:bg-slate-800'
                        }`}
                      >
                        {allSkipped ? <Trash2 className="w-3 h-3 inline mr-0.5" /> : null}
                        {group.label}
                      </button>
                    )
                  })}
                </div>

                {/* Individual test toggles */}
                <div className="grid grid-cols-6 sm:grid-cols-8 md:grid-cols-11 gap-1">
                  {ALL_TEST_IDS.map((testId) => {
                    const isSkipped = rules.skip_test_ids.includes(testId)
                    return (
                      <button
                        key={testId}
                        onClick={() => toggleSkipTest(testId)}
                        className={`text-[10px] font-mono py-1 rounded transition-colors ${
                          isSkipped
                            ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400 ring-1 ring-red-200 dark:ring-red-800'
                            : 'bg-zinc-50 dark:bg-slate-800 text-zinc-500 dark:text-slate-500 hover:bg-zinc-100 dark:hover:bg-slate-700'
                        }`}
                        title={isSkipped ? `${testId}: will be skipped` : `${testId}: will run`}
                      >
                        {testId}
                      </button>
                    )
                  })}
                </div>
                {rules.skip_test_ids.length > 0 && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                    {rules.skip_test_ids.length} test{rules.skip_test_ids.length > 1 ? 's' : ''} will be skipped
                  </p>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 bg-white dark:bg-dark-card flex items-center justify-end gap-2 p-4 border-t border-zinc-100 dark:border-slate-700/50">
              <Dialog.Close className="btn-secondary text-sm">Cancel</Dialog.Close>
              <button
                onClick={handleSubmit}
                disabled={saving || !name.trim() || !manufacturer.trim()}
                className="btn-primary text-sm"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  profile?.id ? 'Update Profile' : 'Create Profile'
                )}
              </button>
            </div>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
