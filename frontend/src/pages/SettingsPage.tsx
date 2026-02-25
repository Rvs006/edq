import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { authApi } from '@/lib/api'
import { Settings, User, Lock, Bell, Shield, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SettingsPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('profile')

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'notifications', label: 'Notifications', icon: Bell },
  ]

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Settings</h1>
        <p className="section-subtitle">Manage your account and application preferences</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-5">
        {/* Tabs */}
        <div className="sm:w-48 flex sm:flex-col gap-1 overflow-x-auto pb-1 sm:pb-0">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1">
          {activeTab === 'profile' && <ProfileSettings user={user} />}
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'notifications' && <NotificationSettings />}
        </div>
      </div>
    </div>
  )
}

function ProfileSettings({ user }: { user: any }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold text-slate-900 mb-4">Profile Information</h2>
      <div className="space-y-4">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-brand-500 flex items-center justify-center">
            <span className="text-xl font-bold text-white">
              {user?.full_name?.[0] || user?.username?.[0] || 'U'}
            </span>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900">{user?.full_name || user?.username}</h3>
            <p className="text-sm text-slate-500">{user?.email}</p>
            <span className="badge text-[10px] bg-brand-50 text-brand-600 border border-brand-200 capitalize mt-1">
              {user?.role}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Username</label>
            <input type="text" value={user?.username || ''} className="input" disabled />
          </div>
          <div>
            <label className="label">Email</label>
            <input type="email" value={user?.email || ''} className="input" disabled />
          </div>
          <div>
            <label className="label">Full Name</label>
            <input type="text" value={user?.full_name || ''} className="input" disabled />
          </div>
          <div>
            <label className="label">Role</label>
            <input type="text" value={user?.role || ''} className="input capitalize" disabled />
          </div>
        </div>

        <p className="text-xs text-slate-400">Contact an administrator to update your profile information.</p>
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
      <h2 className="font-semibold text-slate-900 mb-4">Change Password</h2>
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
            className="input" placeholder="Minimum 8 characters" required />
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

function NotificationSettings() {
  const [settings, setSettings] = useState({
    critical_failures: true,
    test_complete: true,
    device_discovered: true,
    report_ready: false,
  })

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-slate-900 mb-4">Notification Preferences</h2>
      <div className="space-y-4">
        {[
          { key: 'critical_failures', label: 'Critical Test Failures', desc: 'Get notified when essential tests fail' },
          { key: 'test_complete', label: 'Test Run Complete', desc: 'Notification when a test run finishes' },
          { key: 'device_discovered', label: 'New Device Discovered', desc: 'Alert when a new device is found on the network' },
          { key: 'report_ready', label: 'Report Ready', desc: 'Notification when a report is generated' },
        ].map(item => (
          <div key={item.key} className="flex items-center justify-between py-2">
            <div>
              <p className="text-sm font-medium text-slate-900">{item.label}</p>
              <p className="text-xs text-slate-500">{item.desc}</p>
            </div>
            <button
              onClick={() => setSettings(s => ({ ...s, [item.key]: !s[item.key as keyof typeof s] }))}
              className={`w-10 h-6 rounded-full transition-colors relative ${
                settings[item.key as keyof typeof settings] ? 'bg-brand-500' : 'bg-slate-200'
              }`}
            >
              <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                settings[item.key as keyof typeof settings] ? 'translate-x-4.5' : 'translate-x-0.5'
              }`} />
            </button>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400 mt-4">Notification preferences are stored locally. Server-side notifications are always sent for critical events.</p>
    </div>
  )
}
