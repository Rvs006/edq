import { useState } from 'react'
import { ChevronDown, ChevronUp, Terminal, FileSearch, Pencil, ShieldAlert, Info } from 'lucide-react'
import LiveTerminal from './LiveTerminal'
import ManualTestForm from './ManualTestForm'
import VerdictBadge from '@/components/common/VerdictBadge'
import TestExplainer from '@/components/common/TestExplainer'

export interface TestResultDetail {
  id: string
  test_number: string
  test_name: string
  tier: 'automatic' | 'guided_manual' | 'auto_na'
  tool_used: string | null
  tool_command: string | null
  raw_stdout: string | null
  raw_stderr: string | null
  parsed_findings: any
  verdict: string | null
  auto_comment: string | null
  engineer_selection: string | null
  engineer_notes: string | null
  is_overridden: boolean
  override_reason: string | null
  overridden_by: string | null
  script_flag: string
  started_at: string | null
  completed_at: string | null
  duration_seconds?: number
  essential_pass?: boolean
  test_description?: string
  pass_criteria?: string
}

interface TestDetailProps {
  result: TestResultDetail
  liveOutput: string
  isRunning: boolean
  userRole: string
  userId: string
  onSubmitManual: (resultId: string, verdict: string, notes: string) => Promise<void>
  onOverride: (resultId: string, verdict: string, reason: string) => Promise<void>
  isSubmitting: boolean
}

export default function TestDetail({
  result,
  liveOutput,
  isRunning,
  userRole,
  userId,
  onSubmitManual,
  onOverride,
  isSubmitting,
}: TestDetailProps) {
  const [explainerOpen, setExplainerOpen] = useState(false)
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [overrideVerdict, setOverrideVerdict] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [notesValue, setNotesValue] = useState(result.engineer_notes || '')

  const canOverride = userRole === 'admin' || userRole === 'reviewer'
  const isManual = result.tier === 'guided_manual'
  const termOutput = liveOutput || result.raw_stdout || ''

  const tierLabel =
    result.tier === 'automatic' ? 'Automatic' : result.tier === 'guided_manual' ? 'Manual' : 'Auto N/A'
  const tierBg =
    result.tier === 'automatic'
      ? 'bg-blue-50 text-blue-700 border-blue-200'
      : result.tier === 'guided_manual'
        ? 'bg-amber-50 text-amber-700 border-amber-200'
        : 'bg-zinc-100 text-zinc-600 border-zinc-200'

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-5 pt-5 pb-4 border-b border-zinc-100 space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-mono font-bold text-zinc-500">
                {result.test_number}
              </span>
              <h2 className="text-base font-semibold text-zinc-900 truncate">
                {result.test_name}
              </h2>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {result.tool_used && (
                <span className="badge text-[10px] bg-violet-50 text-violet-700 border border-violet-200">
                  {result.tool_used}
                </span>
              )}
              <span className={`badge text-[10px] border ${tierBg}`}>{tierLabel}</span>
              {result.essential_pass && (
                <span className="badge text-[10px] bg-red-50 text-red-700 border border-red-200">
                  Essential
                </span>
              )}
              {result.script_flag === 'Yes' && (
                <span className="badge text-[10px] bg-zinc-100 text-zinc-500 border border-zinc-200">
                  Scripted
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
              <span className="badge text-[10px] bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
                Running...
              </span>
            ) : (
              <VerdictBadge verdict="pending" size="md" />
            )}
          </div>
        </div>

        <TestExplainer
          testNumber={result.test_number}
          testName={result.test_name}
          description={result.test_description}
          passCriteria={result.pass_criteria}
          toolUsed={result.tool_used}
        />
      </div>

      <div className="flex-1 px-5 py-4 space-y-5">
        {!isManual && termOutput && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Terminal className="w-4 h-4 text-zinc-400" />
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Terminal Output
              </h3>
              {result.tool_command && (
                <code className="text-[10px] font-mono text-zinc-400 bg-zinc-100 px-1.5 py-0.5 rounded ml-auto truncate max-w-[50%]">
                  {result.tool_command}
                </code>
              )}
            </div>
            <LiveTerminal output={termOutput} className="h-[240px]" />
          </div>
        )}

        {!isManual && result.parsed_findings && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <FileSearch className="w-4 h-4 text-zinc-400" />
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Parsed Findings
              </h3>
            </div>
            <div className="bg-zinc-50 rounded-lg border border-zinc-200 p-3">
              <FindingsDisplay findings={result.parsed_findings} />
            </div>
          </div>
        )}

        {!isManual && result.auto_comment && (
          <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-100">
            <p className="text-xs font-medium text-zinc-500 mb-1">Auto-Generated Comment</p>
            <p className="text-sm text-zinc-700">{result.auto_comment}</p>
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
            <ManualTestForm
              testId={result.id}
              testNumber={result.test_number}
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
                  onSubmitManual(result.id, result.verdict || 'pending', notesValue)
                }
              }}
            />
          </div>
        )}

        {canOverride && result.verdict && result.verdict !== 'pending' && (
          <div className="border-t border-zinc-100 pt-4">
            <button
              onClick={() => setOverrideOpen(!overrideOpen)}
              className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-700 transition-colors"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Override Verdict</span>
              {overrideOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {overrideOpen && (
              <div className="mt-3 p-3 bg-amber-50/50 rounded-lg border border-amber-200 space-y-3">
                <select
                  value={overrideVerdict}
                  onChange={(e) => setOverrideVerdict(e.target.value)}
                  className="input text-sm"
                >
                  <option value="">Select new verdict...</option>
                  <option value="pass">Pass</option>
                  <option value="fail">Fail</option>
                  <option value="advisory">Advisory</option>
                  <option value="n/a">N/A</option>
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
              <div className="mt-2 p-2.5 bg-amber-50 rounded-lg border border-amber-200">
                <p className="text-xs text-amber-800">
                  <span className="font-medium">Overridden:</span> {result.override_reason}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function FindingsDisplay({ findings }: { findings: any }) {
  if (!findings) return null

  if (Array.isArray(findings)) {
    return (
      <ul className="space-y-1.5">
        {findings.map((f, i) => (
          <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
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
            <dt className="font-medium text-zinc-600 min-w-0 flex-shrink-0">{key}:</dt>
            <dd className="text-zinc-700 min-w-0 break-words">
              {typeof value === 'string' ? value : JSON.stringify(value)}
            </dd>
          </div>
        ))}
      </dl>
    )
  }

  return <p className="text-sm text-zinc-700">{String(findings)}</p>
}
