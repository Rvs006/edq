import { useState, useEffect, useRef } from 'react'
import { RefreshCw, Loader2, AlertCircle } from 'lucide-react'
import Callout from '@/components/common/Callout'
import { agentsApi } from '@/lib/api'

interface AgentFromApi {
  id: string
  name: string
  hostname: string | null
  api_key_prefix: string
  platform: string | null
  agent_version: string | null
  ip_address: string | null
  status: string
  last_heartbeat: string | null
  capabilities: unknown
  current_task: string | null
  is_active: boolean
  created_at: string
}

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

function mapApiAgent(a: AgentFromApi): Agent {
  const platformMap: Record<string, string> = {
    macos: 'macOS',
    windows: 'Windows',
    linux: 'Linux',
  }
  return {
    id: a.id,
    name: a.name || a.hostname || 'Unknown',
    engineer: a.hostname || a.api_key_prefix,
    os: a.platform ? platformMap[a.platform] || a.platform : 'Unknown',
    version: a.agent_version || 'N/A',
    status: (['online', 'busy', 'offline'].includes(a.status) ? a.status : 'offline') as Agent['status'],
    lastHeartbeat: a.last_heartbeat || a.created_at,
    syncedTests: 0,
    totalTests: 0,
  }
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchAgents() {
      try {
        const res = await agentsApi.list()
        if (cancelled) return
        const apiAgents: AgentFromApi[] = res.data
        setAgents(apiAgents.map(mapApiAgent))
        setError(null)
      } catch {
        if (cancelled) return
        setAgents([])
        setError('Failed to load distributed agent registrations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchAgents()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (agents.length === 0) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/ws/agents`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'heartbeat' && data.agent_id) {
            setAgents((prev) =>
              prev.map((agent) =>
                agent.id === data.agent_id
                  ? {
                      ...agent,
                      status: (['online', 'busy', 'offline'].includes(data.status) ? data.status : agent.status) as Agent['status'],
                      lastHeartbeat: data.timestamp || new Date().toISOString(),
                    }
                  : agent
              )
            )
          }
        } catch {
          // Ignore malformed heartbeat payloads
        }
      }
    } catch {
      // WebSocket is optional here; the page still works without live updates.
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [agents.length])

  const onlineCount = agents.filter((agent) => agent.status === 'online').length
  const busyCount = agents.filter((agent) => agent.status === 'busy').length
  const offlineCount = agents.filter((agent) => agent.status === 'offline').length

  const stats = [
    { label: 'Online', value: onlineCount, color: 'text-emerald-600' },
    { label: 'Busy (Scanning)', value: busyCount, color: 'text-amber-600' },
    { label: 'Offline', value: offlineCount, color: 'text-zinc-500' },
  ]

  if (loading) {
    return (
      <div className="page-container">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-slate-100 mb-4">Distributed Agents</h1>
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading agents...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-container">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-slate-100 mb-4">Distributed Agents</h1>
        <Callout variant="error">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            <span>Failed to load agents. {error}</span>
          </div>
        </Callout>
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="page-container">
        <div className="mb-6">
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Distributed Agents</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Optional runner registrations for distributed deployments.
          </p>
        </div>

        <Callout variant="info" className="mb-5">
          <div>
            <strong className="block text-[13px] font-semibold mb-0.5">You probably do not need this</strong>
            In the normal EDQ setup, each engineer runs Docker locally on their own laptop and scans from that same machine.
            This page only matters if you later build a separate fleet of registered remote runners.
          </div>
        </Callout>

        <div className="bg-white dark:bg-dark-card rounded-xl border border-zinc-200 dark:border-slate-700/50 p-12 text-center">
          <RefreshCw className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <p className="text-sm font-medium text-zinc-600 dark:text-slate-400">No distributed agents registered</p>
          <p className="text-xs text-zinc-400 mt-1">
            That is normal if engineers run EDQ locally instead of through a shared runner fleet.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">Distributed Agents</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Optional fleet view for registered remote runner instances
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <RefreshCw className="w-3 h-3" />
          Live heartbeat view
        </div>
      </div>

      <Callout variant="info" className="mb-5">
        <div>
          <strong className="block text-[13px] font-semibold mb-0.5">What is this page?</strong>
          This page is for a distributed EDQ deployment where separate runner machines register themselves
          and report heartbeats. It is not needed for the normal laptop-local workflow where the engineer
          opens EDQ in the browser and the same laptop runs the Docker containers.
        </div>
      </Callout>

      <div className="grid grid-cols-3 gap-4 mb-5">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-white dark:bg-dark-card rounded-xl border border-zinc-200 dark:border-slate-700/50 p-5">
            <div className="text-[13px] text-zinc-500">{stat.label}</div>
            <div className={`text-2xl font-bold ${stat.color}`} data-testid="stat-value">
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white dark:bg-dark-card rounded-xl border border-zinc-200 dark:border-slate-700/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 dark:border-slate-700/50 bg-zinc-50/60 dark:bg-slate-800/60">
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Status
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Agent
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Engineer
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  OS
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Version
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Synced
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-500 dark:text-slate-400 text-xs uppercase tracking-wide">
                  Last Heartbeat
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
              {agents.map((agent) => {
                const sc = statusConfig[agent.status]
                const outdated = agent.version !== CURRENT_VERSION && agent.version !== 'N/A'
                return (
                  <tr key={agent.id} className="hover:bg-zinc-50/60 dark:hover:bg-slate-800/60 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${sc.dot}`} />
                        <span className={`text-[13px] font-medium ${sc.text}`}>{sc.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-medium text-zinc-900 dark:text-slate-100">{agent.name}</td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-slate-400">{agent.engineer}</td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-slate-400">{agent.os}</td>
                    <td className="px-4 py-3">
                      {outdated ? (
                        <span className="text-amber-600 font-semibold">{agent.version} !</span>
                      ) : (
                        <span className="text-zinc-500">{agent.version}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-slate-400">
                      {agent.syncedTests}/{agent.totalTests}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-slate-400">{heartbeatText(agent.lastHeartbeat)}</td>
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
