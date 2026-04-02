import {
  Play, Pause, Unplug, FileBarChart, CheckCircle2,
  Send, Loader2, Activity
} from 'lucide-react'
import { motion } from 'framer-motion'

interface SessionControlsProps {
  runStatus: string
  canSelfApprove: boolean
  isOwner: boolean
  onStart: () => void
  onPause: () => void
  onResume: () => void
  onFlagCable: () => void
  onGenerateReport: () => void
  onApprove: () => void
  onRequestReview: () => void
  isActioning: boolean
  runningTestName?: string | null
  progressPct?: number
  completedCount?: number
  totalCount?: number
}

export default function SessionControls({
  runStatus,
  canSelfApprove,
  isOwner,
  onStart,
  onPause,
  onResume,
  onFlagCable,
  onGenerateReport,
  onApprove,
  onRequestReview,
  isActioning,
  runningTestName,
  progressPct = 0,
  completedCount = 0,
  totalCount = 0,
}: SessionControlsProps) {
  const isRunning = runStatus === 'running' || runStatus === 'selecting_interface' || runStatus === 'syncing'
  const isPaused = runStatus === 'paused_manual' || runStatus === 'paused_cable'
  const isPending = runStatus === 'pending'
  const isComplete = runStatus === 'completed'
  const isAwaitingReview = runStatus === 'awaiting_review'
  const isAwaitingManual = runStatus === 'awaiting_manual'

  return (
    <div className="bg-white dark:bg-dark-card border-t border-zinc-200 dark:border-slate-700/50">
      {/* Running progress banner */}
      {isRunning && (
        <div className="px-4 pt-2">
          <div className="flex items-center gap-2 mb-1.5">
            <Activity className="w-3.5 h-3.5 text-blue-500 animate-pulse flex-shrink-0" />
            <span className="text-xs font-medium text-blue-700 dark:text-blue-300 truncate">
              {runningTestName ? `Running: ${runningTestName}` : 'Running tests...'}
            </span>
            <span className="text-xs font-mono text-blue-500 ml-auto flex-shrink-0">
              {completedCount}/{totalCount}
            </span>
          </div>
          <div className="w-full h-1.5 bg-blue-100 dark:bg-blue-900/40 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-blue-500 to-brand-500 rounded-full"
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            />
          </div>
        </div>
      )}

      {/* Next step prompts */}
      {isAwaitingManual && (
        <div className="px-4 pt-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50">
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
            </span>
            <span className="text-xs font-medium text-amber-800 dark:text-amber-300">
              Automatic tests complete — manual tests need your input. Click each one in the sidebar.
            </span>
          </div>
        </div>
      )}

      {isComplete && (
        <div className="px-4 pt-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800/50">
            <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400 flex-shrink-0" />
            <span className="text-xs font-medium text-green-800 dark:text-green-300">
              All tests complete. Generate a report or review the results.
            </span>
          </div>
        </div>
      )}

      {/* Action buttons */}
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
            <button onClick={onFlagCable} className="btn-secondary text-sm" title="Flag cable disconnect">
              <Unplug className="w-4 h-4" />
              <span className="hidden sm:inline">Flag Cable</span>
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {(isComplete || isAwaitingReview || isAwaitingManual) && (
            <button onClick={onGenerateReport} className="btn-secondary text-sm">
              <FileBarChart className="w-4 h-4" />
              Generate Report
            </button>
          )}

          {(isComplete || isAwaitingReview) && canSelfApprove && (
            <>
              <button onClick={onApprove} disabled={isActioning} className="btn-primary text-sm">
                {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {isAwaitingReview ? 'Approve' : 'Approve All'}
              </button>
              {!isAwaitingReview && (
                <button onClick={onRequestReview} disabled={isActioning} className="btn-secondary text-sm" title="Submit for peer review">
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
