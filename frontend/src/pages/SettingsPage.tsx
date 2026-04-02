import { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useTheme } from '@/contexts/ThemeContext'
import { useNavigate } from 'react-router-dom'
import { authApi, brandingApi } from '@/lib/api'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import type { TourState } from '@/lib/types'
import { User, Lock, Sun, Moon, Loader2, Server, RotateCcw, Save, Palette, Upload, Shield, ShieldCheck, ShieldOff } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SettingsPage({ tourState }: { tourState?: TourState }) {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('profile')

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'appearance', label: 'Appearance', icon: Sun },
    { id: 'branding', label: 'Report Branding', icon: Palette },
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
                  ? 'bg-brand-50 text-brand-500 dark:bg-brand-950/30 dark:text-brand-300'
                  : 'text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-800'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1" data-tour="settings-section">
          {activeTab === 'profile' && <ProfileSettings user={user} />}
          {activeTab === 'security' && <>
            <TwoFactorSettings />
            <div className="mt-5" />
            <SecuritySettings />
          </>}
          {activeTab === 'appearance' && <AppearanceSettings />}
          {activeTab === 'branding' && <BrandingSettings />}
          {activeTab === 'system' && <SystemStatus />}
          <HelpSection tourState={tourState} />
        </div>
      </div>
    </div>
  )
}

function ProfileSettings({ user }: { user: { full_name?: string | null; username?: string; email?: string; role?: string; id?: string } | null }) {
  const { refreshUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    full_name: (user?.full_name as string) || '',
    email: (user?.email as string) || '',
  })

  const handleSave = async () => {
    setSaving(true)
    try {
      await authApi.updateProfile(form)
      toast.success('Profile updated')
      setEditing(false)
      if (refreshUser) refreshUser()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to update profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-zinc-900 dark:text-slate-100">Profile Information</h2>
        {!editing ? (
          <button onClick={() => setEditing(true)} className="text-xs text-brand-500 hover:text-brand-600 font-medium">
            Edit Profile
          </button>
        ) : (
          <div className="flex gap-2">
            <button onClick={() => { setEditing(false); setForm({ full_name: (user?.full_name as string) || '', email: (user?.email as string) || '' }) }} className="text-xs text-zinc-500 hover:text-zinc-600 font-medium">
              Cancel
            </button>
            <button onClick={handleSave} disabled={saving} className="btn-primary text-xs py-1 px-3">
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Save
            </button>
          </div>
        )}
      </div>
      <div className="space-y-4">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-brand-500 flex items-center justify-center">
            <span className="text-xl font-bold text-white">
              {(user?.full_name ?? '')[0] || (user?.username ?? '')[0] || 'U'}
            </span>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-slate-100">{user?.full_name || user?.username}</h3>
            <p className="text-sm text-zinc-500">{user?.email}</p>
            <span className="badge text-[10px] bg-brand-50 text-brand-500 border border-brand-100 dark:bg-brand-950/30 dark:text-brand-300 dark:border-brand-800 capitalize mt-1">
              {user?.role}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Username</label>
            <input type="text" value={(user?.username as string) || ''} className="input bg-zinc-50" disabled />
          </div>
          <div>
            <label className="label">Email</label>
            <input type="email" value={editing ? form.email : ((user?.email as string) || '')} onChange={e => setForm({ ...form, email: e.target.value })} className={`input ${editing ? '' : 'bg-zinc-50'}`} disabled={!editing} />
          </div>
          <div>
            <label className="label">Full Name</label>
            <input type="text" value={editing ? form.full_name : ((user?.full_name as string) || '')} onChange={e => setForm({ ...form, full_name: e.target.value })} className={`input ${editing ? '' : 'bg-zinc-50'}`} disabled={!editing} />
          </div>
          <div>
            <label className="label">Role</label>
            <input type="text" value={(user?.role as string) || ''} className="input bg-zinc-50 capitalize" disabled />
          </div>
        </div>

        {!editing && <p className="text-xs text-zinc-400">Click "Edit Profile" to update your name or email.</p>}
      </div>
    </div>
  )
}

