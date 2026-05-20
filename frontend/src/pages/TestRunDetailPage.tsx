import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { testRunsApi, testResultsApi, reportsApi, resolveApiUrl, getApiErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useLiveTestRunState } from '@/hooks/useLiveTestRunState'
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  ArrowLeft, Loader2, Monitor,
  FileText, Cpu, Menu, X, Fingerprint, Save, ListChecks, CheckSquare, Square
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { profilesApi } from '@/lib/api'
import { StatusBadge } from '@/components/common/VerdictBadge'
import SegmentedProgressBar from '@/components/common/SegmentedProgressBar'
import SmartPrompt from '@/components/common/SmartPrompt'
import TestSidebar, { type TestResultItem } from '@/components/testing/TestSidebar'
import TestDetail, { type TestResultDetail } from '@/components/testing/TestDetail'
import WobblyCableAlert from '@/components/testing/WobblyCableAlert'
import SessionControls from '@/components/testing/SessionControls'
import ConnectionScenarioDialog from '@/components/testing/ConnectionScenarioDialog'
import type { TestResult, TestRun } from '@/lib/types'
import { isActiveTestRunStatus, isExecutingTestRunStatus, toLocalDateString } from '@/lib/testContracts'
import { normalizeTemplateName } from '@/lib/templateNames'
import { getManualEvidenceIssue } from '@/lib/manualEvidence'
import {
  buildProgressSegments,
  countCompletedResults,
  getNextPendingManualResultId,
  getPendingManualResultIds,
  getRunningTestIdFromProgress,
} from '@/lib/testRunDetailPage'
import { summarizeRunProgress } from '@/lib/testUi'
import { formatConnectionScenarioLabel } from '@/lib/universal-tests'
import {
  fetchTestRun,
  fetchTestRunResults,
  invalidateTestRunResource,
  refetchTestRunResource,
  testRunKeys,
} from '@/lib/testRunResources'

type CurrentTestMeta = {
  test_id: string
  test_name: string
  status: string
}

type ReportTemplateKey = 'generic'

const bulkVerdictOptions = [
  { value: 'na', label: 'N/A' },
]

const EMPTY_RESULTS: TestResult[] = []

function getCurrentTestFromMetadata(metadata: TestRun['run_metadata'] | undefined): CurrentTestMeta | null {
  const value = metadata?.current_test
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const current = value as Record<string, unknown>
  const testId = typeof current.test_id === 'string' ? current.test_id : ''
  if (!testId) return null
  return {
    test_id: testId,
    test_name: typeof current.test_name === 'string' && current.test_name.trim() ? current.test_name : testId,
    status: typeof current.status === 'string' ? current.status : 'running',
  }
}

function inferReportTemplateKey(run: TestRun | undefined): ReportTemplateKey {
  void run
  return 'generic'
}

