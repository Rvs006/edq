import { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'
import { authApi, healthApi } from '@/lib/api'
import { User, Lock, Sun, Moon, Monitor as MonitorIcon, Loader2, Server, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'

type Theme = 'light' | 'dark' | 'system'

function getStoredTheme(): Theme {
  return (localStorage.getItem('edq_theme') as Theme) || 'light'
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === 'dark') {
    root.classList.add('dark')
  } else if (theme === 'system') {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  } else {
    root.classList.remove('dark')
  }
}

export default function SettingsPage({ tourState }: { tourState?: any }) {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('profile')

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'appearance', label: 'Appearance', icon: Sun },
    { id: 'system', label: 'System Status', icon: Server },
  ]

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Settings</h1>
        <p className="section-subtitle">Manage your account and application preferences</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-5">
        <div className="sm:w-48 flex sm:flex-col gap-1 overflow-x-auto pb-1 sm:pb-0">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-brand-50 text-brand-500'
                  : 'text-zinc-600 hover:bg-zinc-100'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1" data-tour="settings-section">
          {activeTab === 'profile' && <ProfileSettings user={user} />}
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'appearance' && <AppearanceSettings />}
          {activeTab === 'system' && <SystemStatus />}
          <HelpSection tourState={tourState} />
        </div>
      </div>
    </div>
  )
}

function ProfileSettings({ user }: { user: any }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 mb-4">Profile Information</h2>
      <div className="space-y-4">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-brand-500 flex items-center justify-center">
            <span className="text-xl font-bold text-white">
              {user?.full_name?.[0] || user?.username?.[0] || 'U'}
            </span>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-zinc-900">{user?.full_name || user?.username}</h3>
            <p className="text-sm text-zinc-500">{user?.email}</p>
            <span className="badge text-[10px] bg-brand-50 text-brand-500 border border-brand-100 capitalize mt-1">
              {user?.role}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Username</label>
            <input type="text" value={user?.username || ''} className="input bg-zinc-50" disabled />
          </div>
          <div>
            <label className="label">Email</label>
            <input type="email" value={user?.email || ''} className="input bg-zinc-50" disabled />
          </div>
          <div>
            <label className="label">Full Name</label>
            <input type="text" value={user?.full_name || ''} className="input bg-zinc-50" disabled />
          </div>
          <div>
            <label className="label">Role</label>
            <input type="text" value={user?.role || ''} className="input bg-zinc-50 capitalize" disabled />
          </div>
        </div>

        <p className="text-xs text-zinc-400">Contact an administrator to update your profile information.</p>
      </div>
    </div>
  )
}

function SecuritySettings() {
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.new_password !== form.confirm_password) {
      toast.error('Passwords do not match')
      return
    }
    if (form.new_password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    if (!/[A-Z]/.test(form.new_password)) {
      toast.error('Password must contain at least one uppercase letter')
      return
    }
    if (!/[a-z]/.test(form.new_password)) {
      toast.error('Password must contain at least one lowercase letter')
      return
    }
    if (!/[0-9]/.test(form.new_password)) {
      toast.error('Password must contain at least one digit')
      return
    }
    setLoading(true)
    try {
      await authApi.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
      })
      toast.success('Password changed successfully')
      setForm({ current_password: '', new_password: '', confirm_password: '' })
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 mb-4">Change Password</h2>
      <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
        <div>
          <label className="label">Current Password</label>
          <input type="password" value={form.current_password}
            onChange={(e) => setForm({ ...form, current_password: e.target.value })}
            className="input" required />
        </div>
        <div>
          <label className="label">New Password</label>
          <input type="password" value={form.new_password}
            onChange={(e) => setForm({ ...form, new_password: e.target.value })}
            className="input" placeholder="Min 8 chars, uppercase, lowercase, digit" required />
        </div>
        <div>
          <label className="label">Confirm New Password</label>
          <input type="password" value={form.confirm_password}
            onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
            className="input" required />
        </div>
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
          Change Password
        </button>
      </form>
    </div>
  )
}

function AppearanceSettings() {
  const [theme, setTheme] = useState<Theme>(getStoredTheme)

  useEffect(() => {
    localStorage.setItem('edq_theme', theme)
    applyTheme(theme)
  }, [theme])

  const options: { value: Theme; label: string; icon: React.ElementType }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'system', label: 'System', icon: MonitorIcon },
  ]

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 mb-4">Theme</h2>
      <div className="grid grid-cols-3 gap-3 max-w-md">
        {options.map(opt => (
          <button
            key={opt.value}
            onClick={() => setTheme(opt.value)}
            className={`flex flex-col items-center gap-2 p-4 rounded-lg border transition-colors ${
              theme === opt.value
                ? 'border-brand-500 bg-brand-50'
                : 'border-zinc-200 hover:border-zinc-300'
            }`}
          >
            <opt.icon className={`w-5 h-5 ${theme === opt.value ? 'text-brand-500' : 'text-zinc-400'}`} />
            <span className="text-sm font-medium text-zinc-700">{opt.label}</span>
          </button>
        ))}
      </div>
      <p className="text-xs text-zinc-400 mt-3">Theme preference is saved locally.</p>
    </div>
  )
}

function SystemStatus() {
  const [versions, setVersions] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  const fetchVersions = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await healthApi.toolVersions()
      setVersions(res.data.tools || {})
      setCheckedAt(new Date())
    } catch (err: any) {
      setError('Failed to connect to tools sidecar')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchVersions() }, [])

  const toolLabels: Record<string, string> = {
    nmap: 'Nmap',
    testssl: 'testssl.sh',
    ssh_audit: 'ssh-audit',
    hydra: 'Hydra',
    nikto: 'Nikto',
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-zinc-900">System Status</h2>
        <button onClick={fetchVersions} className="text-xs text-brand-500 hover:text-brand-600 font-medium">
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-6 text-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto" />
        </div>
      ) : error ? (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{error}</div>
      ) : (
        <div className="space-y-2">
          {Object.entries(toolLabels).map(([key, label]) => {
            const version = versions[key]
            const available = version && version !== 'unavailable'
            return (
              <div key={key} className="flex items-center gap-3 py-2 px-3 rounded-lg bg-zinc-50">
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${available ? 'bg-emerald-500' : 'bg-red-400'}`} />
                <span className="text-sm font-medium text-zinc-700 w-24">{label}</span>
                <span className="text-xs text-zinc-500 flex-1 truncate font-mono">
                  {available ? version : 'Not available'}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {checkedAt && (
        <p className="text-[11px] text-zinc-400 mt-3">
          Last checked: {checkedAt.toLocaleTimeString()}
        </p>
      )}
    </div>
  )
}

function HelpSection({ tourState }: { tourState?: any }) {
  const navigate = useNavigate()

  return (
    <div className="card p-5 mt-5">
      <h2 className="font-semibold text-zinc-900 mb-4">Help</h2>
      <div className="space-y-3">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-brand-50 flex items-center justify-center shrink-0">
            <RotateCcw className="w-4 h-4 text-brand-500" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-zinc-900 mb-0.5">Guided Tour</h3>
            <p className="text-xs text-zinc-500 mb-2">
              Restart the interactive walkthrough to learn about EDQ features.
            </p>
            <button
              onClick={() => {
                if (tourState?.restartTour) {
                  tourState.restartTour()
                } else {
                  localStorage.removeItem('edq_tour_completed')
                  localStorage.removeItem('edq_tour_dismissed')
                  navigate('/')
                }
              }}
              className="btn-secondary text-sm py-1.5 px-3"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Restart Guided Tour
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