function TwoFactorSettings() {
  const [status, setStatus] = useState<{ enabled: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [setupData, setSetupData] = useState<{ secret: string; qr_code_base64: string } | null>(null)
  const [verifyCode, setVerifyCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    authApi.twoFactorStatus().then(res => setStatus(res.data)).catch((err) => { console.error('Failed to fetch 2FA status:', err) }).finally(() => setLoading(false))
  }, [])

  const handleSetup = async () => {
    setSubmitting(true)
    try {
      const res = await authApi.twoFactorSetup()
      setSetupData(res.data)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to start 2FA setup')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVerify = async () => {
    if (verifyCode.length !== 6) return
    setSubmitting(true)
    try {
      await authApi.twoFactorVerify(verifyCode)
      toast.success('Two-factor authentication enabled!')
      setSetupData(null)
      setVerifyCode('')
      setStatus({ enabled: true })
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Invalid code')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDisable = async () => {
    if (disableCode.length !== 6 || !disablePassword) return
    setSubmitting(true)
    try {
      await authApi.twoFactorDisable(disableCode, disablePassword)
      toast.success('Two-factor authentication disabled')
      setDisableCode('')
      setDisablePassword('')
      setStatus({ enabled: false })
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to disable 2FA')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="card p-5">
        <div className="py-6 text-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto" />
        </div>
      </div>
    )
  }

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="w-5 h-5 text-brand-500" />
        <h2 className="font-semibold text-zinc-900 dark:text-slate-100">Two-Factor Authentication</h2>
      </div>

      {status?.enabled ? (
        <div>
          <div className="flex items-center gap-2 mb-4 p-3 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/50 rounded-lg">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">2FA is enabled</span>
          </div>

          <p className="text-xs text-zinc-500 mb-3">To disable 2FA, enter your current TOTP code and password:</p>
          <div className="space-y-3 max-w-sm">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={disableCode}
              onChange={e => setDisableCode(e.target.value.replace(/\D/g, ''))}
              className="input text-center font-mono tracking-widest"
              placeholder="6-digit code"
            />
            <input
              type="password"
              value={disablePassword}
              onChange={e => setDisablePassword(e.target.value)}
              className="input"
              placeholder="Your password"
            />
            <button onClick={handleDisable} disabled={submitting || disableCode.length !== 6 || !disablePassword} className="btn-secondary text-sm py-1.5 px-3 text-red-500 border-red-200 hover:bg-red-50">
              {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldOff className="w-3 h-3" />}
              Disable 2FA
            </button>
          </div>
        </div>
      ) : setupData ? (
        <div>
          <p className="text-sm text-zinc-600 dark:text-slate-400 mb-3">
            Scan this QR code with your authenticator app (Google Authenticator, Authy, 1Password):
          </p>
          <div className="flex flex-col items-center gap-4 mb-4">
            <img
              src={`data:image/png;base64,${setupData.qr_code_base64}`}
              alt="2FA QR Code"
              className="w-48 h-48 rounded-lg border border-zinc-200 dark:border-slate-700 bg-white p-2"
            />
            <div className="text-center">
              <p className="text-[11px] text-zinc-400 mb-1">Or enter this key manually:</p>
              <code className="text-xs font-mono bg-zinc-100 dark:bg-slate-800 px-2 py-1 rounded select-all">
                {setupData.secret}
              </code>
            </div>
          </div>
          <div className="max-w-sm space-y-3">
            <div>
              <label className="label">Verification Code</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={verifyCode}
                onChange={e => setVerifyCode(e.target.value.replace(/\D/g, ''))}
                className="input text-center text-xl font-mono tracking-[0.4em]"
                placeholder="000000"
                autoFocus
              />
            </div>
            <button onClick={handleVerify} disabled={submitting || verifyCode.length !== 6} className="btn-primary w-full">
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
              Verify & Enable 2FA
            </button>
            <button onClick={() => { setSetupData(null); setVerifyCode('') }} className="text-xs text-zinc-500 hover:text-zinc-600">
              Cancel setup
            </button>
          </div>
        </div>
      ) : (
        <div>
          <p className="text-sm text-zinc-600 dark:text-slate-400 mb-4">
            Add an extra layer of security to your account. You'll need an authenticator app like
            Google Authenticator, Authy, or 1Password.
          </p>
          <button onClick={handleSetup} disabled={submitting} className="btn-primary text-sm">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            Set Up Two-Factor Authentication
          </button>
        </div>
      )}
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
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">Change Password</h2>
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
  const { mode, setMode } = useTheme()

  const options: { value: 'light' | 'dark'; label: string; icon: React.ElementType }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
  ]

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">Theme</h2>
      <div className="grid grid-cols-3 gap-3 max-w-md">
        {options.map(opt => (
          <button
            key={opt.value}
            onClick={() => setMode(opt.value)}
            className={`flex flex-col items-center gap-2 p-4 rounded-lg border transition-colors ${
              mode === opt.value
                ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30'
                : 'border-zinc-200 dark:border-slate-700/50 hover:border-zinc-300 dark:hover:border-slate-600'
            }`}
          >
            <opt.icon className={`w-5 h-5 ${mode === opt.value ? 'text-brand-500' : 'text-zinc-400'}`} />
            <span className="text-sm font-medium text-zinc-700 dark:text-slate-300">{opt.label}</span>
          </button>
        ))}
      </div>
      <p className="text-xs text-zinc-400 mt-3">Theme preference is saved locally.</p>
    </div>
  )
}

