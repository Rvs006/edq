import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { auditApi } from '@/lib/api'
import type { AuditLogEntry } from '@/lib/types'
import { ListChecks, Loader2, Download } from 'lucide-react'
import toast from 'react-hot-toast'

const ACTION_COLORS: Record<string, string> = {
  device_created: 'bg-blue-50 text-blue-700 border border-blue-200',
  device_updated: 'bg-blue-50 text-blue-700 border border-blue-200',
  test_run_started: 'bg-purple-50 text-purple-700 border border-purple-200',
  test_run_completed: 'bg-green-50 text-green-700 border border-green-200',
  test_result_updated: 'bg-amber-50 text-amber-700 border border-amber-200',
  report_generated: 'bg-cyan-50 text-cyan-700 border border-cyan-200',
  user_login: 'bg-zinc-100 text-zinc-700 border border-zinc-200',
  user_created: 'bg-indigo-50 text-indigo-700 border border-indigo-200',
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
        <button onClick={handleExportCsv} className="btn-secondary text-xs">
          <Download className="w-3.5 h-3.5" /> Export CSV
        </button>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex gap-2 overflow-x-auto pb-1 flex-1">
          {['', 'device_created', 'test_run_started', 'test_run_completed', 'report_generated', 'user_login'].map(a => (
            <button
              key={a}
              onClick={() => { setActionFilter(a); setPage(0) }}
              className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                actionFilter === a ? 'bg-brand-500 text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
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
            className="input text-xs py-1.5 w-36"
            placeholder="From"
          />
          <span className="text-zinc-400 text-xs">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(0) }}
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
                  <tr className="border-b border-zinc-200 bg-zinc-50/50">
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Action</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden sm:table-cell">User</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 hidden md:table-cell">Details</th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-zinc-50 transition-colors">
                      <td className="py-3 px-4">
                        <span className={`badge text-[10px] ${ACTION_COLORS[log.action] || 'bg-zinc-100 text-zinc-600 border border-zinc-200'}`}>
                          {log.action?.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-zinc-600 text-xs hidden sm:table-cell">
                        {log.user_name || (log.user_id ? log.user_id.slice(0, 8) : '\u2014')}
                      </td>
                      <td className="py-3 px-4 text-zinc-600 text-xs max-w-xs truncate hidden md:table-cell">
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
          <h3 className="text-base font-semibold text-zinc-700 mb-1">No audit logs</h3>
          <p className="text-sm text-zinc-500">Actions will be logged here as you use the system</p>
        </div>
      )}
    </div>
  )
}
