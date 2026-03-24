import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { testRunsApi, devicesApi, templatesApi } from '@/lib/api'
import type { TestRun, Device, TestTemplate } from '@/lib/types'
import { Play, Plus, Loader2, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'

export default function TestRunsPage() {
  const [searchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const deviceId = searchParams.get('device_id') || undefined

  const { data: runs, isLoading } = useQuery({
    queryKey: ['test-runs', statusFilter, deviceId],
    queryFn: () => testRunsApi.list({ status: statusFilter || undefined, device_id: deviceId }).then(r => r.data),
  })

  return (
    <div className="page-container">
      <div data-tour="test-runs-table" className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Test Runs</h1>
          <p className="section-subtitle">Monitor and manage device qualification test runs</p>
        </div>
        <button onClick={() => setShowCreateModal(true)} className="btn-primary">
          <Plus className="w-4 h-4" /> New Test Run
        </button>
      </div>

      <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
        {['', 'pending', 'running', 'paused_manual', 'awaiting_review', 'complete', 'failed', 'error'].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              statusFilter === s
                ? 'bg-brand-500 text-white'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
            }`}
          >
            {s ? s.replace(/_/g, ' ') : 'All'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : runs && runs.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-800/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Device</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">IP</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden md:table-cell">Template</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">Progress</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">Verdict</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-zinc-400 hidden lg:table-cell">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {runs.map((run: TestRun) => (
                  <tr key={run.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors">
                    <td className="py-3 px-4">
                      <Link to={`/test-runs/${run.id}`} className="font-medium text-zinc-900 dark:text-zinc-100 hover:text-brand-500">
                        {run.device_name || `Run ${run.id.slice(0, 8)}`}
                      </Link>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-zinc-500 hidden sm:table-cell">
                      {run.device_ip || run.device_id?.slice(0, 8)}
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden md:table-cell">
                      {run.template_name || run.template_id?.slice(0, 8)}
                    </td>
                    <td className="py-3 px-4"><StatusBadge status={run.status} /></td>
                    <td className="py-3 px-4 hidden sm:table-cell">
                      {run.status === 'running' ? (
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-zinc-100 dark:bg-zinc-700 rounded-full overflow-hidden">
                            <div className="h-full bg-brand-500 rounded-full" style={{ width: `${run.progress_pct || 0}%` }} />
                          </div>
                          <span className="text-xs text-zinc-500">{Math.round(run.progress_pct || 0)}%</span>
                        </div>
                      ) : (
                        <span className="text-xs text-zinc-400">
                          {run.total_tests ? `${run.passed_tests || 0}/${run.total_tests}` : '—'}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden lg:table-cell">
                      {run.started_at ? new Date(run.started_at).toLocaleString() : new Date(run.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Play className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-zinc-300 mb-1">No test runs</h3>
          <p className="text-sm text-zinc-500 mb-4">Create a test run to start qualifying devices</p>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> New Test Run
          </button>
        </div>
      )}

      <AnimatePresence>
        {showCreateModal && <CreateRunModal onClose={() => setShowCreateModal(false)} />}
      </AnimatePresence>
    </div>
  )
}

function CreateRunModal({ onClose }: { onClose: () => void }) {
  const [deviceId, setDeviceId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const { data: devices } = useQuery({
    queryKey: ['devices-list'],
    queryFn: () => devicesApi.list().then(r => r.data),
  })
  const { data: templates } = useQuery({
    queryKey: ['templates-list'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await testRunsApi.create({ device_id: deviceId, template_id: templateId })
      queryClient.invalidateQueries({ queryKey: ['test-runs'] })
      toast.success('Test run created')
      onClose()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Failed to create test run')
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
                   sm:w-full sm:max-w-md bg-white dark:bg-zinc-900 rounded-lg shadow-2xl z-50"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">New Test Run</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="label">Device</label>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} className="input" required>
              <option value="">Select a device...</option>
              {devices?.map((d: Device) => (
                <option key={d.id} value={d.id}>{d.ip_address} — {d.hostname || d.manufacturer || 'Unknown'}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Test Template</label>
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} className="input" required>
              <option value="">Select a template...</option>
              {templates?.map((t: TestTemplate) => (
                <option key={t.id} value={t.id}>{t.name} ({t.test_ids?.length || 0} tests)</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Create Run
            </button>
          </div>
        </form>
      </motion.div>
    </>
  )
}
