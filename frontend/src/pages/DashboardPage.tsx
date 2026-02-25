import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { devicesApi, testRunsApi, agentsApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import {
  Monitor, Play, CheckCircle2, XCircle, AlertTriangle, Wifi,
  ArrowRight, TrendingUp, Clock, Shield, Activity
} from 'lucide-react'
import { motion } from 'framer-motion'

export default function DashboardPage() {
  const { user } = useAuth()
  const { data: deviceStats } = useQuery({ queryKey: ['device-stats'], queryFn: () => devicesApi.stats().then(r => r.data) })
  const { data: runStats } = useQuery({ queryKey: ['run-stats'], queryFn: () => testRunsApi.stats().then(r => r.data) })
  const { data: recentRuns } = useQuery({ queryKey: ['recent-runs'], queryFn: () => testRunsApi.list({ limit: 5 }).then(r => r.data) })
  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: () => agentsApi.list().then(r => r.data) })

  const stats = [
    {
      label: 'Total Devices',
      value: deviceStats?.total || 0,
      icon: Monitor,
      color: 'bg-blue-50 text-blue-600',
      iconBg: 'bg-blue-100',
      href: '/devices',
    },
    {
      label: 'Test Runs',
      value: runStats?.total || 0,
      icon: Play,
      color: 'bg-purple-50 text-purple-600',
      iconBg: 'bg-purple-100',
      href: '/test-runs',
    },
    {
      label: 'Passed',
      value: runStats?.by_verdict?.pass || 0,
      icon: CheckCircle2,
      color: 'bg-emerald-50 text-emerald-600',
      iconBg: 'bg-emerald-100',
      href: '/test-runs',
    },
    {
      label: 'Active Agents',
      value: agents?.length || 0,
      icon: Wifi,
      color: 'bg-amber-50 text-amber-600',
      iconBg: 'bg-amber-100',
      href: '/agents',
    },
  ]

  return (
    <div className="page-container">
      {/* Welcome header */}
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900">
          Welcome back, {user?.full_name || user?.username}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Here's an overview of your device qualification activity.
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <Link to={stat.href} className="card-hover block p-4">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg ${stat.iconBg} flex items-center justify-center`}>
                  <stat.icon className={`w-5 h-5 ${stat.color.split(' ')[1]}`} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900">{stat.value}</p>
                  <p className="text-xs text-slate-500">{stat.label}</p>
                </div>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        {/* Recent Test Runs */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between p-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Recent Test Runs</h2>
            <Link to="/test-runs" className="text-sm text-brand-500 hover:text-brand-600 flex items-center gap-1">
              View all <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <div className="divide-y divide-slate-100">
            {recentRuns && recentRuns.length > 0 ? (
              recentRuns.map((run: any) => (
                <Link
                  key={run.id}
                  to={`/test-runs/${run.id}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors"
                >
                  <VerdictIcon verdict={run.overall_verdict} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">
                      Run {run.id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-slate-500">
                      {run.passed_tests}/{run.total_tests} passed
                    </p>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={run.status} />
                    <p className="text-xs text-slate-400 mt-1">
                      {new Date(run.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </Link>
              ))
            ) : (
              <div className="p-8 text-center">
                <Play className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-500">No test runs yet</p>
                <Link to="/devices" className="text-sm text-brand-500 hover:text-brand-600 mt-1 inline-block">
                  Start by adding a device
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions & Device Categories */}
        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Quick Actions</h3>
            <div className="space-y-2">
              <Link to="/devices" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-50 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
                  <Monitor className="w-4 h-4 text-blue-600" />
                </div>
                <span className="text-sm font-medium text-slate-700">Add New Device</span>
              </Link>
              <Link to="/test-runs" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-50 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center">
                  <Play className="w-4 h-4 text-purple-600" />
                </div>
                <span className="text-sm font-medium text-slate-700">Start Test Run</span>
              </Link>
              <Link to="/reports" className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-50 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 text-emerald-600" />
                </div>
                <span className="text-sm font-medium text-slate-700">Generate Report</span>
              </Link>
            </div>
          </div>

          {/* Device Categories */}
          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Device Categories</h3>
            {deviceStats?.by_category && Object.keys(deviceStats.by_category).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(deviceStats.by_category).map(([cat, count]: [string, any]) => (
                  <div key={cat} className="flex items-center justify-between py-1.5">
                    <span className="text-sm text-slate-600 capitalize">{cat}</span>
                    <span className="text-sm font-semibold text-slate-900">{count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">No devices categorized yet</p>
            )}
          </div>

          {/* Compliance */}
          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Compliance Frameworks</h3>
            <div className="space-y-2">
              {['ISO 27001', 'Cyber Essentials', 'SOC2'].map((fw) => (
                <div key={fw} className="flex items-center gap-2 py-1">
                  <Shield className="w-4 h-4 text-brand-500" />
                  <span className="text-sm text-slate-600">{fw}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function VerdictIcon({ verdict }: { verdict: string | null }) {
  if (verdict === 'pass') return <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
  if (verdict === 'fail') return <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
  if (verdict === 'advisory') return <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
  return <Clock className="w-5 h-5 text-blue-400 flex-shrink-0" />
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'badge-pending',
    running: 'bg-blue-100 text-blue-700 border border-blue-200',
    completed: 'badge-pass',
    failed: 'badge-fail',
    cancelled: 'badge-na',
  }
  return <span className={`badge ${styles[status] || 'badge-na'}`}>{status}</span>
}
