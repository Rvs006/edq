import {
  Play, Pause, Unplug, FileBarChart, CheckCircle2,
  Send, Loader2, Activity, StopCircle,
} from 'lucide-react'

interface SessionControlsProps {
  runStatus: string
  canSelfApprove: boolean
  isOwner: boolean
  pendingManualCount: number
  canGenerateReport?: boolean
  reportBlockedReason?: string | null
  onStart: () => void
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onFlagCable: () => void
  onGenerateReport: () => void
  onApprove: () => void
  onRequestReview: () => void
  isActioning: boolean
  runningTestName?: string | null
  progressPct?: number
  completedCount?: number
  totalCount?: number
  etaText?: string | null
}

export default function SessionControls({
  runStatus,
  canSelfApprove,
  isOwner,
  pendingManualCount,
  canGenerateReport = true,
  reportBlockedReason = null,
  onStart,
  onPause,
  onResume,
  onCancel,
  onFlagCable,
  onGenerateReport,
  onApprove,
  onRequestReview,
  isActioning,
  runningTestName,
  progressPct = 0,
  completedCount = 0,
  totalCount = 0,
  etaText: _etaText,
}: SessionControlsProps) {
  const isRunning = runStatus === 'running' || runStatus === 'selecting_interface' || runStatus === 'syncing'
  const isPaused = runStatus === 'paused_manual' || runStatus === 'paused_cable'
  const isPending = runStatus === 'pending'
  const isComplete = runStatus === 'completed'
  const isAwaitingReview = runStatus === 'awaiting_review'
  const isAwaitingManual = runStatus === 'awaiting_manual'

  return (
    <div className="bg-white dark:bg-dark-card border-t border-zinc-200 dark:border-slate-700/50">
      {isRunning && runningTestName && (
        <div className="px-4 pt-2">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-blue-500 animate-pulse flex-shrink-0" />
            <span className="text-xs font-medium text-blue-700 dark:text-blue-300 truncate">
              Running: {runningTestName}
            </span>
          </div>
        </div>
      )}

      {isAwaitingManual && (
        <div className="fixed bottom-16 right-4 z-50 max-w-xs animate-in slide-in-from-right-5 fade-in duration-300">
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 shadow-lg">
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0 mt-0.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
            </span>
            <span className="text-xs font-medium text-amber-800 dark:text-amber-300">
              Manual tests need your input. Open each amber item from the sidebar.
            </span>
          </div>
        </div>
      )}

      {isComplete && (
        <div className="fixed bottom-16 right-4 z-50 max-w-xs animate-in slide-in-from-right-5 fade-in duration-300">
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800/50 shadow-lg">
            <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400 flex-shrink-0" />
            <span className="text-xs font-medium text-green-800 dark:text-green-300">
              All tests complete. Generate a report or review results.
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 px-4 py-3 flex-wrap">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {isPending && (
            <button onClick={onStart} disabled={isActioning} className="btn-primary text-sm">
              {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Start Automated Tests
            </button>
          )}

          {isPaused && (
            <button onClick={onResume} disabled={isActioning} className="btn-primary text-sm">
              {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Resume
            </button>
          )}

          {isRunning && (
            <button onClick={onPause} disabled={isActioning} className="btn-secondary text-sm">
              {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Pause className="w-4 h-4" />}
              Pause
            </button>
          )}

          {(isRunning || isPaused) && (
            <>
              <button type="button" onClick={onCancel} disabled={isActioning} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors disabled:opacity-50">
                <StopCircle className="w-4 h-4" />
                <span className="hidden sm:inline">Cancel</span>
              </button>
              <button type="button" onClick={onFlagCable} className="btn-secondary text-sm" title="Flag cable disconnect">
                <Unplug className="w-4 h-4" />
                <span className="hidden sm:inline">Flag Cable</span>
              </button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          {(isComplete || isAwaitingReview || isAwaitingManual) && (
            <button
              onClick={onGenerateReport}
              disabled={pendingManualCount > 0 || !canGenerateReport}
              className="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              title={pendingManualCount > 0 || !canGenerateReport ? (reportBlockedReason || 'Report is not ready yet') : 'Generate official report'}
            >
              <FileBarChart className="w-4 h-4" />
              Generate Report
            </button>
          )}

          {(isComplete || isAwaitingReview) && canSelfApprove && (
            <>
              <button onClick={onApprove} disabled={isActioning || pendingManualCount > 0} className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed">
                {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {isAwaitingReview ? 'Approve' : 'Approve All'}
              </button>
              {!isAwaitingReview && (
                <button onClick={onRequestReview} disabled={isActioning || pendingManualCount > 0} className="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed" title="Submit for peer review">
                  <Send className="w-4 h-4" />
                  <span className="hidden sm:inline">Request Review</span>
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}