function SystemStatus() {
  const {
    isOnline,
    frontendHealthy,
    backendHealthy,
    databaseHealthy,
    toolsHealthy,
    toolVersions,
    lastChecked,
  } = useOnlineStatus()

  const toolLabels: Record<string, string> = {
    nmap: 'Nmap',
    testssl: 'testssl.sh',
    ssh_audit: 'ssh-audit',
    hydra: 'Hydra',
    nikto: 'Nikto',
    snmpwalk: 'snmpwalk',
  }

  // Strip ANSI escape codes from tool version strings
  const stripAnsi = (str: string) => str.replace(/\x1b\[[0-9;]*m/g, '').replace(/\u001b\[[0-9;]*m/g, '').replace(/\[[\d;]*m/g, '').trim()

  const serviceRows = [
    { label: 'Frontend UI', ok: frontendHealthy, detail: frontendHealthy ? 'Loaded in browser' : 'Unavailable' },
    { label: 'Backend API', ok: backendHealthy, detail: backendHealthy ? 'Connected' : 'Unavailable' },
    { label: 'Database', ok: databaseHealthy, detail: databaseHealthy ? 'Connected' : 'Unavailable' },
    { label: 'Tools Sidecar', ok: toolsHealthy, detail: toolsHealthy ? 'Connected' : 'Unavailable' },
  ]

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-zinc-900 dark:text-slate-100">System Status</h2>
        <span className={`badge border ${isOnline ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-800' : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-800'}`}>
          {isOnline ? 'Browser Online' : 'Browser Offline'}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-2">
          {serviceRows.map(({ label, ok, detail }) => (
            <div key={label} className="flex items-center gap-3 py-2.5 px-3 rounded-lg bg-zinc-50 dark:bg-slate-800">
              <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${ok ? 'bg-emerald-500' : 'bg-red-400'}`} />
              <span className="text-sm font-medium text-zinc-700 dark:text-slate-300 w-28">{label}</span>
              <span className={`text-xs flex-1 ${ok ? 'text-zinc-500 dark:text-slate-400' : 'text-red-600 dark:text-red-300'}`}>
                {detail}
              </span>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          {Object.entries(toolLabels).map(([key, label]) => {
            const version = toolVersions[key]
            const available = version && version !== 'unavailable'
            return (
              <div key={key} className="flex items-center gap-3 py-2.5 px-3 rounded-lg bg-zinc-50 dark:bg-slate-800">
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${available ? 'bg-emerald-500' : 'bg-red-400'}`} />
                <span className="text-sm font-medium text-zinc-700 dark:text-slate-300 w-24">{label}</span>
                <span className="text-xs text-zinc-500 dark:text-slate-400 flex-1 truncate font-mono">
                  {available ? stripAnsi(version) : 'Not available'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {lastChecked && (
        <p className="text-[11px] text-zinc-400 mt-3">
          Last checked: {lastChecked.toLocaleTimeString()}
        </p>
      )}
    </div>
  )
}

function BrandingSettings() {
  const [form, setForm] = useState({ company_name: '', primary_color: '#2563eb', footer_text: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [logoPreview, setLogoPreview] = useState<string | null>(null)

  useEffect(() => {
    brandingApi.get().then(res => {
      const d = res.data
      setForm({
        company_name: d.company_name || '',
        primary_color: d.primary_color || '#2563eb',
        footer_text: d.footer_text || '',
      })
      if (d.logo_path) setLogoPreview('/api/settings/branding/logo')
    }).catch((err) => { console.error('Failed to fetch branding settings:', err) }).finally(() => setLoading(false))
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await brandingApi.update(form)
      if (logoFile) {
        await brandingApi.uploadLogo(logoFile)
      }
      toast.success('Branding settings saved')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Failed to save branding')
    } finally {
      setSaving(false)
    }
  }

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg']
    if (!allowedTypes.includes(file.type)) {
      toast.error('Logo must be a PNG or JPEG image')
      e.target.value = ''
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Logo must be under 5MB')
      e.target.value = ''
      return
    }
    setLogoFile(file)
    setLogoPreview(URL.createObjectURL(file))
  }

  if (loading) {
    return (
      <div className="card p-5">
        <div className="py-6 text-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto" />
        </div>
      </div>
    )
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-1">Report Branding</h2>
      <p className="text-xs text-zinc-500 mb-4">Customize the look of generated qualification reports.</p>

      <form onSubmit={handleSave} className="space-y-4 max-w-md">
        <div>
          <label className="label">Company Name</label>
          <input
            type="text"
            value={form.company_name}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })}
            className="input"
            placeholder="Electracom"
          />
        </div>

        <div>
          <label className="label">Company Logo</label>
          <div className="flex items-center gap-3">
            {logoPreview && (
              <img src={logoPreview} alt="Logo preview" className="w-12 h-12 object-contain rounded border border-zinc-200 bg-zinc-50 p-1" />
            )}
            <label className="btn-secondary cursor-pointer text-sm py-1.5 px-3">
              <Upload className="w-3.5 h-3.5" />
              Upload Logo
              <input type="file" accept="image/*" onChange={handleLogoChange} className="hidden" />
            </label>
          </div>
          <p className="text-[11px] text-zinc-400 mt-1">PNG or JPEG, max 5MB. Used in report headers.</p>
        </div>

        <div>
          <label className="label">Brand Color</label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              className="w-10 h-10 rounded border border-zinc-200 cursor-pointer"
            />
            <input
              type="text"
              value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              className="input w-28 font-mono text-sm"
              placeholder="#2563eb"
            />
          </div>
        </div>

        <div>
          <label className="label">Report Footer Text</label>
          <textarea
            value={form.footer_text}
            onChange={(e) => setForm({ ...form, footer_text: e.target.value })}
            className="input min-h-[80px]"
            placeholder="Confidential — for internal use only"
          />
        </div>

        <button type="submit" disabled={saving} className="btn-primary">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Palette className="w-4 h-4" />}
          Save Branding
        </button>
      </form>
    </div>
  )
}

function HelpSection({ tourState }: { tourState?: TourState }) {
  const navigate = useNavigate()

  return (
    <div className="card p-5 mt-5">
      <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">Help</h2>
      <div className="space-y-3">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-brand-50 dark:bg-brand-950/30 flex items-center justify-center shrink-0">
            <RotateCcw className="w-4 h-4 text-brand-500 dark:text-brand-300" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-zinc-900 dark:text-slate-100 mb-0.5">Guided Tour</h3>
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
