import { useState, useEffect, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { testRunsApi, devicesApi, templatesApi } from '@/lib/api'
import type { TestRun, Device, TestTemplate } from '@/lib/types'
import {
  Play, Plus, Loader2, X, Activity, RotateCcw, AlertTriangle,
  Clock, Pause, Eye, CheckCircle2, XCircle, Ban,
  Monitor, Cpu, Shield,
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'
import { isActiveTestRunStatus } from '@/lib/testContracts'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'

/* ── Status filter config with labels, icons, groups, tooltips ── */

interface FilterDef {
  key: string
  label: string
  icon: React.ElementType
  tooltip: string
  pulse?: boolean
}

const filterGroups: { label: string; filters: FilterDef[] }[] = [
  {
    label: 'Active',
    filters: [
      { key: 'running', label: 'Running', icon: Activity, tooltip: 'Tests currently executing', pulse: true },
      { key: 'pending', label: 'Pending', icon: Clock, tooltip: 'Waiting to start' },
      { key: 'selecting_interface', label: 'Selecting', icon: Play, tooltip: 'Selecting the interface or connection path' },
      { key: 'syncing', label: 'Syncing', icon: RotateCcw, tooltip: 'Preparing the run before tests start' },
      { key: 'paused_manual', label: 'Paused', icon: Pause, tooltip: 'Manually paused by engineer' },
      { key: 'paused_cable', label: 'Cable Pause', icon: AlertTriangle, tooltip: 'Paused because device connectivity dropped' },
      { key: 'awaiting_manual', label: 'Manual Input', icon: Eye, tooltip: 'Automatic tests finished and manual checks remain' },
    ],
  },
  {
    label: 'Review',
    filters: [
      { key: 'awaiting_review', label: 'Awaiting Review', icon: Eye, tooltip: 'Completed, waiting for QA review' },
    ],
  },
  {
    label: 'Done',
    filters: [
      { key: 'completed', label: 'Complete', icon: CheckCircle2, tooltip: 'All tests finished' },
      { key: 'failed', label: 'Failed', icon: XCircle, tooltip: 'Run failed due to error during execution' },
      { key: 'cancelled', label: 'Cancelled', icon: Ban, tooltip: 'Cancelled before completion — can be resumed' },
    ],
  },
]

function formatRunName(run: TestRun) {
  const device = getPreferredDeviceName(run)
  const date = run.started_at
    ? new Date(run.started_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : new Date(run.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return `${device} — ${date}`
}

function ConfidenceBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-zinc-400">—</span>
  const color =
    score <= 3 ? 'text-red-600 bg-red-50 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800'
    : score <= 6 ? 'text-amber-600 bg-amber-50 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800'
    : 'text-green-600 bg-green-50 border-green-200 dark:bg-green-950/40 dark:text-green-400 dark:border-green-800'
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold border ${color}`}>
      {score}/10
    </span>
  )
}

function CategoryIcon({ category }: { category: string | null }) {
  if (!category || category === 'unknown') return <Monitor className="w-4 h-4 text-zinc-400" />
  const icons: Record<string, React.ElementType> = {
    camera: Monitor, controller: Cpu, intercom: Monitor, access_panel: Shield,
    lighting: Monitor, hvac: Monitor, iot_sensor: Cpu, meter: Cpu,
  }
  const Icon = icons[category] || Monitor
  return <Icon className="w-4 h-4 text-zinc-400" />
}

export default function TestRunsPage() {
  const [searchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const deviceId = searchParams.get('device_id') || undefined
  const navigate = useNavigate()

  const { data: runs, isLoading } = useQuery({
    queryKey: ['test-runs', statusFilter, deviceId],
    queryFn: () => testRunsApi.list({ status: statusFilter || undefined, device_id: deviceId }).then(r => r.data),
    refetchInterval: (query) => {
      const data = query.state.data as TestRun[] | undefined
      const hasActive = data?.some((r) => isActiveTestRunStatus(r.status))
      return hasActive ? 3000 : false
    },
  })

  // Count runs per status for badges
  const { data: allRuns } = useQuery({
    queryKey: ['test-runs-all-for-counts'],
    queryFn: () => testRunsApi.list({ limit: 200 }).then(r => r.data),
    refetchInterval: 10000,
  })

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    if (allRuns) {
      for (const r of allRuns as TestRun[]) {
        const s = r.status
        counts[s] = (counts[s] || 0) + 1
      }
    }
    return counts
  }, [allRuns])

  const handleResume = async (runId: string) => {
    try {
      await testRunsApi.start(runId)
      toast.success('Test run resumed')
      navigate(`/test-runs/${runId}`)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Failed to resume')
    }
  }

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

      {/* Status filter bar — grouped with labels */}
      <div className="flex flex-wrap items-center gap-1.5 mb-5">
        <button
          onClick={() => setStatusFilter('')}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
            statusFilter === ''
              ? 'bg-brand-500 text-white'
              : 'bg-zinc-100 dark:bg-slate-800 text-zinc-600 dark:text-slate-400 hover:bg-zinc-200 dark:hover:bg-slate-700'
          }`}
        >
          All{allRuns ? ` (${(allRuns as TestRun[]).length})` : ''}
        </button>

        {filterGroups.map((group, gi) => (
          <div key={group.label} className="flex items-center gap-1">
            {gi > 0 && <div className="w-px h-5 bg-zinc-200 dark:bg-slate-700 mx-1" />}
            <span className="text-[9px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-slate-600 mr-0.5 hidden sm:block">
              {group.label}
            </span>
            {group.filters.map((f) => {
              const count = statusCounts[f.key] || 0
              const active = statusFilter === f.key
              const Icon = f.icon
              return (
                <button
                  key={f.key}
                  onClick={() => setStatusFilter(active ? '' : f.key)}
                  className={`group relative inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    active
                      ? 'bg-brand-500 text-white'
                      : 'bg-zinc-100 dark:bg-slate-800 text-zinc-600 dark:text-slate-400 hover:bg-zinc-200 dark:hover:bg-slate-700'
                  }`}
                  title={f.tooltip}
                >
                  <Icon className={`w-3 h-3 ${f.pulse && count > 0 ? 'animate-pulse' : ''}`} />
                  <span className="hidden sm:inline">{f.label}</span>
                  {count > 0 && (
                    <span className={`text-[9px] font-bold min-w-[16px] h-4 flex items-center justify-center rounded-full ${
                      active
                        ? 'bg-white/25 text-white'
                        : f.pulse && count > 0
                          ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-400'
                          : 'bg-zinc-200 text-zinc-600 dark:bg-slate-700 dark:text-slate-400'
                    }`}>
                      {count}
                    </span>
                  )}
                  {/* Tooltip on hover */}
                  <span className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 px-2 py-1 text-[10px] text-white bg-zinc-800 dark:bg-slate-700 rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                    {f.tooltip}
                  </span>
                </button>
              )
            })}
          </div>
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
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Device</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Template</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Progress</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Verdict</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden lg:table-cell">Confidence</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden lg:table-cell">Started</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                {runs.map((run: TestRun) => {
                  const isRunning = ['running', 'selecting_interface', 'syncing'].includes(run.status)
                  const isCancelled = run.status === 'cancelled'
                  const isFailed = run.status === 'failed'
                  return (
                    <tr
                      key={run.id}
                      className={`transition-colors ${
                        isRunning
                          ? 'bg-blue-50/40 dark:bg-blue-950/20 hover:bg-blue-50/70 dark:hover:bg-blue-950/30'
                          : 'hover:bg-zinc-50 dark:hover:bg-slate-800'
                      }`}
                    >
                      {/* Device — rich info */}
                      <td className="py-3 px-4">
                        <Link to={`/test-runs/${run.id}`} className="group block">
                          <div className="flex items-center gap-2.5">
                            <CategoryIcon category={run.device_category} />
                            <div className="min-w-0">
                              <div className="font-medium text-zinc-900 dark:text-slate-100 group-hover:text-brand-500 truncate">
                                {formatRunName(run)}
                              </div>
                              <div className="flex items-center gap-2 text-[11px] text-zinc-400 dark:text-slate-500">
                                <span className="font-mono">{run.device_ip || '—'}</span>
                                {getDeviceMetaSummary(run, { includeMac: true }) && (
                                  <>
                                    <span className="text-zinc-300 dark:text-slate-600">&middot;</span>
                                    <span>{getDeviceMetaSummary(run, { includeMac: true })}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        </Link>
                      </td>
                      <td className="py-3 px-4 text-xs text-zinc-500 hidden md:table-cell">
                        {run.template_name || '—'}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <StatusBadge status={run.status} />
                          {isRunning && (
                            <Activity className="w-3.5 h-3.5 text-blue-500 animate-pulse" />
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 hidden sm:table-cell">
                        {isRunning ? (
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-zinc-100 dark:bg-zinc-700 rounded-full overflow-hidden">
                              <motion.div
                                className="h-full bg-gradient-to-r from-blue-500 to-brand-500 rounded-full"
                                initial={{ width: 0 }}
                                animate={{ width: `${run.progress_pct || 0}%` }}
                                transition={{ duration: 0.5, ease: 'easeOut' }}
                              />
                            </div>
                            <span className="text-xs font-mono text-blue-600 dark:text-blue-400 min-w-[3rem]">
                              {run.completed_tests || 0}/{run.total_tests || 43}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-zinc-400 font-mono">
                            {run.total_tests ? `${run.completed_tests || 0}/${run.total_tests}` : '—'}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                      </td>
                      <td className="py-3 px-4 hidden lg:table-cell">
                        <ConfidenceBadge score={run.confidence ?? null} />
                      </td>
                      <td className="py-3 px-4 text-xs text-zinc-500 hidden lg:table-cell">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : new Date(run.created_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-4">
                        {(isCancelled || isFailed) && (
                          <button
                            onClick={() => handleResume(run.id)}
                            className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-400 dark:hover:bg-blue-950/60 rounded transition-colors"
                            title="Resume this test run from where it stopped"
                          >
                            <RotateCcw className="w-3 h-3" /> Resume
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Play className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">No test runs</h3>
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

/* ── Create Run Modal with duplicate detection ── */

function CreateRunModal({ onClose }: { onClose: () => void }) {
  const [deviceId, setDeviceId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [loading, setLoading] = useState(false)
  const [duplicateInfo, setDuplicateInfo] = useState<{
    has_duplicates: boolean
    count: number
    existing_runs: { id: string; status: string; overall_verdict: string | null; completed_tests: number; total_tests: number; confidence: number; created_at: string }[]
  } | null>(null)
  const [duplicateAck, setDuplicateAck] = useState(false)
  const queryClient = useQueryClient()

  const { data: devices } = useQuery({
    queryKey: ['devices-list'],
    queryFn: () => devicesApi.list().then(r => r.data),
  })
  const { data: templates } = useQuery({
    queryKey: ['templates-list'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })

  const defaultTemplate = (templates as TestTemplate[] | undefined)?.find(t => t.is_default)
  const effectiveTemplateId = templateId || defaultTemplate?.id || ''

  // Check for duplicates when device+template selection changes
  useEffect(() => {
    setDuplicateInfo(null)
    setDuplicateAck(false)
    if (!deviceId || !effectiveTemplateId) return

    let cancelled = false
    testRunsApi.checkDuplicate(deviceId, effectiveTemplateId).then(res => {
      if (!cancelled) setDuplicateInfo(res.data)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [deviceId, effectiveTemplateId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (duplicateInfo?.has_duplicates && !duplicateAck) {
      toast.error('Please acknowledge the existing runs first')
      return
    }
    setLoading(true)
    try {
      await testRunsApi.create({ device_id: deviceId, template_id: effectiveTemplateId })
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-md bg-white dark:bg-dark-card rounded-lg shadow-2xl"
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-slate-700/50">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">New Test Run</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="label">Device</label>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} className="input" required>
              <option value="">Select a device...</option>
              {devices?.map((d: Device) => (
                <option key={d.id} value={d.id}>
                  {getPreferredDeviceName(d)} — {d.ip_address}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Test Template</label>
            <select
              value={templateId || defaultTemplate?.id || ''}
              onChange={(e) => setTemplateId(e.target.value)}
              className="input"
              required
            >
              <option value="">Select a template...</option>
              {templates?.map((t: TestTemplate) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.test_ids?.length || 0} tests){t.is_default ? ' — Recommended' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Duplicate warning */}
          {duplicateInfo?.has_duplicates && (
            <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <div className="text-xs">
                  <p className="font-semibold text-amber-800 dark:text-amber-300 mb-1">
                    {duplicateInfo.count} existing run{duplicateInfo.count > 1 ? 's' : ''} for this device + template
                  </p>
                  <div className="space-y-1 mb-2">
                    {duplicateInfo.existing_runs.slice(0, 3).map(r => (
                      <div key={r.id} className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
                        <StatusBadge status={r.status} />
                        <span>{r.completed_tests}/{r.total_tests} tests</span>
                        <ConfidenceBadge score={r.confidence} />
                        <span className="text-amber-500">{new Date(r.created_at).toLocaleDateString()}</span>
                      </div>
                    ))}
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={duplicateAck}
                      onChange={(e) => setDuplicateAck(e.target.checked)}
                      className="rounded border-amber-400 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-amber-700 dark:text-amber-400">I understand, create a new run anyway</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
            <button
              type="submit"
              disabled={loading || (duplicateInfo?.has_duplicates && !duplicateAck)}
              className="btn-primary"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Create Run
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
