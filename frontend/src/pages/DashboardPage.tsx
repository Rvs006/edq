import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { devicesApi, testRunsApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import Callout from '@/components/common/Callout'
import {
  Monitor, Play, CheckCircle2, XCircle, AlertTriangle, Clock,
  ArrowRight, TrendingUp, Plus, FileText, Percent, Sparkles
} from 'lucide-react'
import { StatusBadge } from '@/components/common/VerdictBadge'
import VerdictBadge from '@/components/common/VerdictBadge'
import type { TestRun, TourState } from '@/lib/types'
import { toLocalDateOnly } from '@/lib/testContracts'
import { getDeviceMetaSummary, getPreferredDeviceName } from '@/lib/deviceLabels'

export default function DashboardPage({ tourState }: { tourState?: TourState }) {
  const { user } = useAuth()
  const { data: deviceStats, isError } = useQuery({
    queryKey: ['device-stats'],
    queryFn: () => devicesApi.stats().then(r => r.data),
  })
  const { data: runStats } = useQuery({
    queryKey: ['run-stats'],
    queryFn: () => testRunsApi.stats().then(r => r.data),
  })
  const { data: recentRuns } = useQuery({
    queryKey: ['recent-runs'],
    queryFn: () => testRunsApi.list({ limit: 8 }).then(r => r.data),
  })

  const passCount = runStats?.by_verdict?.pass || 0
  const totalCompleted = (runStats?.by_verdict?.pass || 0) + (runStats?.by_verdict?.fail || 0) + (runStats?.by_verdict?.advisory || 0)
  const passRate = totalCompleted > 0 ? Math.round((passCount / totalCompleted) * 100) : 0
  const activeRunCount = [
    'pending',
    'selecting_interface',
    'syncing',
    'running',
    'paused_manual',
    'paused_cable',
    'awaiting_manual',
    'awaiting_review',
  ].reduce((sum, key) => sum + Number(runStats?.by_status?.[key] || 0), 0)

  const stats = [
    {
      label: 'Total Devices',
      value: deviceStats?.total || 0,
      icon: Monitor,
      iconColor: 'text-blue-600 dark:text-blue-400',
      iconBg: 'bg-blue-50 dark:bg-blue-950/50',
    },
    {
      label: 'Active Test Runs',
      value: activeRunCount,
      icon: Play,
      iconColor: 'text-purple-600 dark:text-purple-400',
      iconBg: 'bg-purple-50 dark:bg-purple-950/50',
    },
    {
      label: 'Completed This Week',
      value: runStats?.completed_this_week || runStats?.by_status?.completed || 0,
      icon: CheckCircle2,
      iconColor: 'text-green-600 dark:text-green-400',
      iconBg: 'bg-green-50 dark:bg-green-950/50',
    },
    {
      label: 'Pass Rate',
      value: `${passRate}%`,
      icon: Percent,
      iconColor: 'text-amber-600 dark:text-amber-400',
      iconBg: 'bg-amber-50 dark:bg-amber-950/50',
    },
  ]

  return (
    <div className="page-container">
      {tourState?.showWelcomeBanner && (
        <div className="bg-gradient-to-r from-brand-500 to-blue-600 text-white rounded-xl p-5 sm:p-6 mb-6 shadow-lg shadow-brand-500/10">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center shrink-0 mt-0.5">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <h2 className="text-base font-bold mb-1">Welcome to EDQ!</h2>
              <p className="text-sm text-blue-100 mb-4 leading-relaxed">
                Take a 2-minute tour to learn how EDQ helps you qualify devices faster.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={tourState.startTour}
                  className="inline-flex items-center gap-1.5 bg-white text-brand-600 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-blue-50 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Start Tour
                </button>
                <button
                  onClick={tourState.dismissTour}
                  className="text-white/70 hover:text-white text-sm font-medium transition-colors"
                >
                  Skip for now
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-slate-100">
          Welcome back, {user?.full_name || user?.username}
        </h1>
        <p className="text-sm text-zinc-500 dark:text-slate-400 mt-0.5">
          Device qualification overview
        </p>
      </div>

      {isError && (
        <div className="mb-6">
          <Callout variant="error">Failed to load dashboard data. Please try again.</Callout>
        </div>
      )}

      <div data-tour="kpi-grid" className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        {stats.map((stat) => (
          <div key={stat.label} className="card p-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg ${stat.iconBg} flex items-center justify-center`}>
                <stat.icon className={`w-5 h-5 ${stat.iconColor}`} />
              </div>
              <div>
                  <p className="text-2xl font-bold text-zinc-900 dark:text-slate-100">{stat.value}</p>
                  <p className="text-xs text-zinc-500 dark:text-slate-400">{stat.label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between p-4 border-b border-zinc-100 dark:border-slate-700/50">
            <h2 className="font-semibold text-zinc-900 dark:text-slate-100">Recent Test Sessions</h2>
            <Link to="/test-runs" className="text-sm text-brand-500 hover:text-brand-600 flex items-center gap-1">
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <div className="overflow-x-auto">
            {recentRuns && recentRuns.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-slate-700/50">
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Device</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">IP</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Status</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Verdict</th>
                    <th className="text-left py-2.5 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-slate-700/50">
                  {recentRuns.map((run: TestRun) => (
                    <tr key={run.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                      <td className="py-2.5 px-4">
                        <Link to={`/test-runs/${run.id}`} className="font-medium text-zinc-900 dark:text-slate-100 hover:text-brand-500">
                          {getPreferredDeviceName(run)}
                        </Link>
                        {getDeviceMetaSummary(run, { includeMac: true }) && (
                          <p className="text-[11px] text-zinc-500 dark:text-slate-400 mt-0.5">
                            {getDeviceMetaSummary(run, { includeMac: true })}
                          </p>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-zinc-500 font-mono text-xs hidden sm:table-cell">
                        {run.device_ip || run.device_id?.slice(0, 8)}
                      </td>
                      <td className="py-2.5 px-4">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="py-2.5 px-4">
                        {run.overall_verdict ? (
                          <VerdictBadge verdict={run.overall_verdict} />
                        ) : (
                          <span className="text-xs text-zinc-400">&mdash;</span>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-zinc-500 text-xs hidden md:table-cell">
                        {toLocalDateOnly(run.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-8 text-center">
                <Play className="w-8 h-8 text-zinc-300 mx-auto mb-2" />
                <p className="text-sm text-zinc-500">No test runs yet</p>
                <Link to="/devices" className="text-sm text-brand-500 hover:text-brand-600 mt-1 inline-block">
                  Start by adding a device
                </Link>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4" data-tour="quick-actions">
          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Quick Actions</h3>
            <div className="space-y-2">
              <Link to="/test-runs" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center">
                  <Plus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                </div>
                <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">New Test Run</span>
              </Link>
              <Link to="/devices" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-green-50 dark:bg-green-950 flex items-center justify-center">
                  <Monitor className="w-4 h-4 text-green-600 dark:text-green-400" />
                </div>
                <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">Add Device</span>
              </Link>
              <Link to="/reports" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-purple-50 dark:bg-purple-950 flex items-center justify-center">
                  <FileText className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                </div>
                <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">Generate Report</span>
              </Link>
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Device Categories</h3>
            {deviceStats?.by_category && Object.keys(deviceStats.by_category).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(deviceStats.by_category).map(([cat, count]) => (
                  <div key={cat} className="flex items-center justify-between py-1.5">
                    <span className="text-sm text-zinc-600 dark:text-slate-400 capitalize">{cat.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-semibold text-zinc-900 dark:text-slate-100">{String(count)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-400">No devices categorized yet</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
