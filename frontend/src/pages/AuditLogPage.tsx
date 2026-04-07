import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { auditApi } from '@/lib/api'
import type { AuditLogEntry } from '@/lib/types'
import { ListChecks, Loader2, Download } from 'lucide-react'
import toast from 'react-hot-toast'

const ACTION_COLORS: Record<string, string> = {
  create: 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  device_created: 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  device_updated: 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  test_run_started: 'bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800',
  test_run_completed: 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-950/40 dark:text-green-400 dark:border-green-800',
  test_result_updated: 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800',
  report_generated: 'bg-cyan-50 text-cyan-700 border border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-400 dark:border-cyan-800',
  user_login: 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700',
  user_created: 'bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-400 dark:border-indigo-800',
}

export default function AuditLogPage() {
  const [actionFilter, setActionFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)
  const pageSize = 50

  const { data, isLoading } = useQuery({
    queryKey: ['audit-logs', actionFilter, dateFrom, dateTo, page],
    queryFn: () => auditApi.list({
      action: actionFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      skip: page * pageSize,
      limit: pageSize,
    }).then(r => r.data),
  })

  const logs: AuditLogEntry[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  const handleExportCsv = async () => {
    try {
      const res = await auditApi.exportCsv({
        action: actionFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = 'audit_logs.csv'
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success('CSV exported')
    } catch {
      toast.error('Failed to export CSV')
    }
  }

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Audit Log</h1>
          <p className="section-subtitle">Track all system actions and compliance events</p>
        </div>
        <button type="button" onClick={handleExportCsv} className="btn-secondary text-xs">
          <Download className="w-3.5 h-3.5" /> Export CSV
        </button>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex gap-2 overflow-x-auto pb-1 flex-1">
          {['', 'device_created', 'test_run_started', 'test_run_completed', 'report_generated', 'user_login'].map(a => (
            <button
              type="button"
              key={a}
              onClick={() => { setActionFilter(a); setPage(0) }}
              aria-label={a ? `Filter by ${a.replace(/_/g, ' ')}` : 'Show all actions'}
              className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                actionFilter === a ? 'bg-brand-500 text-white' : 'bg-zinc-100 dark:bg-slate-800 text-zinc-600 dark:text-slate-400 hover:bg-zinc-200 dark:hover:bg-slate-700'
              }`}
            >
              {a ? a.replace(/_/g, ' ') : 'All'}
            </button>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          <input
            type="date"
            value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(0) }}
            aria-label="Filter from date"
            className="input text-xs py-1.5 w-36"
            placeholder="From"
          />
          <span className="text-zinc-400 text-xs">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(0) }}
            aria-label="Filter to date"
            className="input text-xs py-1.5 w-36"
            placeholder="To"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : logs.length > 0 ? (
        <>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Action</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">User</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Details</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                      <td className="py-3 px-4">
                        <span className={`badge text-[10px] ${ACTION_COLORS[log.action] || 'bg-zinc-100 text-zinc-600 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'}`}>
                          {log.action?.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 text-xs hidden sm:table-cell">
                        {log.user_name || (log.user_id ? log.user_id.slice(0, 8) : '\u2014')}
                      </td>
                      <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 text-xs max-w-xs truncate hidden md:table-cell">
                        {log.details ? (typeof log.details === 'string' ? log.details : JSON.stringify(log.details)) : '\u2014'}
                      </td>
                      <td className="py-3 px-4 text-zinc-500 text-xs whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-zinc-500">{total} total entries</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="btn-secondary text-xs py-1.5 px-3 disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="text-xs text-zinc-500 py-1.5">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="btn-secondary text-xs py-1.5 px-3 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="card p-12 text-center">
          <ListChecks className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-zinc-700 dark:text-slate-300 mb-1">No audit logs</h3>
          <p className="text-sm text-zinc-500">Actions will be logged here as you use the system</p>
        </div>
      )}
    </div>
  )
}
