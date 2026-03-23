import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { testRunsApi, testResultsApi, synopsisApi, reportsApi } from '@/lib/api'
import {
  ArrowLeft, CheckCircle2, XCircle, AlertTriangle,
  Download, FileText, Sparkles, Loader2, ChevronDown, ChevronUp
} from 'lucide-react'
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import toast from 'react-hot-toast'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'

export default function TestRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [expandedResult, setExpandedResult] = useState<string | null>(null)
  const [synopsisLoading, setSynopsisLoading] = useState(false)
  const queryClient = useQueryClient()

  const { data: run, isLoading } = useQuery({
    queryKey: ['test-run', id],
    queryFn: () => testRunsApi.get(id!).then(r => r.data),
    enabled: !!id,
    refetchInterval: (data: any) => data?.status === 'running' ? 3000 : false,
  })

  const { data: results } = useQuery({
    queryKey: ['test-results', id],
    queryFn: () => testResultsApi.list({ test_run_id: id }).then(r => r.data),
    enabled: !!id,
  })

  const generateSynopsis = async () => {
    setSynopsisLoading(true)
    try {
      await synopsisApi.generate({ test_run_id: id })
      queryClient.invalidateQueries({ queryKey: ['test-run', id] })
      toast.success('AI synopsis generated')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Synopsis generation failed')
    } finally {
      setSynopsisLoading(false)
    }
  }

  const generateReport = async (type: 'excel' | 'word') => {
    try {
      await reportsApi.generate({ test_run_id: id, report_type: type, include_synopsis: !!run?.synopsis })
      toast.success(`${type.toUpperCase()} report generated`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Report generation failed')
    }
  }

  if (isLoading) {
    return (
      <div className="page-container flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="page-container text-center py-20">
        <p className="text-zinc-500">Test run not found</p>
        <Link to="/test-runs" className="text-brand-500 text-sm mt-2 inline-block">Back to test runs</Link>
      </div>
    )
  }

  const passRate = run.total_tests > 0 ? Math.round((run.passed_tests / run.total_tests) * 100) : 0

  return (
    <div className="page-container">
      <Link to="/test-runs" className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to Test Runs
      </Link>

      <div className="card p-5 mb-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-xl font-bold text-zinc-900">Test Run {run.id.slice(0, 8)}</h1>
              <StatusBadge status={run.status} />
            </div>
            <p className="text-sm text-zinc-500">
              Device: {run.device_name || run.device_id?.slice(0, 8)} · Started: {run.started_at ? new Date(run.started_at).toLocaleString() : 'Not started'}
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button onClick={generateSynopsis} disabled={synopsisLoading} className="btn-secondary text-sm">
              {synopsisLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              AI Synopsis
            </button>
            <button onClick={() => generateReport('excel')} className="btn-secondary text-sm">
              <Download className="w-4 h-4" /> Excel
            </button>
            <button onClick={() => generateReport('word')} className="btn-secondary text-sm">
              <FileText className="w-4 h-4" /> Word
            </button>
          </div>
        </div>

        {run.status === 'running' && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm mb-1.5">
              <span className="text-zinc-500">Progress</span>
              <span className="text-zinc-700 font-semibold">{Math.round(run.progress_pct || 0)}%</span>
            </div>
            <div className="w-full h-2 bg-zinc-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-500 rounded-full transition-all duration-500"
                style={{ width: `${run.progress_pct || 0}%` }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
        {[
          { label: 'Total', value: run.total_tests, color: 'text-zinc-900' },
          { label: 'Passed', value: run.passed_tests, color: 'text-green-600' },
          { label: 'Failed', value: run.failed_tests, color: 'text-red-600' },
          { label: 'Advisory', value: run.advisory_tests, color: 'text-amber-600' },
          { label: 'N/A', value: run.na_tests, color: 'text-zinc-500' },
        ].map(s => (
          <div key={s.label} className="card p-3 text-center">
            <p className={`text-xl font-bold ${s.color}`}>{s.value ?? 0}</p>
            <p className="text-xs text-zinc-500">{s.label}</p>
          </div>
        ))}
      </div>

      {run.overall_verdict && (
        <div className={`card p-4 mb-5 border-l-4 ${
          run.overall_verdict === 'pass' ? 'border-l-green-500 bg-green-50' :
          run.overall_verdict === 'fail' ? 'border-l-red-500 bg-red-50' :
          'border-l-amber-500 bg-amber-50'
        }`}>
          <div className="flex items-center gap-3">
            {run.overall_verdict === 'pass' ? <CheckCircle2 className="w-6 h-6 text-green-600" /> :
             run.overall_verdict === 'fail' ? <XCircle className="w-6 h-6 text-red-600" /> :
             <AlertTriangle className="w-6 h-6 text-amber-600" />}
            <div>
              <p className="font-semibold text-zinc-900">
                Overall Verdict: <span className="uppercase">{run.overall_verdict}</span>
              </p>
              <p className="text-sm text-zinc-600">
                Pass rate: {passRate}% ({run.passed_tests}/{run.total_tests})
              </p>
            </div>
          </div>
        </div>
      )}

      {run.synopsis && (
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-purple-500" />
            <h2 className="font-semibold text-zinc-900">Synopsis</h2>
            <span className={`badge text-[10px] ${
              run.synopsis_status === 'human_approved' ? 'badge-pass' : 'badge-pending'
            }`}>
              {run.synopsis_status === 'human_approved' ? 'Approved' : 'AI Draft'}
            </span>
          </div>
          <p className="text-sm text-zinc-700 leading-relaxed whitespace-pre-wrap">
            {run.synopsis.replace('[AI-DRAFTED] ', '')}
          </p>
        </div>
      )}

      <div className="card">
        <div className="p-4 border-b border-zinc-100">
          <h2 className="font-semibold text-zinc-900">Test Results</h2>
        </div>
        <div className="divide-y divide-zinc-100">
          {results?.map((result: any) => (
            <div key={result.id}>
              <button
                onClick={() => setExpandedResult(expandedResult === result.id ? null : result.id)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 transition-colors text-left"
              >
                <VerdictDot verdict={result.verdict} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-zinc-400">{result.test_id || result.test_number}</span>
                    <span className="text-sm font-medium text-zinc-900">{result.test_name}</span>
                    {result.tier && (
                      <span className="badge text-[9px] bg-zinc-100 text-zinc-500 capitalize">{result.tier.replace(/_/g, ' ')}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    {result.tool && <span className="text-xs text-zinc-400">{result.tool}</span>}
                  </div>
                </div>
                <VerdictBadge verdict={result.verdict || 'pending'} />
                {expandedResult === result.id ? (
                  <ChevronUp className="w-4 h-4 text-zinc-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-zinc-400" />
                )}
              </button>

              <AnimatePresence>
                {expandedResult === result.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 pl-12 space-y-2">
                      {(result.comment || result.auto_comment || result.engineer_notes) && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 mb-0.5">Comment</p>
                          <p className="text-sm text-zinc-700">{result.comment_override || result.auto_comment || result.comment || result.engineer_notes}</p>
                        </div>
                      )}
                      {result.findings && result.findings.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 mb-1">Findings</p>
                          <ul className="space-y-1">
                            {result.findings.map((f: any, i: number) => (
                              <li key={i} className="text-sm text-zinc-700 flex items-start gap-1.5">
                                <span className="text-zinc-400 mt-0.5">&bull;</span>
                                {typeof f === 'string' ? f : JSON.stringify(f)}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.raw_stdout && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 mb-1">Raw Output</p>
                          <pre className="text-xs font-mono bg-zinc-50 border border-zinc-200 rounded p-3 overflow-x-auto max-h-48 text-zinc-700">
                            {result.raw_stdout}
                          </pre>
                        </div>
                      )}
                      {result.duration_seconds && (
                        <p className="text-xs text-zinc-400">Duration: {result.duration_seconds.toFixed(1)}s</p>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
          {(!results || results.length === 0) && (
            <div className="p-8 text-center text-sm text-zinc-500">No test results yet</div>
          )}
        </div>
      </div>
    </div>
  )
}

function VerdictDot({ verdict }: { verdict: string }) {
  const colors: Record<string, string> = {
    pass: 'bg-green-500', fail: 'bg-red-500', advisory: 'bg-amber-500',
    na: 'bg-zinc-400', 'n/a': 'bg-zinc-400', pending: 'bg-blue-400', info: 'bg-cyan-500',
  }
  return <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${colors[verdict?.toLowerCase()] || colors.pending}`} />
}
