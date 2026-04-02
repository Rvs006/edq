import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { authApi } from '@/lib/api'
import { Eye, EyeOff, Loader2, Shield, ExternalLink } from 'lucide-react'
import ThemeToggle from '@/components/common/ThemeToggle'
import { ElectracomLogo } from '@/components/common/ElectracomLogo'
import toast from 'react-hot-toast'

const OIDC_STATE_KEY = 'edq_oidc_state'
const OIDC_NONCE_KEY = 'edq_oidc_nonce'
const OIDC_CODE_VERIFIER_KEY = 'edq_oidc_code_verifier'

function clearOidcSession() {
  sessionStorage.removeItem(OIDC_STATE_KEY)
  sessionStorage.removeItem(OIDC_NONCE_KEY)
  sessionStorage.removeItem(OIDC_CODE_VERIFIER_KEY)
}

function base64UrlEncode(bytes: Uint8Array) {
  const bin = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('')
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function randomUrlSafe(size = 32) {
  const bytes = new Uint8Array(size)
  crypto.getRandomValues(bytes)
  return base64UrlEncode(bytes)
}

async function createPkceChallenge(verifier: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return base64UrlEncode(new Uint8Array(digest))
}

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [requires2FA, setRequires2FA] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const oidcHandledRef = useRef(false)

  // OIDC config
  const [oidcConfig, setOidcConfig] = useState<{
    enabled: boolean
    provider?: string
    client_id?: string
    authorization_endpoint?: string
  } | null>(null)

  useEffect(() => {
    authApi.oidcConfig().then(res => setOidcConfig(res.data)).catch(() => {})
  }, [])

  // Handle OIDC callback
  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')
    if (error && !oidcHandledRef.current) {
      oidcHandledRef.current = true
      clearOidcSession()
      toast.error(searchParams.get('error_description') || 'SSO login failed')
      navigate('/login', { replace: true })
      return
    }
    if (code && state && !oidcHandledRef.current) {
      oidcHandledRef.current = true
      void handleOIDCCallback(code, state)
    }
  }, [navigate, searchParams])

  const handleOIDCCallback = async (code: string, state: string) => {
    const expectedState = sessionStorage.getItem(OIDC_STATE_KEY)
    const expectedNonce = sessionStorage.getItem(OIDC_NONCE_KEY)
    const codeVerifier = sessionStorage.getItem(OIDC_CODE_VERIFIER_KEY)

    if (!expectedState || expectedState !== state) {
      clearOidcSession()
      toast.error('SSO state validation failed')
      navigate('/login', { replace: true })
      return
    }

    if (!expectedNonce) {
      clearOidcSession()
      toast.error('SSO nonce is missing or expired')
      navigate('/login', { replace: true })
      return
    }

    setLoading(true)
    try {
      const res = await authApi.oidcCallback({
        code,
        redirect_uri: `${window.location.origin}/login`,
        nonce: expectedNonce,
        code_verifier: codeVerifier || undefined,
      })
      if (res.data.user) {
        clearOidcSession()
        toast.success('Welcome!')
        window.location.href = '/'
      }
    } catch (err: unknown) {
      clearOidcSession()
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'SSO login failed')
      navigate('/login', { replace: true })
    } finally {
      setLoading(false)
    }
  }

  const handleSSO = async () => {
    if (!oidcConfig?.authorization_endpoint || !oidcConfig.client_id) return
    try {
      const state = randomUrlSafe(32)
      const nonce = randomUrlSafe(32)
      const codeVerifier = randomUrlSafe(64)
      const codeChallenge = await createPkceChallenge(codeVerifier)

      sessionStorage.setItem(OIDC_STATE_KEY, state)
      sessionStorage.setItem(OIDC_NONCE_KEY, nonce)
      sessionStorage.setItem(OIDC_CODE_VERIFIER_KEY, codeVerifier)

      const params = new URLSearchParams({
        response_type: 'code',
        client_id: oidcConfig.client_id,
        redirect_uri: `${window.location.origin}/login`,
        scope: 'openid email profile',
        state,
        nonce,
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
      })
      window.location.href = `${oidcConfig.authorization_endpoint}?${params}`
    } catch {
      clearOidcSession()
      toast.error('Unable to start SSO login')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const result = await login(username, password, requires2FA ? totpCode : undefined)

      // Check if server requires 2FA
      if (result?.requires_2fa) {
        setRequires2FA(true)
        setLoading(false)
        return
      }

      clearOidcSession()
      toast.success('Welcome back!')
      navigate('/', { replace: true })
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Invalid credentials')
      if (requires2FA) setTotpCode('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface dark:bg-dark-bg pt-1">
      {/* Rainbow accent bar — full width fixed */}
      <div
        className="fixed top-0 left-0 right-0 z-[60] h-[3px] rainbow-bar"
      />
      <div className="flex justify-end px-4 py-3">
        <ThemeToggle />
      </div>

      {/* Centered login card */}
      <div className="flex-1 flex items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm">
          <div className="flex flex-col items-center mb-8">
            <ElectracomLogo size="lg" />
          </div>

          <div className="card p-6">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100 mb-1">Sign in</h2>
            <p className="text-sm text-zinc-500 dark:text-slate-400 mb-6">
              {requires2FA ? 'Enter your authentication code' : 'Enter your credentials to continue'}
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              {!requires2FA ? (
                <>
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
                </>
              ) : (
                <div>
                  <div className="flex items-center gap-2 mb-3 text-brand-500">
                    <Shield className="w-5 h-5" />
                    <span className="text-sm font-medium">Two-Factor Authentication</span>
                  </div>
                  <label className="label">Authentication Code</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                    className="input text-center text-2xl tracking-[0.5em] font-mono"
                    placeholder="000000"
                    required
                    autoFocus
                    autoComplete="one-time-code"
                  />
                  <p className="text-xs text-zinc-400 mt-2">
                    Enter the 6-digit code from your authenticator app
                  </p>
                  <button
                    type="button"
                    onClick={() => { setRequires2FA(false); setTotpCode('') }}
                    className="text-xs text-brand-500 hover:text-brand-600 mt-2"
                  >
                    Back to login
                  </button>
                </div>
              )}

              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Signing in...' : requires2FA ? 'Verify & Sign In' : 'Sign In'}
              </button>
            </form>

            {/* SSO / OIDC login */}
            {oidcConfig?.enabled && !requires2FA && (
              <>
                <div className="flex items-center gap-3 my-5">
                  <div className="flex-1 border-t border-zinc-200 dark:border-slate-700" />
                  <span className="text-xs text-zinc-400">or</span>
                  <div className="flex-1 border-t border-zinc-200 dark:border-slate-700" />
                </div>

                <button
                  type="button"
                  onClick={handleSSO}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-zinc-200 dark:border-slate-700 text-sm font-medium text-zinc-700 dark:text-slate-300 hover:bg-zinc-50 dark:hover:bg-slate-800 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  Sign in with {oidcConfig.provider === 'google' ? 'Google' : oidcConfig.provider === 'microsoft' ? 'Microsoft' : 'SSO'}
                </button>
              </>
            )}
          </div>

          <p className="mt-6 text-center text-xs text-zinc-400 dark:text-slate-500">
            Electracom Projects Ltd &mdash; A Sauter Group Company
          </p>
        </div>
      </div>
    </div>
  )
}
