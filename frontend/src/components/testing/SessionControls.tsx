import {
  Play, Pause, Unplug, FileBarChart, CheckCircle2,
  Send, Loader2, Square
} from 'lucide-react'

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
}: SessionControlsProps) {
  const isRunning = runStatus === 'running'
  const isPaused = runStatus === 'paused_manual' || runStatus === 'paused_cable'
  const isPending = runStatus === 'pending'
  const isComplete = runStatus === 'complete' || runStatus === 'completed'
  const isAwaitingReview = runStatus === 'awaiting_review'

  return (
    <div className="flex items-center gap-2 px-4 py-3 bg-white border-t border-zinc-200 flex-wrap">
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
        {(isComplete || isAwaitingReview) && (
          <button onClick={onGenerateReport} className="btn-secondary text-sm">
            <FileBarChart className="w-4 h-4" />
            Generate Report
          </button>
        )}

        {!isComplete && !isAwaitingReview && !isPending && canSelfApprove && (
          <>
            <button onClick={onApprove} disabled={isActioning} className="btn-primary text-sm">
              {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              Approve All
            </button>
            <button onClick={onRequestReview} disabled={isActioning} className="btn-secondary text-sm">
              <Send className="w-4 h-4" />
              <span className="hidden sm:inline">Request Review</span>
            </button>
          </>
        )}

        {isAwaitingReview && canSelfApprove && (
          <button onClick={onApprove} disabled={isActioning} className="btn-primary text-sm">
            {isActioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Approve
          </button>
        )}
      </div>
    </div>
  )
}
