import { Suspense, lazy, useState } from 'react'
import { ChevronDown, ChevronUp, Terminal, FileSearch, Pencil, ShieldAlert } from 'lucide-react'
import ManualTestForm from './ManualTestForm'
import VerdictBadge from '@/components/common/VerdictBadge'
import TestExplainer from '@/components/common/TestExplainer'

const LiveTerminal = lazy(() => import('./LiveTerminal'))

export interface TestResultDetail {
  id: string
  test_id: string
  test_name: string
  tier: 'automatic' | 'guided_manual' | 'auto_na'
  tool: string | null
  raw_output: string | null
  parsed_data: Record<string, unknown> | unknown[] | null
  findings: Record<string, unknown> | unknown[] | null
  verdict: string | null
  comment: string | null
  engineer_notes: string | null
  is_overridden: boolean
  override_reason: string | null
  override_verdict: string | null
  overridden_by_username: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds?: number
  is_essential?: boolean
  test_description?: string
  pass_criteria?: string
}

interface TestDetailProps {
  result: TestResultDetail
  liveOutput: string
  isRunning: boolean
  userRole: string
  onSubmitManual: (resultId: string, verdict: string, notes: string) => Promise<void>
  onOverride: (resultId: string, verdict: string, reason: string) => Promise<void>
  onSaveNotes?: (resultId: string, notes: string) => Promise<void>
  isSubmitting: boolean
}

