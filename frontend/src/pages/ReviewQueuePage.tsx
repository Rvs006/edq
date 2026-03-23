import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { testRunsApi } from '@/lib/api'
import { Eye, Loader2, ClipboardCheck } from 'lucide-react'
import VerdictBadge, { StatusBadge } from '@/components/common/VerdictBadge'

export default function ReviewQueuePage() {
  const { data: runs, isLoading } = useQuery({
    queryKey: ['review-queue'],
    queryFn: () => testRunsApi.list({ status: 'awaiting_review' }).then(r => r.data),
  })

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Review Queue</h1>
        <p className="section-subtitle">Test runs awaiting reviewer sign-off</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : runs && runs.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50/50">
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Device</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden sm:table-cell">Engineer</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Status</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Verdict</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden md:table-cell">Date</th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {runs.map((run: any) => (
                  <tr key={run.id} className="hover:bg-zinc-50 transition-colors">
                    <td className="py-3 px-4">
                      <p className="font-medium text-zinc-900">{run.device_name || `Run ${run.id.slice(0, 8)}`}</p>
                      <p className="text-xs text-zinc-500 font-mono">{run.device_ip || run.device_id?.slice(0, 8)}</p>
                    </td>
                    <td className="py-3 px-4 text-zinc-600 text-xs hidden sm:table-cell">
                      {run.user_name || run.user_id?.slice(0, 8) || '—'}
                    </td>
                    <td className="py-3 px-4"><StatusBadge status={run.status} /></td>
                    <td className="py-3 px-4">
                      {run.overall_verdict ? <VerdictBadge verdict={run.overall_verdict} /> : <span className="text-xs text-zinc-400">&mdash;</span>}
                    </td>
                    <td className="py-3 px-4 text-xs text-zinc-500 hidden md:table-cell">
                      {new Date(run.created_at).toLocaleDateString()}
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
          <h3 className="text-base font-semibold text-zinc-700 mb-1">No runs awaiting review</h3>
          <p className="text-sm text-zinc-500">Test runs submitted for review will appear here</p>
        </div>
      )}
    </div>
  )
}
