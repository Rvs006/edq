import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { adminApi, getApiErrorMessage } from '@/lib/api'
import type { UserProfile } from '@/lib/types'
import { toLocalDateString } from '@/lib/testContracts'
import { Users, Server, Loader2, Plus, X } from 'lucide-react'
import Callout from '@/components/common/Callout'
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
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'engineer', full_name: '' })

  const { data: users, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminApi.users().then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (d as { items?: UserProfile[] })?.items ?? []
    }),
    retry: 1,
    staleTime: 30_000,
  })

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await adminApi.updateUser(userId, { role: newRole })
      toast.success('Role updated')
      await refetch()
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to update role'))
      await refetch()
    }
  }

  const handleToggleActive = async (userId: string, currentlyActive: boolean) => {
    try {
      await adminApi.updateUser(userId, { is_active: !currentlyActive })
      toast.success(currentlyActive ? 'User deactivated' : 'User activated')
      await refetch()
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to update user status'))
      await refetch()
    }
  }

  const handleCreateUser = async () => {
    if (!newUser.username.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      toast.error('Username, email, and password are required')
      return
    }
    setCreating(true)
    try {
      await adminApi.createUser({
        username: newUser.username.trim(),
        email: newUser.email.trim(),
        password: newUser.password,
        full_name: newUser.full_name.trim() || undefined,
        role: newUser.role,
      })
      toast.success('User created')
      setShowCreate(false)
      setNewUser({ username: '', email: '', password: '', role: 'engineer', full_name: '' })
      await refetch()
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Failed to create user'))
    } finally {
      setCreating(false)
    }
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <Callout variant="error">Failed to load users. Please check your connection and permissions.</Callout>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          Retry
        </button>
      </div>
    )
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
    <div>
      <div className="flex justify-end mb-4">
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> Create User
        </button>
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowCreate(false)}>
          <div className="bg-white dark:bg-dark-surface rounded-xl shadow-xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">Create User</h3>
              <button onClick={() => setShowCreate(false)} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800">
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Username *</label>
                <input value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                  placeholder="johndoe" autoFocus />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Full Name</label>
                <input value={newUser.full_name} onChange={e => setNewUser({ ...newUser, full_name: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                  placeholder="John Doe" />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Email *</label>
                <input type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                  placeholder="john@example.com" />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Password *</label>
                <input type="password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                  placeholder="Minimum 8 characters" />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Role</label>
                <select value={newUser.role} onChange={e => setNewUser({ ...newUser, role: e.target.value })}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 outline-none">
                  <option value="engineer">Engineer</option>
                  <option value="reviewer">Reviewer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-slate-700 rounded-lg">Cancel</button>
              <button onClick={handleCreateUser} disabled={creating || !newUser.username.trim() || !newUser.email.trim() || !newUser.password.trim()}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
                {creating ? 'Creating...' : 'Create User'}
              </button>
            </div>
          </div>
        </div>
      )}

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
                      aria-label={`Role for ${u.username}`}
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
                    {u.last_login ? toLocalDateString(u.last_login) : 'Never'}
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
                  <td colSpan={6} className="py-8 text-center text-sm text-zinc-500">
                    <Users className="w-8 h-8 text-zinc-300 mx-auto mb-2" />
                    No users found. Click "Create User" to add the first user.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
  const aiProviderStatus =
    systemInfo.ai_status === 'configured'
      ? 'Configured'
      : systemInfo.ai_status === 'invalid_configuration'
        ? 'Configuration error'
        : 'Not configured'
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
        ['AI Synopsis Provider', aiProviderStatus],
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
      {systemInfo.ai_message && (
        <div className="mt-4">
          <Callout
            variant={systemInfo.ai_status === 'invalid_configuration' ? 'warning' : 'info'}
            title="AI synopsis configuration"
          >
            {systemInfo.ai_message}
          </Callout>
        </div>
      )}
      {systemInfo.checked_at && (
        <p className="text-[11px] text-zinc-400 dark:text-slate-500 mt-3">
          Last checked: {toLocalDateString(systemInfo.checked_at)}
        </p>
      )}
    </div>
  )
}
