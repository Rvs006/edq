import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { testRunsApi, testResultsApi, reportsApi, getApiErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useTestRunWebSocket } from '@/hooks/useTestRunWebSocket'
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  ArrowLeft, Loader2, Monitor,
  FileText, Cpu, Menu, X, Fingerprint, Zap, Save
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { profilesApi } from '@/lib/api'
import { StatusBadge } from '@/components/common/VerdictBadge'
import SegmentedProgressBar from '@/components/common/SegmentedProgressBar'
import SmartPrompt from '@/components/common/SmartPrompt'
import CsvExportButton from '@/components/common/CsvExportButton'
import TestSidebar, { type TestResultItem } from '@/components/testing/TestSidebar'
import TestDetail, { type TestResultDetail } from '@/components/testing/TestDetail'
import WobblyCableAlert from '@/components/testing/WobblyCableAlert'
import SessionControls from '@/components/testing/SessionControls'
import ConnectionScenarioDialog from '@/components/testing/ConnectionScenarioDialog'
import type { TestResult } from '@/lib/types'
import { isActiveTestRunStatus, toLocalDateString } from '@/lib/testContracts'
import { normalizeTemplateName } from '@/lib/templateNames'
import {
  buildProgressSegments,
  countCompletedResults,
  getNextPendingManualResultId,
  getPendingManualResultIds,
  getRunningTestIdFromProgress,
} from '@/lib/testRunDetailPage'
import { summarizeRunProgress } from '@/lib/testUi'

