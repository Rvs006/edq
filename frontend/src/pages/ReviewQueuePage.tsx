import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { testRunsApi } from '@/lib/api'
import type { TestRun } from '@/lib/types'
import { toLocalDateOnly } from '@/lib/testContracts'
import { Eye, Loader2, ClipboardCheck, ArrowUpDown } from 'lucide-react'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'

type SortField = 'created_at' | 'device_name'
type SortDir = 'asc' | 'desc'

export default function ReviewQueuePage() {
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: runs, isLoading } = useQuery({
    queryKey: ['review-queue'],
    queryFn: () => testRunsApi.list({ status: 'awaiting_review' }).then(r => r.data),
  })

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sortedRuns = [...(runs || [])].sort((a: TestRun, b: TestRun) => {
    let cmp = 0
    if (sortField === 'created_at') {
      cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    } else if (sortField === 'device_name') {
      cmp = (a.device_name || '').localeCompare(b.device_name || '')
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  return (
    <div className="page-container" data-tour="review-list">
      <div className="mb-5">
        <h1 className="section-title">Review Queue</h1>
        <p className="section-subtitle">Test runs awaiting reviewer sign-off</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : sortedRuns.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">
                    <button type="button" onClick={() => toggleSort('device_name')} className="flex items-center gap-1 hover:text-zinc-700 dark:hover:text-zinc-300">
                      Device <ArrowUpDown className="w-3 h-3" />
                    </button>
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Engineer</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Verdict</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">
                    <button type="button" onClick={() => toggleSort('created_at')} className="flex items-center gap-1 hover:text-zinc-700 dark:hover:text-zinc-300">
                      Date <ArrowUpDown className="w-3 h-3" />
                    </button>
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                {sortedRuns.map((run: TestRun) => (
                  <tr key={run.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                    <td className="py-3 px-4">
                      <p className="font-medium text-zinc-900 dark:text-slate-100">{run.device_name || `Run ${run.id.slice(0, 8)}`}</p>
                      <p className="text-xs text-zinc-500 font-mono">{run.device_ip || run.device_id?.slice(0, 8)}</p>
                    </td>
                    <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 text-xs hidden sm:table-cell">
                      {run.engineer_name || run.engineer_id.slice(0, 8)}
                    </td>
                    <td className="py-3 px-4"><StatusBadge status={run.status} /></td>
                    <td className="py-3 px-4">
                      {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden md:table-cell">
                      {toLocalDateOnly(run.created_at)}
                    </td>
                    <td className="py-3 px-4">
                      <Link
                        to={`/test-runs/${run.id}`}
                        className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-500 hover:text-brand-600"
                      >
                        <Eye className="w-3.5 h-3.5" /> Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <ClipboardCheck className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">No runs awaiting review</h3>
          <p className="text-sm text-zinc-500">Test runs submitted for review will appear here</p>
        </div>
      )}
    </div>
  )
}