export default function TestDetail({
  result,
  liveOutput,
  isRunning,
  userRole,
  onSubmitManual,
  onOverride,
  onSaveNotes,
  isSubmitting,
}: TestDetailProps) {
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [overrideVerdict, setOverrideVerdict] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [notesValue, setNotesValue] = useState(result.engineer_notes || '')

  const canOverride = userRole === 'admin' || userRole === 'reviewer'
  const isManual = result.tier === 'guided_manual'
  const termOutput = liveOutput || result.raw_output || ''
  const structuredOutput = result.findings || result.parsed_data

  const tierLabel =
    result.tier === 'automatic' ? 'Automatic' : result.tier === 'guided_manual' ? 'Manual' : 'Auto N/A'
  const tierBg =
    result.tier === 'automatic'
      ? 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-800'
      : result.tier === 'guided_manual'
        ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800'
        : 'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700/50'

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-5 pt-5 pb-4 border-b border-zinc-100 dark:border-slate-700/50 space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-mono font-bold text-zinc-500">
                {result.test_id}
              </span>
              <h2 className="text-base font-semibold text-zinc-900 dark:text-slate-100 truncate">
                {result.test_name}
              </h2>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {result.tool && (
                <span className="badge text-[10px] bg-violet-50 text-violet-700 border border-violet-200 dark:bg-violet-950/30 dark:text-violet-300 dark:border-violet-800">
                  {result.tool}
                </span>
              )}
              <span className={`badge text-[10px] border ${tierBg}`}>{tierLabel}</span>
              {result.is_essential && (
                <span className="badge text-[10px] bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-800">
                  Essential
                </span>
              )}
              {result.duration_seconds != null && (
                <span className="text-xs text-zinc-400">
                  {result.duration_seconds.toFixed(1)}s
                </span>
              )}
            </div>
          </div>
          <div className="flex-shrink-0">
            {result.verdict && result.verdict !== 'pending' ? (
              <VerdictBadge verdict={result.verdict} size="md" showIcon />
            ) : isRunning ? (
              <span className="badge text-[10px] bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-800 animate-pulse">
                Running...
              </span>
            ) : (
              <VerdictBadge verdict="pending" size="md" />
            )}
          </div>
        </div>

        <TestExplainer
          testNumber={result.test_id}
          testName={result.test_name}
          description={result.test_description}
          passCriteria={result.pass_criteria}
          toolUsed={result.tool}
          tier={result.tier}
        />
      </div>

      <div className="flex-1 px-5 py-4 space-y-5">
        <div className="p-3 rounded-lg border border-zinc-200 dark:border-slate-700/50 bg-zinc-50 dark:bg-slate-900/40">
          <p className="text-xs font-semibold text-zinc-700 dark:text-slate-200">How to review this test</p>
          <ul className="mt-2 space-y-1 text-xs text-zinc-500 dark:text-slate-400 list-disc pl-4">
            {isManual ? (
              <>
                <li>Read the explainer first so you know what evidence the test is asking for.</li>
                <li>Perform the action on the physical device or its web UI.</li>
                <li>Use notes to record what screen, setting, or behaviour you observed.</li>
              </>
            ) : (
              <>
                <li>Check the terminal output for what the tool actually tested.</li>
                <li>Use parsed findings for the key result, not just the raw text.</li>
                <li>If a fail looks unexpected, add notes so the reviewer understands why.</li>
              </>
            )}
          </ul>
        </div>

        {!isManual && termOutput && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Terminal className="w-4 h-4 text-zinc-400" />
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Terminal Output
              </h3>
            </div>
            <Suspense
              fallback={
                <div className="h-[240px] rounded-lg border border-zinc-700/50 bg-zinc-950/80 flex items-center justify-center text-xs text-zinc-400">
                  Loading terminal...
                </div>
              }
            >
              <LiveTerminal output={termOutput} className="h-[240px]" />
            </Suspense>
          </div>
        )}

        {!isManual && structuredOutput && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <FileSearch className="w-4 h-4 text-zinc-400" />
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Parsed Findings
              </h3>
            </div>
            <div className="bg-zinc-50 dark:bg-slate-900/40 rounded-lg border border-zinc-200 dark:border-slate-700/50 p-3">
              <FindingsDisplay findings={structuredOutput} />
            </div>
          </div>
        )}

        {!isManual && result.comment && (
          <div className="p-3 bg-zinc-50 dark:bg-slate-900/40 rounded-lg border border-zinc-100 dark:border-slate-700/50">
            <p className="text-xs font-medium text-zinc-500 mb-1">Comment</p>
            <p className="text-sm text-zinc-700 dark:text-slate-300">{result.comment}</p>
          </div>
        )}

        {isManual && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Pencil className="w-4 h-4 text-amber-500" />
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Manual Assessment
              </h3>
            </div>
            <div className="mb-3 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              Pick the verdict that best matches what you observed. Use <strong>Advisory</strong> when it works but still needs attention, and <strong>N/A</strong> only when the test genuinely does not apply to this device.
            </div>
            <ManualTestForm
              testId={result.id}
              testNumber={result.test_id}
              testName={result.test_name}
              currentVerdict={result.verdict}
              currentNotes={result.engineer_notes}
              onSubmit={(verdict, notes) => onSubmitManual(result.id, verdict, notes)}
              isSubmitting={isSubmitting}
            />
          </div>
        )}

        {!isManual && (
          <div>
            <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">
              Engineer Notes
            </label>
            <textarea
              value={notesValue}
              onChange={(e) => setNotesValue(e.target.value)}
              rows={2}
              placeholder="Add any observations or context..."
              className="input resize-y text-sm"
              onBlur={() => {
                if (notesValue !== (result.engineer_notes || '')) {
                  if (onSaveNotes) {
                    onSaveNotes(result.id, notesValue)
                  } else {
                    onSubmitManual(result.id, result.verdict || 'pending', notesValue)
                  }
                }
              }}
            />
          </div>
        )}

        {canOverride && result.verdict && result.verdict !== 'pending' && (
          <div className="border-t border-zinc-100 dark:border-slate-700/50 pt-4">
            <button
              onClick={() => setOverrideOpen(!overrideOpen)}
              className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-slate-400 hover:text-zinc-700 dark:hover:text-slate-200 transition-colors"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Override Verdict</span>
              {overrideOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {overrideOpen && (
              <div className="mt-3 p-3 bg-amber-50/50 dark:bg-amber-950/20 rounded-lg border border-amber-200 dark:border-amber-800 space-y-3">
                <select
                  value={overrideVerdict}
                  onChange={(e) => setOverrideVerdict(e.target.value)}
                  className="input text-sm"
                >
                  <option value="">Select new verdict...</option>
                  <option value="pass">Pass</option>
                  <option value="fail">Fail</option>
                  <option value="advisory">Advisory</option>
                  <option value="na">N/A</option>
                  <option value="info">Info</option>
                </select>
                <textarea
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  rows={2}
                  placeholder="Justification for override (required)..."
                  className="input resize-y text-sm"
                />
                <button
                  onClick={() => {
                    if (overrideVerdict && overrideReason.trim()) {
                      onOverride(result.id, overrideVerdict, overrideReason)
                      setOverrideOpen(false)
                      setOverrideVerdict('')
                      setOverrideReason('')
                    }
                  }}
                  disabled={!overrideVerdict || !overrideReason.trim()}
                  className="btn-secondary text-sm"
                >
                  Apply Override
                </button>
              </div>
            )}

            {result.is_overridden && (
              <div className="mt-2 p-2.5 bg-amber-50 dark:bg-amber-950/20 rounded-lg border border-amber-200 dark:border-amber-800">
                <p className="text-xs text-amber-800 dark:text-amber-200">
                  <span className="font-medium">Overridden:</span> {result.override_reason}
                  {result.overridden_by_username ? ` by ${result.overridden_by_username}` : ''}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function FindingsDisplay({ findings }: { findings: Record<string, unknown> | unknown[] | null }) {
  if (!findings) return null

  if (Array.isArray(findings)) {
    return (
      <ul className="space-y-1.5">
        {findings.map((f, i) => (
          <li key={i} className="text-sm text-zinc-700 dark:text-slate-300 flex items-start gap-2">
            <span className="text-zinc-400 mt-0.5 flex-shrink-0">&bull;</span>
            <span>{typeof f === 'string' ? f : JSON.stringify(f)}</span>
          </li>
        ))}
      </ul>
    )
  }

  if (typeof findings === 'object') {
    return (
      <dl className="space-y-1.5">
        {Object.entries(findings).map(([key, value]) => (
          <div key={key} className="flex items-start gap-2 text-sm">
            <dt className="font-medium text-zinc-600 dark:text-slate-400 min-w-0 flex-shrink-0">{key}:</dt>
            <dd className="text-zinc-700 dark:text-slate-300 min-w-0 break-words">
              {typeof value === 'string' ? value : JSON.stringify(value)}
            </dd>
          </div>
        ))}
      </dl>
    )
  }

  return <p className="text-sm text-zinc-700 dark:text-slate-300">{String(findings)}</p>
}
