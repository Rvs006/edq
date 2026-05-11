import { useEffect, useState } from 'react'
import { CheckCircle2, XCircle, AlertTriangle, MinusCircle, Loader2, ArrowRight } from 'lucide-react'

interface ManualTestFormProps {
  testId: string
  testNumber: string
  testName: string
  currentVerdict: string | null
  currentNotes: string | null
  onSubmit: (verdict: string, notes: string) => Promise<void>
  isSubmitting: boolean
}

const verdictOptions = [
  { value: 'pass', label: 'PASS', icon: CheckCircle2, color: 'bg-green-500 hover:bg-green-600 text-white', activeRing: 'ring-green-500/30' },
  { value: 'fail', label: 'FAIL', icon: XCircle, color: 'bg-red-500 hover:bg-red-600 text-white', activeRing: 'ring-red-500/30' },
  { value: 'advisory', label: 'ADVISORY', icon: AlertTriangle, color: 'bg-amber-500 hover:bg-amber-600 text-white', activeRing: 'ring-amber-500/30' },
  { value: 'na', label: 'N/A', icon: MinusCircle, color: 'bg-zinc-400 hover:bg-zinc-500 text-white', activeRing: 'ring-zinc-400/30' },
]

function normalizeVerdict(verdict: string | null | undefined): string | null {
  if (!verdict) return null
  const normalized = verdict.toLowerCase()
  return normalized === 'n/a' ? 'na' : normalized
}

export default function ManualTestForm({
  testId,
  testNumber,
  testName,
  currentVerdict,
  currentNotes,
  onSubmit,
  isSubmitting,
}: ManualTestFormProps) {
  const [selectedVerdict, setSelectedVerdict] = useState<string | null>(
    currentVerdict && currentVerdict !== 'pending' ? normalizeVerdict(currentVerdict) : null
  )
  const [notes, setNotes] = useState(currentNotes || '')
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    setSelectedVerdict(
      currentVerdict && currentVerdict !== 'pending' ? normalizeVerdict(currentVerdict) : null
    )
  }, [currentVerdict])

  useEffect(() => {
    setNotes(currentNotes || '')
  }, [currentNotes])

  const handleSubmit = async () => {
    if (!selectedVerdict) return
    if (selectedVerdict !== 'pending' && !notes.trim()) return
    await onSubmit(selectedVerdict, notes)
    setSubmitted(true)
    setTimeout(() => setSubmitted(false), 2000)
  }

  const hasChanges =
    selectedVerdict !== (normalizeVerdict(currentVerdict) || null) ||
    notes !== (currentNotes || '')

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
          Select Verdict
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
          {verdictOptions.map((opt) => {
            const isActive = selectedVerdict === opt.value
            const Icon = opt.icon
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setSelectedVerdict(opt.value)}
                className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg font-semibold text-xs
                  transition-all duration-150
                  ${isActive ? `${opt.color} ring-2 ${opt.activeRing} shadow-md scale-[1.02]` : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'}
                `}
              >
                <Icon className="w-4 h-4" />
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <label htmlFor={`notes-${testId}`} className="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">
          Comments
        </label>
        <textarea
          id={`notes-${testId}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Observations, steps taken, or why this test does not apply..."
          className="input resize-y text-sm"
        />
        {!notes.trim() && selectedVerdict && selectedVerdict !== 'pending' && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Add engineer notes before saving this manual verdict.
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!selectedVerdict || isSubmitting || (selectedVerdict !== 'pending' && !notes.trim())}
          className="btn-primary text-sm"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : submitted ? (
            <>
              <CheckCircle2 className="w-4 h-4" />
              Saved
            </>
          ) : (
            <>
              Submit Result
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
        {hasChanges && !submitted && currentVerdict && currentVerdict !== 'pending' && (
          <span className="text-xs text-amber-600">Unsaved changes</span>
        )}
        {submitted && (
          <span className="text-xs text-green-600 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Auto-advancing to next test...
          </span>
        )}
      </div>
    </div>
  )
}
