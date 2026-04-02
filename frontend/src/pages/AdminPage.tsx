import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '@/lib/api'
import type { UserProfile } from '@/lib/types'
import { Users, Server, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState('users')

  const tabs = [
    { id: 'users', label: 'Users', icon: Users },
    { id: 'system', label: 'System', icon: Server },
  ]

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Administration</h1>
        <p className="section-subtitle">Manage users and system configuration</p>
      </div>

      <div className="flex gap-2 mb-5 border-b border-zinc-200 dark:border-slate-700/50">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.id
                ? 'border-brand-500 text-brand-500'
                : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'system' && <SystemTab />}
    </div>
  )
}

function UsersTab() {
  const queryClient = useQueryClient()
  const { data: users, isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminApi.users().then(r => r.data),
  })

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await adminApi.updateUser(userId, { role: newRole })
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('Role updated')
    } catch {
      toast.error('Failed to update role')
    }
  }

  const handleToggleActive = async (userId: string, currentlyActive: boolean) => {
    try {
      await adminApi.updateUser(userId, { is_active: !currentlyActive })
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success(currentlyActive ? 'User deactivated' : 'User activated')
    } catch {
      toast.error('Failed to update user status')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
      </div>
    )
  }

  const userList: UserProfile[] = Array.isArray(users) ? users : []

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50/50 dark:bg-slate-800/50">
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">User</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Email</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Role</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden sm:table-cell">Status</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400 hidden md:table-cell">Last Login</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-zinc-500 dark:text-slate-400">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-slate-700/50">
            {userList.length > 0 ? userList.map((u: UserProfile) => (
              <tr key={u.id} className="hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center">
                      <span className="text-xs font-semibold text-white">
                        {u.full_name?.[0] || u.username?.[0] || 'U'}
                      </span>
                    </div>
                    <div>
                      <p className="font-medium text-zinc-900 dark:text-slate-100">{u.full_name || u.username}</p>
                      <p className="text-xs text-zinc-500">@{u.username}</p>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4 text-zinc-600 dark:text-slate-400 text-xs">{u.email}</td>
                <td className="py-3 px-4">
                  <select
                    value={u.role}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    className="text-xs border border-zinc-200 dark:border-slate-700/50 rounded px-2 py-1 bg-white dark:bg-slate-800 dark:text-slate-200 capitalize"
                  >
                    <option value="admin">Admin</option>
                    <option value="engineer">Engineer</option>
                    <option value="reviewer">Reviewer</option>
                  </select>
                </td>
                <td className="py-3 px-4 hidden sm:table-cell">
                  <span className={`badge text-[10px] ${u.is_active ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                    {u.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="py-3 px-4 text-xs text-zinc-500 hidden md:table-cell">
                  {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                </td>
                <td className="py-3 px-4">
                  <button
                    onClick={() => handleToggleActive(u.id, u.is_active)}
                    className={`text-xs font-medium px-2 py-1 rounded ${u.is_active ? 'text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30' : 'text-green-600 hover:bg-green-50 dark:hover:bg-green-950/30'}`}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan={6} className="py-8 text-center text-sm text-zinc-500">No users found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SystemTab() {
  const { frontendHealthy } = useOnlineStatus()
  const { data: info, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: () => adminApi.systemInfo().then(r => r.data),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
      </div>
    )
  }

  const systemInfo = info || {}
  const tools = systemInfo.tools || {}
  const hasTool = (key: string) => Boolean(tools[key] && tools[key] !== 'unavailable')
  const sections = [
    {
      title: 'Services',
      items: [
        ['Frontend UI', frontendHealthy ? 'Loaded' : 'Unavailable'],
        ['Backend API', systemInfo.api_status || 'Unavailable'],
        ['Database', systemInfo.database || 'Unavailable'],
        ['Tools Sidecar', systemInfo.tools_sidecar_status || 'Unavailable'],
      ],
    },
    {
      title: 'Application',
      items: [
        ['Version', systemInfo.version || systemInfo.app_version || '1.0.0'],
        ['Overall Status', systemInfo.status || 'unknown'],
        ['AI Features', systemInfo.ai_enabled ? 'Enabled' : 'Disabled'],
      ],
    },
    {
      title: 'Security Tools',
      items: [
        ['Nmap', hasTool('nmap') ? 'Available' : 'Not Found'],
        ['testssl.sh', hasTool('testssl') ? 'Available' : 'Not Found'],
        ['ssh-audit', hasTool('ssh_audit') ? 'Available' : 'Not Found'],
        ['Hydra', hasTool('hydra') ? 'Available' : 'Not Found'],
        ['Nikto', hasTool('nikto') ? 'Available' : 'Not Found'],
        ['snmpwalk', hasTool('snmpwalk') ? 'Available' : 'Not Found'],
      ],
    },
  ]

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {sections.map(section => (
          <div key={section.title} className="card p-5">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">{section.title}</h3>
            <dl className="space-y-3">
              {section.items.map(([label, value]) => (
                <div key={label} className="flex justify-between text-sm">
                  <dt className="text-zinc-500 dark:text-slate-400">{label}</dt>
                  <dd className="text-zinc-900 dark:text-slate-100 font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
      {systemInfo.checked_at && (
        <p className="text-[11px] text-zinc-400 dark:text-slate-500 mt-3">
          Last checked: {new Date(systemInfo.checked_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  )
}