export default function TestRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const invalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Ref tracks live WebSocket freshness so that the refetchInterval
  // callbacks (which are re-invoked by React Query on every tick) can read
  // it without creating a circular dependency between `ws` and the queries.
  const wsHealthyRef = useRef(false)
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [scenarioDialogOpen, setScenarioDialogOpen] = useState(false)
  const [isActioning, setIsActioning] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: ['test-run', id],
    queryFn: () => testRunsApi.get(id!).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query: { state: { data?: unknown } }) => {
      // WebSocket provides real-time updates — skip polling entirely when live.
      const d = query.state.data as Record<string, unknown> | undefined
      if (!isActiveTestRunStatus(d?.status)) return false
      // Slow fallback poll when WS is unavailable (was 3s — caused polling storm).
      return wsHealthyRef.current ? 30000 : 10000
    },
  })

  const { data: results = [], isLoading: resultsLoading } = useQuery({
    queryKey: ['test-results', id],
    queryFn: () => testResultsApi.list({ test_run_id: id }).then((r) => r.data),
    enabled: !!id,
    refetchInterval: () => {
      // WebSocket invalidates this query on test_complete/run_complete messages.
      if (!isActiveTestRunStatus(run?.status)) return false
      // Slow fallback poll when WS is unavailable (was 5s — caused polling storm).
      return wsHealthyRef.current ? 30000 : 10000
    },
  })

  const ws = useTestRunWebSocket(
    run && isActiveTestRunStatus(run.status) ? id : undefined
  )

  // Keep the ref in sync with the live WS connection state so that
  // the refetchInterval callbacks above can read the latest value.
  useEffect(() => {
    wsHealthyRef.current = ws.isConnected && ws.isFresh
  }, [ws.isConnected, ws.isFresh])

  useEffect(() => {
    return () => {
      if (invalidateTimerRef.current) {
        clearTimeout(invalidateTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!ws.lastProgress) return
    const msg = ws.lastProgress

    const shouldRefreshRun =
      msg.type === 'run_started'
      || msg.type === 'run_complete'
      || msg.type === 'run_failed'
      || msg.type === 'run_error'
      || msg.type === 'cable_disconnected'
      || msg.type === 'cable_reconnected'
      || msg.type === 'cable_timeout'
    const shouldRefreshResults = msg.type === 'test_complete'

    if (shouldRefreshRun || shouldRefreshResults) {
      if (invalidateTimerRef.current) clearTimeout(invalidateTimerRef.current)
      invalidateTimerRef.current = setTimeout(() => {
        if (shouldRefreshResults) {
          queryClient.invalidateQueries({ queryKey: ['test-results', id] })
        }
        if (shouldRefreshRun || shouldRefreshResults) {
          queryClient.invalidateQueries({ queryKey: ['test-run', id] })
        }
      }, 500)
    }
  }, [ws.lastProgress, id, queryClient])

  useEffect(() => {
    if (!ws.lastProgress) return
    const msg = ws.lastProgress
    if (msg.type === 'test_start' && msg.data.test_id) {
      const running = (results as TestResult[]).find((r) => r.test_id === msg.data.test_id)
      if (running) {
        setSelectedTestId(running.id)
      }
    }
  }, [ws.lastProgress, results])

  // Sync state after WebSocket reconnection (catch missed messages)
  useEffect(() => {
    if (ws.reconnectCount > 0) {
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
    }
  }, [ws.reconnectCount, id, queryClient])

  const runningTestId = useMemo(() => {
    return getRunningTestIdFromProgress(ws.lastProgress)
  }, [ws.lastProgress])

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
      if (scenario !== 'direct_cable') {
        await testRunsApi.update(id!, { connection_scenario: scenario })
      }
      const resp = await testRunsApi.start(id!)
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
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
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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
        include_synopsis: !!run?.synopsis,
      })
      toast.success('Report generated successfully')
      if (resp.data?.filename) {
        const blob = await reportsApi.download(resp.data.filename)
        const url = URL.createObjectURL(new Blob([blob.data]))
        const a = document.createElement('a')
        a.href = url
        a.download = resp.data.filename
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Report generation failed'))
    }
  }

  const handleApprove = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.complete(id!)
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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

  const handleSubmitManual = async (resultId: string, verdict: string, notes: string) => {
    setIsSubmitting(true)
    try {
      await testResultsApi.update(resultId, {
        verdict,
        engineer_notes: notes,
      })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })

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

  const handleSaveNotes = async (resultId: string, notes: string) => {
    // Optimistic update - immediately update the cache
    queryClient.setQueryData(['test-results', id], (old: TestResult[] | undefined) => {
      if (!old) return old
      return old.map(r => r.id === resultId ? { ...r, engineer_notes: notes } : r)
    })
    try {
      await testResultsApi.update(resultId, { engineer_notes: notes })
      // No need to invalidate - we already updated the cache
    } catch (err: unknown) {
      // Revert on error
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
      toast.error(getApiErrorMessage(err, 'Failed to save notes'))
    }
  }

  const handleOverride = async (resultId: string, verdict: string, reason: string) => {
    try {
      await testResultsApi.override(resultId, { verdict, override_reason: reason })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
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
        queryClient.invalidateQueries({ queryKey: ['test-run', id] })
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

  const firstPendingManualId = pendingManualIds[0] || null

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
    if (readinessSummary) items.push(`${readinessSummary.label} (${readinessSummary.score}/10)`)
    return items
  }, [readinessSummary])

  const compactSummaryText = useMemo(() => {
    if (run?.status === 'awaiting_manual' && pendingManualCount > 0) {
      return `${pendingManualCount} manual test${pendingManualCount > 1 ? 's' : ''} still need evidence.`
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
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
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
                  {run.connection_scenario.replace(/_/g, ' ')}
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
          <CsvExportButton
            results={sidebarResults}
            deviceName={run.device_name || `device-${run.device_id?.slice(0, 8)}`}
          />
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
                  onClick: () => setSelectedTestId(firstPendingManualId),
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

      <div className="flex-1 flex min-h-0 relative overflow-hidden">
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
              setSelectedTestId(testId)
              setSidebarOpen(false)
            }}
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
              onSaveNotes={handleSaveNotes}
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
              ? (results as TestResult[]).find((r) => r.test_id === runningTestId)?.test_name || runningTestId
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
