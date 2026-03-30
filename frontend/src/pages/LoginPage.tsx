import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import ThemeToggle from '@/components/common/ThemeToggle'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(username, password)
      toast.success('Welcome back!')
      navigate('/', { replace: true })
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface dark:bg-dark-bg pt-1">
      {/* Rainbow accent bar — full width fixed */}
      <div
        className="fixed top-0 left-0 right-0 z-[60] h-[3px]"
        style={{ background: 'linear-gradient(90deg, #0044ff, #00bfff, #00e676, #ffeb3b, #ff9800, #f44336, #e91e63)' }}
      />
      <div className="flex justify-end px-4 py-3">
        <ThemeToggle />
      </div>

      {/* Centered login card */}
      <div className="flex-1 flex items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm">
          <div className="flex flex-col items-center mb-8">
            <img src="/electracom-logo.png" alt="Electracom" className="h-20 mb-2" />
            <p className="text-sm text-zinc-500 dark:text-slate-400 mt-1.5">Device Qualifier</p>
          </div>

          <div className="card p-6">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100 mb-1">Sign in</h2>
            <p className="text-sm text-zinc-500 dark:text-slate-400 mb-6">Enter your credentials to continue</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="label">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input"
                  placeholder="Enter your username"
                  required
                  autoFocus
                />
              </div>

              <div>
                <label className="label">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input pr-10"
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          </div>

          <p className="mt-6 text-center text-xs text-zinc-400 dark:text-slate-500">
            Electracom Projects Ltd &mdash; A Sauter Group Company
          </p>
        </div>
      </div>
    </div>
  )
}