export default function TestRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()

  // Ref tracks live WebSocket freshness so that the refetchInterval
  // callbacks (which are re-invoked by React Query on every tick) can read
  // it without creating a circular dependency between `ws` and the queries.
  const wsHealthyRef = useRef(false)
  const selectionPinnedRef = useRef(false)
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [scenarioDialogOpen, setScenarioDialogOpen] = useState(false)
  const [isActioning, setIsActioning] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [bulkManualSelectedIds, setBulkManualSelectedIds] = useState<string[]>([])
  const [bulkManualVerdict, setBulkManualVerdict] = useState('na')
  const [bulkManualNotes, setBulkManualNotes] = useState('')

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: testRunKeys.detail(id),
    queryFn: () => fetchTestRun(id!),
    enabled: !!id,
    refetchInterval: (query: { state: { data?: unknown } }) => {
      // WebSocket provides real-time updates — skip polling entirely when live.
      const d = query.state.data as Record<string, unknown> | undefined
      if (!isExecutingTestRunStatus(d?.status)) return false
      // Slow fallback poll when WS is unavailable (was 3s — caused polling storm).
      return wsHealthyRef.current ? 30000 : 10000
    },
  })

  const { data: results = EMPTY_RESULTS, isLoading: resultsLoading } = useQuery({
    queryKey: testRunKeys.results(id),
    queryFn: () => fetchTestRunResults(id!),
    enabled: !!id,
    refetchInterval: () => {
      // WebSocket invalidates this query on test_complete/run_complete messages.
      if (!isExecutingTestRunStatus(run?.status)) return false
      // Slow fallback poll when WS is unavailable (was 5s — caused polling storm).
      return wsHealthyRef.current ? 30000 : 10000
    },
  })

  const ws = useLiveTestRunState(id, run?.status)

  // Keep the ref in sync with the live WS connection state so that
  // the refetchInterval callbacks above can read the latest value.
  useEffect(() => {
    wsHealthyRef.current = ws.isConnected && ws.isFresh
  }, [ws.isConnected, ws.isFresh])

  useEffect(() => {
    if (!ws.lastProgress) return
    const msg = ws.lastProgress
    if (msg.type === 'test_start' && msg.data.test_id && !selectionPinnedRef.current) {
      const running = (results as TestResult[]).find((r) => r.test_id === msg.data.test_id)
      if (running) {
        setSelectedTestId(running.id)
      }
    }
  }, [ws.lastProgress, results])

  const currentTestFromRun = useMemo(
    () => getCurrentTestFromMetadata(run?.run_metadata),
    [run?.run_metadata]
  )

  const runningTestId = useMemo(() => {
    const wsRunningTestId = getRunningTestIdFromProgress(ws.lastProgress)
    if (wsRunningTestId) return wsRunningTestId
    if (
      !ws.lastProgress
      && isExecutingTestRunStatus(run?.status)
      && currentTestFromRun?.status === 'running'
    ) {
      return currentTestFromRun.test_id
    }
    return null
  }, [currentTestFromRun, run?.status, ws.lastProgress])

  useEffect(() => {
    if (ws.lastProgress || !currentTestFromRun || selectionPinnedRef.current) return
    const running = (results as TestResult[]).find((r) => r.test_id === currentTestFromRun.test_id)
    if (running) {
      setSelectedTestId(running.id)
    }
  }, [currentTestFromRun, results, ws.lastProgress])

  const sidebarResults: TestResultItem[] = useMemo(
    () =>
      (results as TestResult[]).map((r) => ({
        id: r.id,
        test_id: r.test_id || '',
        test_name: r.test_name || '',
        tier: (r.tier || 'automatic') as 'automatic' | 'guided_manual' | 'auto_na',
        verdict: r.verdict || null,
        tool: r.tool || null,
        is_essential: r.is_essential === 'yes',
        comment: r.comment || null,
        duration_seconds: r.duration_seconds ?? null,
        started_at: r.started_at || null,
      })),
    [results]
  )

  const selectedResult: TestResultDetail | null = useMemo(() => {
    if (!selectedTestId) return null
    const r = (results as TestResult[]).find((r) => r.id === selectedTestId)
    if (!r) return null
    return {
      id: r.id,
      test_id: r.test_id || '',
      test_name: r.test_name || '',
      tier: (r.tier || 'automatic') as 'automatic' | 'guided_manual' | 'auto_na',
      tool: r.tool || null,
      raw_output: r.raw_output || null,
      parsed_data: r.parsed_data || null,
      findings: r.findings || null,
      verdict: r.verdict || null,
      comment: r.comment || null,
      comment_override: r.comment_override || null,
      engineer_notes: r.engineer_notes || null,
      is_overridden: r.is_overridden ?? false,
      override_reason: r.override_reason || null,
      override_verdict: r.override_verdict || null,
      overridden_by_username: r.overridden_by_username || null,
      started_at: r.started_at || null,
      completed_at: r.completed_at || null,
      duration_seconds: r.duration_seconds ?? undefined,
      is_essential: r.is_essential === 'yes',
    }
  }, [selectedTestId, results])

  useEffect(() => {
    if (results.length > 0 && !selectedTestId) {
      setSelectedTestId((results as TestResult[])[0]?.id || null)
    }
  }, [results, selectedTestId])

  useEffect(() => {
    selectionPinnedRef.current = false
  }, [id])

  const completedCount = useMemo(
    () => countCompletedResults(results as TestResult[]),
    [results]
  )

  const progressPct =
    results.length > 0 ? Math.round((completedCount / results.length) * 100) : 0

  const readinessSummary = run?.readiness_summary ?? null
  const displayTotalCount = Math.max(run?.total_tests || 0, results.length)
  const displayCompletedCount = Math.min(completedCount, displayTotalCount)
  const displayTemplateName = normalizeTemplateName(run?.template_name)

  const runProgressSummary = useMemo(
    () => summarizeRunProgress(results as TestResult[], runningTestId, run?.status),
    [results, runningTestId, run?.status]
  )

  const progressSegments = useMemo(() => {
    return buildProgressSegments(results as TestResult[], runningTestId, run?.status)
  }, [results, runningTestId, run?.status])

  const handleStartTests = () => {
    setScenarioDialogOpen(true)
  }

  const handleConfirmStart = async (scenario: string) => {
    // Guard against double-click: if a start (or any action) is already in
    // flight, ignore subsequent invocations. Prevents the backend 500
    // "Test run is already executing" error.
    if (isActioning) return
    setIsActioning(true)
    try {
      const nextScenario = scenario === 'direct_cable' ? 'direct' : scenario
      if (run?.status === 'pending' && nextScenario !== run.connection_scenario) {
        await testRunsApi.update(id!, { connection_scenario: nextScenario })
      }
      const resp = await testRunsApi.start(id!)
      invalidateTestRunResource(queryClient, id)
      setScenarioDialogOpen(false)
      if (resp.data?.status === 'paused_cable') {
        toast(resp.data?.message || 'Device is not connected. Tests are paused until it comes back online.')
      } else {
        toast.success(resp.data?.message || 'Automated tests started')
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to start tests'))
    } finally {
      setIsActioning(false)
    }
  }

  const handlePause = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.pause(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Test run paused')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to pause'))
    } finally {
      setIsActioning(false)
    }
  }

  const handleResume = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.resume(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Test run resumed')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to resume'))
    } finally {
      setIsActioning(false)
    }
  }

  const handleCancel = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.cancel(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Test run cancelled')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to cancel'))
    } finally {
      setIsActioning(false)
    }
  }

  const handleFlagCable = async () => {
    try {
      await testRunsApi.pauseCable(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Cable disconnect flagged')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to flag cable'))
    }
  }

  const handleGenerateReport = async () => {
    try {
      const resp = await reportsApi.generate({
        test_run_id: id!,
        report_type: 'excel',
        template_key: inferReportTemplateKey(run),
        include_synopsis: !!run?.synopsis,
      })
      toast.success('Report generated successfully')
      if (resp.data?.download_url) {
        const a = document.createElement('a')
        a.href = resolveApiUrl(resp.data.download_url)
        a.download = resp.data.filename || `EDQ_Report_${id}.xlsx`
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        setTimeout(() => document.body.removeChild(a), 100)
      } else {
        toast.error('Report generated but no download URL was returned')
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Report generation failed'))
    }
  }

  const handleApprove = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.complete(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Test run approved and completed')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to approve'))
    } finally {
      setIsActioning(false)
    }
  }

  const handleRequestReview = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.requestReview(id!)
      invalidateTestRunResource(queryClient, id)
      toast.success('Submitted for review')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to submit for review'))
    } finally {
      setIsActioning(false)
    }
  }

  const findNextPendingManual = useCallback(
    (afterId: string) => getNextPendingManualResultId(results as TestResult[], afterId),
    [results]
  )

  const handleSelectTest = useCallback((testId: string) => {
    selectionPinnedRef.current = true
    setSelectedTestId(testId)
  }, [])

  const handleVisibleSidebarResultsChange = useCallback((visibleIds: string[]) => {
    if (visibleIds.length === 0) {
      setSelectedTestId(null)
      return
    }
    setSelectedTestId((current) => (
      current && visibleIds.includes(current) ? current : visibleIds[0]
    ))
  }, [])

  const handleSubmitManual = async (resultId: string, verdict: string, notes: string) => {
    setIsSubmitting(true)
    try {
      await testResultsApi.update(resultId, {
        verdict,
        comment_override: notes,
        engineer_notes: notes,
      })
      invalidateTestRunResource(queryClient, id)

      const nextId = findNextPendingManual(resultId)
      if (nextId) {
        setTimeout(() => setSelectedTestId(nextId), 600)
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to save result'))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSaveComment = async (resultId: string, comment: string) => {
    const commentOverride = comment.trim() ? comment : null
    queryClient.setQueryData(testRunKeys.results(id), (old: TestResult[] | undefined) => {
      if (!old) return old
      return old.map(r => r.id === resultId ? { ...r, comment_override: commentOverride } : r)
    })
    try {
      await testResultsApi.update(resultId, { comment_override: commentOverride })
    } catch (err: unknown) {
      queryClient.invalidateQueries({ queryKey: testRunKeys.results(id) })
      toast.error(getApiErrorMessage(err, 'Failed to save comments'))
    }
  }

  const handleOverride = async (resultId: string, verdict: string, reason: string) => {
    try {
      await testResultsApi.override(resultId, { verdict, override_reason: reason })
      invalidateTestRunResource(queryClient, id)
      toast.success('Verdict overridden')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Override failed'))
    }
  }

  const fingerprint = useMemo(() => {
    const value = run?.run_metadata?.fingerprint
    return value && typeof value === 'object' ? (value as Record<string, any>) : null
  }, [run])

  const handleSaveProfile = async () => {
    if (!id) return
    try {
      const resp = await profilesApi.autoLearn(id)
      if (resp.data?.created) {
        toast.success(resp.data.message || 'Profile saved')
        invalidateTestRunResource(queryClient, id)
      } else {
        toast.error(resp.data?.message || 'Could not create profile')
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to save profile'))
    }
  }

  const isOwner = user?.id === run?.engineer_id
  const canSelfApprove =
    user?.role === 'admin' || (isOwner && (user?.role === 'engineer' || user?.role === 'reviewer'))

  const pendingManualIds = useMemo(() => {
    return getPendingManualResultIds(results as TestResult[])
  }, [results])

  const pendingManualCount = pendingManualIds.length
  const pendingManualResults = useMemo(
    () =>
      (results as TestResult[]).filter(
        (result) => result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending')
      ),
    [results]
  )
  const bulkManualSelectedSet = useMemo(
    () => new Set(bulkManualSelectedIds),
    [bulkManualSelectedIds]
  )
  const bulkManualEvidenceIssue = bulkManualVerdict !== 'pending'
    ? getManualEvidenceIssue(bulkManualNotes)
    : null

  const firstPendingManualId = pendingManualIds[0] || null

  useEffect(() => {
    const validIds = new Set(pendingManualResults.map((result) => result.id))
    setBulkManualSelectedIds((current) => {
      const next = current.filter((resultId) => validIds.has(resultId))
      return next.length === current.length ? current : next
    })
  }, [pendingManualResults])

  const toggleBulkManualSelection = useCallback((resultId: string) => {
    setBulkManualSelectedIds((current) =>
      current.includes(resultId)
        ? current.filter((id) => id !== resultId)
        : [...current, resultId]
    )
  }, [])

  const handleApplyBulkManual = async () => {
    if (bulkManualSelectedIds.length === 0) return
    if (bulkManualEvidenceIssue) {
      toast.error(bulkManualEvidenceIssue)
      return
    }
    setIsSubmitting(true)
    try {
      const trimmedNotes = bulkManualNotes.trim()
      await testResultsApi.bulkUpdateManual({
        result_ids: bulkManualSelectedIds,
        verdict: bulkManualVerdict,
        ...(trimmedNotes ? { engineer_notes: trimmedNotes } : {}),
      })
      await refetchTestRunResource(queryClient, id!)
      toast.success(`Updated ${bulkManualSelectedIds.length} manual tests`)
      setBulkManualSelectedIds([])
      setBulkManualNotes('')
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to update manual tests'))
    } finally {
      setIsSubmitting(false)
    }
  }

  // Auto-navigate to first pending manual test when run enters awaiting_manual
  useEffect(() => {
    if (run?.status === 'awaiting_manual' && firstPendingManualId && !selectedTestId) {
      setSelectedTestId(firstPendingManualId)
    }
  }, [run?.status, firstPendingManualId, selectedTestId])

  const readinessVariant = useMemo(() => {
    if (!readinessSummary) return 'info' as const
    if (readinessSummary.operational_ready) return 'success' as const
    if (readinessSummary.level === 'blocked') return 'error' as const
    if (
      readinessSummary.level === 'awaiting_manual_evidence'
      || readinessSummary.level === 'awaiting_review_signoff'
      || readinessSummary.level === 'review_required'
      || readinessSummary.level === 'conditional'
    ) {
      return 'warning' as const
    }
    return 'info' as const
  }, [readinessSummary])

  const reportBlockedReason = useMemo(() => {
    if (!readinessSummary || readinessSummary.report_ready) return null
    return readinessSummary.next_step || readinessSummary.summary || 'Report is not ready yet.'
  }, [readinessSummary])

  const compactSummaryItems = useMemo(() => {
    const items: string[] = []
    if (readinessSummary) {
      if (readinessSummary.level === 'in_progress' && isActiveTestRunStatus(run?.status)) {
        items.push(runProgressSummary.progressLabel)
      } else {
        items.push(`${readinessSummary.label} (${readinessSummary.score}/10)`)
      }
    }
    return items
  }, [readinessSummary, run?.status, runProgressSummary.progressLabel])

  const compactSummaryText = useMemo(() => {
    if (run?.status === 'awaiting_manual' && pendingManualCount > 0) {
      return `${pendingManualCount} manual test${pendingManualCount > 1 ? 's' : ''} still need evidence.`
    }
    if (readinessSummary?.level === 'in_progress' && isActiveTestRunStatus(run?.status)) {
      return runProgressSummary.detailText
    }
    if (readinessSummary?.summary) return readinessSummary.summary
    return runProgressSummary.detailText
  }, [pendingManualCount, readinessSummary, run?.status, runProgressSummary.detailText])

  if (runLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-3.5rem)]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
          <p className="text-sm text-zinc-500">Loading test session...</p>
        </div>
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-3.5rem)] gap-3">
        <p className="text-zinc-500">Test run not found</p>
        <Link to="/test-runs" className="text-brand-500 text-sm hover:underline">
          Back to test runs
        </Link>
      </div>
    )
  }

  const runIsExecuting =
    run.status === 'running' || run.status === 'selecting_interface' || run.status === 'syncing'

  const liveOutput =
    selectedResult && runIsExecuting && runningTestId === selectedResult.test_id
      ? ws.terminalOutput[selectedResult.test_id] || ''
      : ''

  // Cable alert: prefer WS cable status, but fall back to REST poll status.
  // Only treat WS disconnection as a warning if the socket was previously
  // connected — avoids a false "reconnecting" flash on page load/refresh.
  const isRunActive = isActiveTestRunStatus(run.status)
  const cableAlertStatus =
    ws.cableStatus !== 'connected'
      ? ws.cableStatus
      : run.status === 'paused_cable'
        ? 'disconnected'
        : ws.hasConnectedOnce && !ws.isConnected && isRunActive
          ? 'reconnecting'
          : 'connected'

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col lg:h-[calc(100vh-3.5rem)]">
      <div className="flex-shrink-0 bg-white dark:bg-dark-card border-b border-zinc-200 dark:border-slate-700/50 px-4 py-3">
        <div className="flex items-center gap-3 mb-2">
          <Link
            to="/test-runs"
            className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
            title="Back to test runs"
          >
            <ArrowLeft className="w-4 h-4 text-zinc-500" />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 truncate">
                {run.device_name || run.device_ip || `Device ${run.device_id?.slice(0, 8)}`}
              </h1>
              <StatusBadge status={run.status} />
              {ws.isConnected && ws.isFresh && (
                <span className="flex items-center gap-1 text-[10px] text-green-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                  Live
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500 mt-0.5 flex-wrap">
              {run.device_ip && (
                <span className="flex items-center gap-1">
                  <Monitor className="w-3 h-3" />
                  {run.device_ip}
                </span>
              )}
              {displayTemplateName && (
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  {displayTemplateName}
                </span>
              )}
              {run.connection_scenario && (
                <span className="flex items-center gap-1">
                  <Cpu className="w-3 h-3" />
                  {formatConnectionScenarioLabel(run.connection_scenario)}
                </span>
              )}
              {run.started_at && (
                <span>Started {toLocalDateString(run.started_at)}</span>
              )}
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="lg:hidden p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
            title="Toggle test list"
            aria-label="Toggle test list"
          >
            {sidebarOpen ? <X className="w-5 h-5 text-zinc-600" /> : <Menu className="w-5 h-5 text-zinc-600" />}
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex-1">
            <SegmentedProgressBar
              total={displayTotalCount}
              segments={progressSegments}
            />
            <div className="mt-1.5 flex items-center justify-between gap-3 text-[11px] text-zinc-500 dark:text-slate-400">
              <span aria-live="polite">{runProgressSummary.progressLabel}</span>
              <span>{runProgressSummary.detailText}</span>
            </div>
          </div>
          <span className="text-xs font-mono text-zinc-500 flex-shrink-0" aria-live="polite">
            {run.progress_pct ?? progressPct}% ({displayCompletedCount}/{displayTotalCount})
          </span>
        </div>
      </div>

      <div className="flex-shrink-0 px-4 pt-3">
        <SmartPrompt
          variant={readinessVariant}
          action={
            firstPendingManualId
              ? {
                  label: 'Next manual',
                  onClick: () => handleSelectTest(firstPendingManualId),
                }
              : undefined
          }
        >
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <strong className="text-sm">{compactSummaryText}</strong>
              {compactSummaryItems.map((item) => (
                <span key={item} className="rounded-full bg-black/5 dark:bg-white/5 px-2 py-0.5">
                  {item}
                </span>
              ))}
              {readinessSummary && (
                <span className="rounded-full bg-black/5 dark:bg-white/5 px-2 py-0.5">
                  Report {readinessSummary.report_ready ? 'ready' : 'blocked'}
                </span>
              )}
            </div>
            {fingerprint && (
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 px-2 py-0.5">
                  <Fingerprint className="w-3 h-3" />
                  {fingerprint.category?.replace(/_/g, ' ') || 'Unknown'}
                </span>
                {fingerprint.matched_profile_name && <span>Profile: {fingerprint.matched_profile_name}</span>}
                {fingerprint.skip_test_ids?.length > 0 && (
                  <span>Skipped {fingerprint.skip_test_ids.length} tests</span>
                )}
                {!fingerprint.matched_profile_id && fingerprint.category !== 'unknown' && (
                  <button
                    onClick={handleSaveProfile}
                    className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-2 py-0.5 text-white hover:bg-indigo-700"
                    title="Save current fingerprint as reusable profile"
                  >
                    <Save className="w-3 h-3" />
                    Save profile
                  </button>
                )}
              </div>
            )}
          </div>
        </SmartPrompt>
      </div>

      {run.status === 'awaiting_manual' && pendingManualResults.length > 1 && (
        <div className="flex-shrink-0 border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50 dark:bg-slate-900/40 px-4 py-2">
          <div className="flex flex-col gap-2 2xl:flex-row 2xl:items-center">
            <div className="flex items-center gap-2 text-xs font-semibold text-zinc-600 dark:text-slate-300">
              <ListChecks className="w-4 h-4 text-amber-500" />
              <span>Bulk manual result</span>
              <span className="rounded-full bg-white dark:bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-zinc-500 dark:text-slate-400">
                {bulkManualSelectedIds.length} selected
              </span>
            </div>

            <div className="flex flex-1 gap-1 overflow-x-auto pb-1 2xl:pb-0">
              {pendingManualResults.map((result) => {
                const isSelected = bulkManualSelectedSet.has(result.id)
                return (
                  <button
                    key={result.id}
                    type="button"
                    onClick={() => toggleBulkManualSelection(result.id)}
                    title={`${result.test_id} - ${result.test_name}`}
                    className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] transition-colors
                      ${isSelected
                        ? 'border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
                        : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                      }`}
                  >
                    {isSelected ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                    <span className="font-mono">{result.test_id}</span>
                  </button>
                )
              })}
            </div>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setBulkManualSelectedIds(pendingManualResults.map((result) => result.id))}
                  className="btn-secondary h-8 px-2 text-xs"
                >
                  <CheckSquare className="w-3.5 h-3.5" />
                  Select all
                </button>
                <button
                  type="button"
                  onClick={() => setBulkManualSelectedIds([])}
                  className="btn-secondary h-8 px-2 text-xs"
                >
                  <X className="w-3.5 h-3.5" />
                  Deselect all
                </button>
              </div>
              <select
                aria-label="Bulk manual verdict"
                title="Bulk manual verdict"
                value={bulkManualVerdict}
                onChange={(event) => setBulkManualVerdict(event.target.value)}
                className="input h-8 min-w-28 text-sm"
              >
                {bulkVerdictOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <input
                type="text"
                aria-label="Bulk manual comments"
                value={bulkManualNotes}
                onChange={(event) => setBulkManualNotes(event.target.value)}
                placeholder="Why these tests do not apply..."
                className={`input h-8 min-w-0 text-sm sm:w-64 ${bulkManualEvidenceIssue ? 'border-amber-400' : ''}`}
              />
              {bulkManualEvidenceIssue && (
                <span className="text-xs text-amber-700 dark:text-amber-300">
                  {bulkManualEvidenceIssue}
                </span>
              )}
              <button
                type="button"
                onClick={handleApplyBulkManual}
                disabled={bulkManualSelectedIds.length === 0 || isSubmitting || Boolean(bulkManualEvidenceIssue)}
                className="btn-primary h-8 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ListChecks className="w-4 h-4" />}
                Apply
              </button>
            </div>
          </div>
        </div>
      )}

      <AnimatePresence>
        {cableAlertStatus !== 'connected' && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="flex-shrink-0 px-4 pt-2 overflow-hidden"
            aria-live="assertive"
          >
            <WobblyCableAlert status={cableAlertStatus} probe={ws.cableProbe} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative flex min-h-[34rem] flex-1 overflow-hidden lg:min-h-0">
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div
          className={`absolute lg:relative z-40 lg:z-auto h-full w-[340px] max-w-[90vw] flex-shrink-0
            transition-transform duration-200
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        >
          <TestSidebar
            results={sidebarResults}
            selectedTestId={selectedTestId}
            runningTestId={runIsExecuting ? runningTestId : null}
            runStatus={run.status}
            onSelectTest={(testId) => {
              handleSelectTest(testId)
              setSidebarOpen(false)
            }}
            onVisibleResultsChange={handleVisibleSidebarResultsChange}
            className="h-full"
          />
        </div>

        <div className="flex-1 min-w-0 bg-white dark:bg-dark-card overflow-hidden">
          {selectedResult ? (
            <TestDetail
              key={selectedResult.id}
              result={selectedResult}
              liveOutput={liveOutput}
              isRunning={runIsExecuting && runningTestId === selectedResult.test_id}
              runStatus={run.status}
              userRole={user?.role || 'engineer'}
              onSubmitManual={handleSubmitManual}
              onOverride={handleOverride}
              onSaveComment={handleSaveComment}
              isSubmitting={isSubmitting}
              manualProgress={
                selectedResult.tier === 'guided_manual'
                  ? { current: pendingManualCount, total: (results as TestResult[]).filter(r => r.tier === 'guided_manual').length }
                  : null
              }
            />
          ) : resultsLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
            </div>
          ) : results.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
              <div className="w-12 h-12 rounded-full bg-zinc-100 dark:bg-slate-800 flex items-center justify-center">
                <FileText className="w-6 h-6 text-zinc-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-700 dark:text-slate-300">No tests loaded yet</p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Start automated tests to begin the qualification process.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-zinc-500">Select a test from the sidebar</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex-shrink-0">
        <SessionControls
          runStatus={run.status}
          canSelfApprove={canSelfApprove}
          isOwner={isOwner}
          pendingManualCount={pendingManualCount}
          canGenerateReport={Boolean(readinessSummary?.report_ready)}
          reportBlockedReason={reportBlockedReason}
          onStart={handleStartTests}
          onPause={handlePause}
          onResume={handleResume}
          onCancel={handleCancel}
          onFlagCable={handleFlagCable}
          onGenerateReport={handleGenerateReport}
          onApprove={handleApprove}
          onRequestReview={handleRequestReview}
          isActioning={isActioning}
          runningTestName={
            runIsExecuting && runningTestId
              ? (results as TestResult[]).find((r) => r.test_id === runningTestId)?.test_name
                || currentTestFromRun?.test_name
                || runningTestId
              : null
          }
          progressPct={run.progress_pct ?? progressPct}
          completedCount={completedCount}
          totalCount={results.length}
          etaText={null}
        />
      </div>

      <ConnectionScenarioDialog
        open={scenarioDialogOpen}
        onOpenChange={setScenarioDialogOpen}
        onConfirm={handleConfirmStart}
        isLoading={isActioning}
      />
    </div>
  )
}
