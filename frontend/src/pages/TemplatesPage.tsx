import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { templatesApi } from '@/lib/api'
import type { TestTemplate, TestLibraryItem } from '@/lib/types'
import { FileText, Plus, Pencil, Trash2, Loader2, X, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'

export default function TemplatesPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<TestTemplate | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })

  const { data: library } = useQuery({
    queryKey: ['test-library'],
    queryFn: () => templatesApi.library().then(r => r.data),
  })

  const handleDelete = async (id: string, name: string) => {
    if (!confirm('Delete template "' + name + '"?')) return
    try {
      await templatesApi.delete(id)
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success('Template deleted')
    } catch {
      toast.error('Failed to delete template')
    }
  }

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Test Templates</h1>
          <p className="section-subtitle">Configure test suites for device qualification</p>
        </div>
        <button type="button" onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> New Template
        </button>
      </div>

      <div className="card mb-5">
        <button
          type="button"
          onClick={() => setExpanded(expanded === 'library' ? null : 'library')}
          className="w-full flex items-center justify-between p-4 hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors"
        >
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-brand-500" />
            <span className="font-semibold text-zinc-900 dark:text-slate-100">Universal Test Library</span>
            <span className="badge text-[10px] bg-blue-50 text-blue-700 border border-blue-200">
              {library?.length || 30} tests
            </span>
          </div>
          {expanded === 'library' ? <ChevronUp className="w-4 h-4 text-zinc-400" /> : <ChevronDown className="w-4 h-4 text-zinc-400" />}
        </button>
        <AnimatePresence>
          {expanded === 'library' && library && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-4 pb-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200 dark:border-slate-700/50">
                        <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-slate-400">ID</th>
                        <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-slate-400">Name</th>
                        <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Tier</th>
                        <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Tool</th>
                        <th className="text-left py-2 px-2 text-xs font-medium text-zinc-500 dark:text-slate-400">Essential</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                      {library.map((test: TestLibraryItem) => (
                        <tr key={test.test_id} className="hover:bg-zinc-50 dark:hover:bg-slate-800">
                          <td className="py-2 px-2 font-mono text-xs text-zinc-500 dark:text-slate-400">{test.test_id}</td>
                          <td className="py-2 px-2 text-zinc-900 dark:text-slate-100">{test.name}</td>
                          <td className="py-2 px-2 text-zinc-600 dark:text-slate-400 capitalize hidden sm:table-cell">{test.tier?.replace(/_/g, ' ')}</td>
                          <td className="py-2 px-2 text-zinc-500 dark:text-slate-400 hidden sm:table-cell">{test.tool || '\u2014'}</td>
                          <td className="py-2 px-2">
                            {test.is_essential ? <Check className="w-4 h-4 text-red-500" /> : <span className="text-zinc-300">{'\u2014'}</span>}
                          </td>
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

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : templates && templates.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Name</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Description</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Tests</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Category</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                {templates.map((t: TestTemplate) => (
                  <tr key={t.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                    <td className="py-3 px-4 font-medium text-zinc-900 dark:text-slate-100">{t.name}</td>
                    <td className="py-3 px-4 text-zinc-500 dark:text-slate-400 text-xs hidden sm:table-cell">{t.description || '\u2014'}</td>
                    <td className="py-3 px-4">
                      <span className="badge text-[10px] bg-zinc-100 text-zinc-600">{t.test_ids?.length || 0} tests</span>
                    </td>
                    <td className="py-3 px-4 text-zinc-500 dark:text-slate-400 capitalize hidden md:table-cell">{t.device_category || '\u2014'}</td>
                    <td className="py-3 px-4">
                      {t.is_default && <span className="badge text-[10px] bg-blue-50 text-blue-700 border border-blue-200">Default</span>}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <button type="button" onClick={() => setEditingTemplate(t)} className="p-1.5 rounded hover:bg-zinc-100 dark:hover:bg-slate-800" title="Edit">
                          <Pencil className="w-3.5 h-3.5 text-zinc-500" />
                        </button>
                        <button type="button" onClick={() => handleDelete(t.id, t.name)} className="p-1.5 rounded hover:bg-red-50" title="Delete">
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <FileText className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">No templates yet</h3>
          <p className="text-sm text-zinc-500 mb-4">Create a test template to define which tests to run</p>
          <button type="button" onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> New Template
          </button>
        </div>
      )}

      <AnimatePresence>
        {showCreate && <CreateTemplateModal library={library || []} onClose={() => setShowCreate(false)} />}
        {editingTemplate && <EditTemplateModal template={editingTemplate} library={library || []} onClose={() => setEditingTemplate(null)} />}
      </AnimatePresence>
    </div>
  )
}

function CreateTemplateModal({ library, onClose }: { library: TestLibraryItem[]; onClose: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedTests, setSelectedTests] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const toggleTest = (id: string) => {
    setSelectedTests(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id])
  }

  const selectAll = () => setSelectedTests(library.map(t => t.test_id))
  const selectEssential = () => setSelectedTests(library.filter(t => t.is_essential).map(t => t.test_id))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedTests.length === 0) { toast.error('Select at least one test'); return }
    setLoading(true)
    try {
      await templatesApi.create({ name, description, test_ids: selectedTests })
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success('Template created')
      onClose()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to create template')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-2xl bg-white dark:bg-dark-card rounded-lg shadow-2xl flex flex-col max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">New Test Template</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="p-4 space-y-3">
            <div>
              <label className="label">Template Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                className="input" placeholder="Full Security Assessment" required />
            </div>
            <div>
              <label className="label">Description</label>
              <input type="text" value={description} onChange={(e) => setDescription(e.target.value)}
                className="input" placeholder="Complete 30-test qualification suite" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">
                Select Tests ({selectedTests.length}/{library.length})
              </span>
              <div className="flex gap-2">
                <button type="button" onClick={selectAll} className="text-xs text-brand-500 hover:text-brand-600">All</button>
                <button type="button" onClick={selectEssential} className="text-xs text-red-500 hover:text-red-600">Essential</button>
                <button type="button" onClick={() => setSelectedTests([])} className="text-xs text-zinc-500 hover:text-zinc-600">None</button>
              </div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <div className="space-y-1">
              {library.map((test: TestLibraryItem) => (
                <label key={test.test_id}
                  className={'flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ' +
                    (selectedTests.includes(test.test_id) ? 'bg-brand-50 dark:bg-brand-500/10' : 'hover:bg-zinc-50 dark:hover:bg-slate-800')
                  }>
                  <input type="checkbox" checked={selectedTests.includes(test.test_id)}
                    onChange={() => toggleTest(test.test_id)}
                    className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500" />
                  <span className="text-xs font-mono text-zinc-400 w-8">{test.test_id}</span>
                  <span className="text-sm text-zinc-900 dark:text-slate-100 flex-1">{test.name}</span>
                  {test.is_essential && <span className="badge text-[9px] bg-red-50 text-red-600 border border-red-200">Essential</span>}
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-3 p-4 border-t border-zinc-200 dark:border-slate-700/50">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Template
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}

function EditTemplateModal({ template, library, onClose }: { template: TestTemplate; library: TestLibraryItem[]; onClose: () => void }) {
  const [name, setName] = useState(template.name)
  const [description, setDescription] = useState(template.description || '')
  const [selectedTests, setSelectedTests] = useState<string[]>(template.test_ids || [])
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const toggleTest = (id: string) => {
    setSelectedTests(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id])
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedTests.length === 0) { toast.error('Select at least one test'); return }
    setLoading(true)
    try {
      await templatesApi.update(template.id, { name, description, test_ids: selectedTests })
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success('Template updated')
      onClose()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to update template')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-2xl bg-white dark:bg-dark-card rounded-lg shadow-2xl flex flex-col max-h-[90vh]"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Edit Template</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="p-4 space-y-3">
            <div>
              <label className="label">Template Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                className="input" required />
            </div>
            <div>
              <label className="label">Description</label>
              <input type="text" value={description} onChange={(e) => setDescription(e.target.value)}
                className="input" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">
                Select Tests ({selectedTests.length}/{library.length})
              </span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <div className="space-y-1">
              {library.map((test: TestLibraryItem) => (
                <label key={test.test_id}
                  className={'flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ' +
                    (selectedTests.includes(test.test_id) ? 'bg-brand-50 dark:bg-brand-500/10' : 'hover:bg-zinc-50 dark:hover:bg-slate-800')
                  }>
                  <input type="checkbox" checked={selectedTests.includes(test.test_id)}
                    onChange={() => toggleTest(test.test_id)}
                    className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500" />
                  <span className="text-xs font-mono text-zinc-400 w-8">{test.test_id}</span>
                  <span className="text-sm text-zinc-900 dark:text-slate-100 flex-1">{test.name}</span>
                  {test.is_essential && <span className="badge text-[9px] bg-red-50 text-red-600 border border-red-200">Essential</span>}
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-3 p-4 border-t border-zinc-200 dark:border-slate-700/50">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Pencil className="w-4 h-4" />}
              Save Changes
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
