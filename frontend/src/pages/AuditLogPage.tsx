import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { auditApi } from '@/lib/api'
import { ListChecks, Loader2, Filter, Shield, ChevronDown, ChevronUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const ACTION_COLORS: Record<string, string> = {
  device_created: 'bg-blue-100 text-blue-700',
  device_updated: 'bg-blue-100 text-blue-700',
  test_run_started: 'bg-purple-100 text-purple-700',
  test_run_completed: 'bg-emerald-100 text-emerald-700',
  test_result_updated: 'bg-amber-100 text-amber-700',
  report_generated: 'bg-teal-100 text-teal-700',
  user_login: 'bg-slate-100 text-slate-700',
  user_created: 'bg-indigo-100 text-indigo-700',
}

export default function AuditLogPage() {
  const [actionFilter, setActionFilter] = useState('')
  const [showCompliance, setShowCompliance] = useState(false)

  const { data: logs, isLoading } = useQuery({
    queryKey: ['audit-logs', actionFilter],
    queryFn: () => auditApi.list({ action: actionFilter || undefined, limit: 100 }).then(r => r.data),
  })

  const { data: compliance } = useQuery({
    queryKey: ['compliance-summary'],
    queryFn: () => auditApi.complianceSummary().then(r => r.data),
  })

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="section-title">Audit Log</h1>
          <p className="section-subtitle">Track all system actions and compliance events</p>
        </div>
        <button onClick={() => setShowCompliance(!showCompliance)} className="btn-secondary text-sm">
          <Shield className="w-4 h-4" /> Compliance Summary
        </button>
      </div>

      {/* Compliance Summary */}
      <AnimatePresence>
        {showCompliance && compliance && (
          <motion.div
            initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden mb-5"
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {Object.entries(compliance).map(([framework, data]: [string, any]) => (
                <div key={framework} className="card p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="w-5 h-5 text-brand-500" />
                    <h3 className="font-semibold text-slate-900">{framework}</h3>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Controls Tested</span>
                      <span className="font-semibold text-slate-900">{data.tested || 0}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Passed</span>
                      <span className="font-semibold text-emerald-600">{data.passed || 0}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Failed</span>
                      <span className="font-semibold text-red-600">{data.failed || 0}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filter */}
      <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
        {['', 'device_created', 'test_run_started', 'test_run_completed', 'report_generated', 'user_login'].map(a => (
          <button
            key={a}
            onClick={() => setActionFilter(a)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              actionFilter === a ? 'bg-brand-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {a ? a.replace(/_/g, ' ') : 'All'}
          </button>
        ))}
      </div>

      {/* Log entries */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : logs && logs.length > 0 ? (
        <div className="card divide-y divide-slate-100">
          {logs.map((log: any) => (
            <div key={log.id} className="flex items-start gap-3 px-4 py-3">
              <div className="w-2 h-2 rounded-full bg-brand-400 mt-2 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`badge text-[10px] ${ACTION_COLORS[log.action] || 'bg-slate-100 text-slate-600'}`}>
                    {log.action?.replace(/_/g, ' ')}
                  </span>
                  {log.user_id && (
                    <span className="text-xs text-slate-500">by {log.user_id.slice(0, 8)}</span>
                  )}
                </div>
                {log.details && (
                  <p className="text-sm text-slate-700 mt-0.5">{typeof log.details === 'string' ? log.details : JSON.stringify(log.details)}</p>
                )}
                {log.compliance_tags && log.compliance_tags.length > 0 && (
                  <div className="flex gap-1 mt-1">
                    {log.compliance_tags.map((tag: string, i: number) => (
                      <span key={i} className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{tag}</span>
                    ))}
                  </div>
                )}
              </div>
              <span className="text-xs text-slate-400 whitespace-nowrap flex-shrink-0">
                {new Date(log.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <ListChecks className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-700 mb-1">No audit logs</h3>
          <p className="text-sm text-slate-500">Actions will be logged here as you use the system</p>
        </div>
      )}
    </div>
  )
}
