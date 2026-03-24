import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import Callout from '@/components/common/Callout'

interface Agent {
  id: string
  name: string
  engineer: string
  os: string
  version: string
  status: 'online' | 'busy' | 'offline'
  lastHeartbeat: string
  syncedTests: number
  totalTests: number
}

/** Demo agents — in production these would come from a WebSocket or polling API. */
const DEMO_AGENTS: Agent[] = [
  {
    id: '1',
    name: 'Dylan-MBP',
    engineer: 'Dylan M.',
    os: 'macOS 14',
    version: '1.0.0',
    status: 'online',
    lastHeartbeat: new Date(Date.now() - 120_000).toISOString(),
    syncedTests: 47,
    totalTests: 47,
  },
  {
    id: '2',
    name: 'Sarah-Thinkpad',
    engineer: 'Sarah K.',
    os: 'Win 11',
    version: '1.0.0',
    status: 'busy',
    lastHeartbeat: new Date(Date.now() - 5_000).toISOString(),
    syncedTests: 45,
    totalTests: 46,
  },
  {
    id: '3',
    name: 'James-MBP',
    engineer: 'James T.',
    os: 'macOS 14',
    version: '1.0.0',
    status: 'online',
    lastHeartbeat: new Date(Date.now() - 900_000).toISOString(),
    syncedTests: 32,
    totalTests: 32,
  },
  {
    id: '4',
    name: 'Alex-Dell',
    engineer: 'Alex R.',
    os: 'Win 10',
    version: '0.9.8',
    status: 'offline',
    lastHeartbeat: new Date(Date.now() - 10_800_000).toISOString(),
    syncedTests: 28,
    totalTests: 30,
  },
]

const CURRENT_VERSION = '1.0.0'

function heartbeatText(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'Just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

const statusConfig = {
  online: { label: 'Online', dot: 'bg-emerald-500', text: 'text-emerald-700' },
  busy: { label: 'Scanning', dot: 'bg-amber-500 animate-pulse', text: 'text-amber-700' },
  offline: { label: 'Offline', dot: 'bg-zinc-400', text: 'text-zinc-500' },
} as const

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>(DEMO_AGENTS)

  // Simulate heartbeat updates every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setAgents((prev) =>
        prev.map((a) => ({
          ...a,
          lastHeartbeat:
            a.status !== 'offline'
              ? new Date(Date.now() - Math.floor(Math.random() * 30_000)).toISOString()
              : a.lastHeartbeat,
        }))
      )
    }, 5_000)
    return () => clearInterval(interval)
  }, [])

  const onlineCount = agents.filter((a) => a.status === 'online').length
  const busyCount = agents.filter((a) => a.status === 'busy').length
  const offlineCount = agents.filter((a) => a.status === 'offline').length

  const stats = [
    { label: 'Online', value: onlineCount, color: 'text-emerald-600' },
    { label: 'Busy (Scanning)', value: busyCount, color: 'text-amber-600' },
    { label: 'Offline', value: offlineCount, color: 'text-zinc-500' },
  ]

  return (
    <div className="p-4 sm:p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900">Agent Fleet</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Monitor connected EDQ agents across your team
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <RefreshCw className="w-3 h-3" />
          Updates every 5s
        </div>
      </div>

      <Callout variant="info" className="mb-5">
        <div>
          <strong className="block text-[13px] font-semibold mb-0.5">What is this page?</strong>
          Each engineer runs an EDQ Agent app on their laptop. This page shows which laptops are
          connected, who is actively scanning, and whether anyone needs a software update. Think of
          it like a fleet tracker for your team's testing equipment.{' '}
          <strong>Status updates every 5 seconds.</strong>
        </div>
      </Callout>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        {stats.map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-zinc-200 p-5">
            <div className="text-[13px] text-zinc-500">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Agent table */}
      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50/60">
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Status
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Agent
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Engineer
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  OS
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Version
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Synced
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 text-xs uppercase tracking-wide">
                  Last Heartbeat
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {agents.map((agent) => {
                const sc = statusConfig[agent.status]
                const outdated = agent.version !== CURRENT_VERSION
                return (
                  <tr key={agent.id} className="hover:bg-zinc-50/60 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${sc.dot}`} />
                        <span className={`text-[13px] font-medium ${sc.text}`}>{sc.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-medium text-zinc-900">{agent.name}</td>
                    <td className="px-4 py-3 text-zinc-500">{agent.engineer}</td>
                    <td className="px-4 py-3 text-zinc-500">{agent.os}</td>
                    <td className="px-4 py-3">
                      {outdated ? (
                        <span className="text-amber-600 font-semibold">
                          {agent.version} ⚠
                        </span>
                      ) : (
                        <span className="text-zinc-500">{agent.version}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-500">
                      {agent.syncedTests}/{agent.totalTests}
                    </td>
                    <td className="px-4 py-3 text-zinc-500">{heartbeatText(agent.lastHeartbeat)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
