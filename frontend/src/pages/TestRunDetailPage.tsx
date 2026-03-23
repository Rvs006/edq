import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { testRunsApi, testResultsApi, reportsApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useTestRunWebSocket } from '@/hooks/useTestRunWebSocket'
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  ArrowLeft, Loader2, Monitor, Wifi, WifiOff,
  FileText, Cpu, Menu, X
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { StatusBadge } from '@/components/common/VerdictBadge'
import TestSidebar, { type TestResultItem } from '@/components/testing/TestSidebar'
import TestDetail, { type TestResultDetail } from '@/components/testing/TestDetail'
import WobblyCableAlert from '@/components/testing/WobblyCableAlert'
import SessionControls from '@/components/testing/SessionControls'
import ConnectionScenarioDialog from '@/components/testing/ConnectionScenarioDialog'

export default function TestRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const [selectedTestId, setSelectedTestId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [scenarioDialogOpen, setScenarioDialogOpen] = useState(false)
  const [isActioning, setIsActioning] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: ['test-run', id],
    queryFn: () => testRunsApi.get(id!).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const d = query.state.data as any
      return d?.status === 'running' || d?.status === 'discovering' ? 3000 : false
    },
  })

  const { data: results = [], isLoading: resultsLoading } = useQuery({
    queryKey: ['test-results', id],
    queryFn: () => testResultsApi.list({ test_run_id: id }).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      return run?.status === 'running' ? 5000 : false
    },
  })

  const ws = useTestRunWebSocket(
    run?.status === 'running' || run?.status === 'discovering' ? id : undefined
  )

  useEffect(() => {
    if (!ws.lastProgress) return
    const msg = ws.lastProgress

    if (msg.type === 'test_complete' || msg.type === 'run_complete') {
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
    }

    if (msg.type === 'test_start' && msg.data.test_number) {
      const running = results.find((r: any) => r.test_number === msg.data.test_number)
      if (running) {
        setSelectedTestId(running.id)
      }
    }
  }, [ws.lastProgress, id, queryClient, results])

  const runningTestNumber = useMemo(() => {
    if (!ws.lastProgress) return null
    const msg = ws.lastProgress
    if (msg.type === 'test_start') return msg.data.test_number || null
    if (msg.type === 'test_progress' && msg.data.status === 'running')
      return msg.data.test_number || null
    return null
  }, [ws.lastProgress])

  const sidebarResults: TestResultItem[] = useMemo(
    () =>
      (results as any[]).map((r: any) => ({
        id: r.id,
        test_number: r.test_number || r.test_id || '',
        test_name: r.test_name || '',
        tier: r.tier || 'automatic',
        verdict: r.verdict || null,
        status: r.status,
        tool_used: r.tool_used || r.tool || null,
        essential_pass: r.essential_pass ?? false,
      })),
    [results]
  )

  const selectedResult: TestResultDetail | null = useMemo(() => {
    if (!selectedTestId) return null
    const r = (results as any[]).find((r: any) => r.id === selectedTestId)
    if (!r) return null
    return {
      id: r.id,
      test_number: r.test_number || r.test_id || '',
      test_name: r.test_name || '',
      tier: r.tier || 'automatic',
      tool_used: r.tool_used || r.tool || null,
      tool_command: r.tool_command || null,
      raw_stdout: r.raw_stdout || null,
      raw_stderr: r.raw_stderr || null,
      parsed_findings: r.parsed_findings || r.findings || null,
      verdict: r.verdict || null,
      auto_comment: r.auto_comment || r.comment || null,
      engineer_selection: r.engineer_selection || null,
      engineer_notes: r.engineer_notes || null,
      is_overridden: r.is_overridden ?? false,
      override_reason: r.override_reason || null,
      overridden_by: r.overridden_by || null,
      script_flag: r.script_flag || 'No',
      started_at: r.started_at || null,
      completed_at: r.completed_at || null,
      duration_seconds: r.duration_seconds,
      essential_pass: r.essential_pass ?? false,
      test_description: r.test_description || r.description || null,
      pass_criteria: r.pass_criteria || null,
    }
  }, [selectedTestId, results])

  useEffect(() => {
    if (results.length > 0 && !selectedTestId) {
      setSelectedTestId((results as any[])[0]?.id || null)
    }
  }, [results, selectedTestId])

  const completedCount = useMemo(
    () => (results as any[]).filter((r: any) => r.verdict && r.verdict !== 'pending').length,
    [results]
  )

  const progressPct =
    results.length > 0 ? Math.round((completedCount / results.length) * 100) : 0

  const handleStartTests = () => {
    setScenarioDialogOpen(true)
  }

  const handleConfirmStart = async (scenario: string) => {
    setIsActioning(true)
    try {
      if (scenario !== 'direct_cable') {
        await testRunsApi.update(id!, { connection_scenario: scenario })
      }
      await testRunsApi.start(id!)
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      setScenarioDialogOpen(false)
      toast.success('Automated tests started')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to start tests')
    } finally {
      setIsActioning(false)
    }
  }

  const handlePause = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.update(id!, { status: 'paused_manual' })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('Test run paused')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to pause')
    } finally {
      setIsActioning(false)
    }
  }

  const handleResume = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.start(id!)
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('Test run resumed')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to resume')
    } finally {
      setIsActioning(false)
    }
  }

  const handleFlagCable = async () => {
    try {
      await testRunsApi.update(id!, { status: 'paused_cable' })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('Cable disconnect flagged')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to flag cable')
    }
  }

  const handleGenerateReport = async () => {
    try {
      const resp = await reportsApi.generate({
        test_run_id: id,
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
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Report generation failed')
    }
  }

  const handleApprove = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.complete(id!)
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('Test run approved and completed')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to approve')
    } finally {
      setIsActioning(false)
    }
  }

  const handleRequestReview = async () => {
    setIsActioning(true)
    try {
      await testRunsApi.update(id!, { status: 'awaiting_review' })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('Submitted for review')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to submit for review')
    } finally {
      setIsActioning(false)
    }
  }

  const findNextPendingManual = useCallback(
    (afterId: string) => {
      const manualTests = (results as any[]).filter(
        (r: any) => r.tier === 'guided_manual'
      )
      const currentIdx = manualTests.findIndex((r: any) => r.id === afterId)
      for (let i = currentIdx + 1; i < manualTests.length; i++) {
        if (!manualTests[i].verdict || manualTests[i].verdict === 'pending') {
          return manualTests[i].id
        }
      }
      for (let i = 0; i < currentIdx; i++) {
        if (!manualTests[i].verdict || manualTests[i].verdict === 'pending') {
          return manualTests[i].id
        }
      }
      return null
    },
    [results]
  )

  const handleSubmitManual = async (resultId: string, verdict: string, notes: string) => {
    setIsSubmitting(true)
    try {
      await testResultsApi.update(resultId, {
        verdict,
        engineer_notes: notes,
        engineer_selection: verdict,
      })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })

      const nextId = findNextPendingManual(resultId)
      if (nextId) {
        setTimeout(() => setSelectedTestId(nextId), 600)
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save result')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleOverride = async (resultId: string, verdict: string, reason: string) => {
    try {
      await testResultsApi.override(resultId, { verdict, override_reason: reason })
      queryClient.invalidateQueries({ queryKey: ['test-results', id] })
      toast.success('Verdict overridden')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Override failed')
    }
  }

  const isOwner = user?.id === run?.user_id
  const canSelfApprove =
    user?.role === 'admin' || (isOwner && (user?.role === 'engineer' || user?.role === 'reviewer'))

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

  const liveOutput =
    selectedResult && runningTestNumber === selectedResult.test_number
      ? ws.terminalOutput[selectedResult.test_number] || ''
      : ''

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-shrink-0 bg-white border-b border-zinc-200 px-4 py-3">
        <div className="flex items-center gap-3 mb-2">
          <Link
            to="/test-runs"
            className="p-1 rounded-lg hover:bg-zinc-100 transition-colors flex-shrink-0"
          >
            <ArrowLeft className="w-4 h-4 text-zinc-500" />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-sm font-semibold text-zinc-900 truncate">
                {run.device_name || `Device ${run.device_id?.slice(0, 8)}`}
              </h1>
              <StatusBadge status={run.status} />
              {ws.isConnected && (
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
              {run.template_name && (
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  {run.template_name}
                </span>
              )}
              {run.connection_scenario && (
                <span className="flex items-center gap-1">
                  <Cpu className="w-3 h-3" />
                  {run.connection_scenario.replace(/_/g, ' ')}
                </span>
              )}
              {run.started_at && (
                <span>Started {new Date(run.started_at).toLocaleString()}</span>
              )}
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="lg:hidden p-1.5 rounded-lg hover:bg-zinc-100 transition-colors flex-shrink-0"
          >
            {sidebarOpen ? <X className="w-5 h-5 text-zinc-600" /> : <Menu className="w-5 h-5 text-zinc-600" />}
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-500 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${run.progress_pct ?? progressPct}%` }}
            />
          </div>
          <span className="text-xs font-mono text-zinc-500 flex-shrink-0">
            {run.progress_pct ?? progressPct}% ({completedCount}/{results.length})
          </span>
        </div>
      </div>

      <AnimatePresence>
        {ws.cableStatus !== 'connected' && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="flex-shrink-0 px-4 pt-2 overflow-hidden"
          >
            <WobblyCableAlert status={ws.cableStatus} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex min-h-0 relative">
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div
          className={`absolute lg:relative z-40 lg:z-auto h-full w-[280px] flex-shrink-0
            transition-transform duration-200
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        >
          <TestSidebar
            results={sidebarResults}
            selectedTestId={selectedTestId}
            runningTestNumber={runningTestNumber}
            onSelectTest={(testId) => {
              setSelectedTestId(testId)
              setSidebarOpen(false)
            }}
            className="h-full"
          />
        </div>

        <div className="flex-1 min-w-0 bg-white">
          {selectedResult ? (
            <TestDetail
              key={selectedResult.id}
              result={selectedResult}
              liveOutput={liveOutput}
              isRunning={runningTestNumber === selectedResult.test_number}
              userRole={user?.role || 'engineer'}
              userId={user?.id || ''}
              onSubmitManual={handleSubmitManual}
              onOverride={handleOverride}
              isSubmitting={isSubmitting}
            />
          ) : resultsLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
            </div>
          ) : results.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
              <div className="w-12 h-12 rounded-full bg-zinc-100 flex items-center justify-center">
                <FileText className="w-6 h-6 text-zinc-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-700">No tests loaded yet</p>
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
          onStart={handleStartTests}
          onPause={handlePause}
          onResume={handleResume}
          onFlagCable={handleFlagCable}
          onGenerateReport={handleGenerateReport}
          onApprove={handleApprove}
          onRequestReview={handleRequestReview}
          isActioning={isActioning}
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
