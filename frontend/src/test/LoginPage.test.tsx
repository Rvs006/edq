import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'

const mockLogin = vi.fn()

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/lib/api', () => ({
  authApi: {
    oidcConfig: vi.fn(),
    oidcCallback: vi.fn(),
  },
}))

import { useAuth } from '@/contexts/AuthContext'
import { authApi } from '@/lib/api'
import toast from 'react-hot-toast'
import LoginPage from '@/pages/LoginPage'

async function renderLoginPage() {
  const view = render(
    <BrowserRouter>
      <LoginPage />
    </BrowserRouter>
  )
  await waitFor(() => expect(authApi.oidcConfig).toHaveBeenCalled())
  return view
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    window.history.replaceState({}, '', '/login')
    vi.mocked(useAuth).mockReturnValue({
      login: mockLogin,
      isAuthenticated: false,
      loading: false,
      user: null,
      logout: vi.fn(),
      refreshUser: vi.fn(),
    })
    vi.mocked(authApi.oidcConfig).mockResolvedValue({ data: { enabled: false } })
  })

  it('renders the login form with all required elements', async () => {
    await renderLoginPage()

    expect(screen.getAllByAltText('Electracom').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Device Qualifier')).toBeInTheDocument()
    expect(screen.getByText('Sign in')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter your username or email')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter your password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows the password field as password type by default', async () => {
    await renderLoginPage()

    const passwordInput = screen.getByPlaceholderText('Enter your password')
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('toggles password visibility when eye icon is clicked', async () => {
    const user = userEvent.setup()
    await renderLoginPage()

    const passwordInput = screen.getByPlaceholderText('Enter your password')
    expect(passwordInput).toHaveAttribute('type', 'password')

    // Find and click the toggle button (the button inside the password field wrapper)
    const toggleButtons = screen.getAllByRole('button')
    const toggleButton = toggleButtons.find(btn => btn.getAttribute('type') === 'button')!
    await user.click(toggleButton)

    expect(passwordInput).toHaveAttribute('type', 'text')
  })

  it('calls login with credentials on form submit', async () => {
    mockLogin.mockResolvedValue(undefined)
    const user = userEvent.setup()
    await renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your username or email'), 'admin')
    await user.type(screen.getByPlaceholderText('Enter your password'), 'TestPass1!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(mockLogin).toHaveBeenCalledWith('admin', 'TestPass1!', undefined)
  })

  it('shows a network-specific error message when the backend is unreachable', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Network Error'))
    const user = userEvent.setup()
    await renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your username or email'), 'admin')
    await user.type(screen.getByPlaceholderText('Enter your password'), 'TestPass1!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Unable to reach the server. Check that EDQ is still running and try again.')
    })
  })

  it('shows Electracom branding in footer', async () => {
    await renderLoginPage()

    expect(screen.getByText(/Electracom Projects Ltd/)).toBeInTheDocument()
  })

  it('blocks OIDC login when the returned state does not match session state', async () => {
    sessionStorage.setItem('edq_oidc_state', 'expected-state')
    sessionStorage.setItem('edq_oidc_nonce', 'nonce-123')
    window.history.replaceState({}, '', '/login?code=code-123&state=wrong-state')

    await renderLoginPage()

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('SSO state validation failed')
    })
    expect(authApi.oidcCallback).not.toHaveBeenCalled()
  })

  it('sends nonce and PKCE verifier to the backend after validating state', async () => {
    sessionStorage.setItem('edq_oidc_state', 'expected-state')
    sessionStorage.setItem('edq_oidc_nonce', 'nonce-123')
    sessionStorage.setItem('edq_oidc_code_verifier', 'v'.repeat(43))
    window.history.replaceState({}, '', '/login?code=code-123&state=expected-state')
    vi.mocked(authApi.oidcCallback).mockResolvedValue({ data: {} })

    await renderLoginPage()

    await waitFor(() => {
      expect(authApi.oidcCallback).toHaveBeenCalledWith({
        code: 'code-123',
        redirect_uri: `${window.location.origin}/login`,
        nonce: 'nonce-123',
        code_verifier: 'v'.repeat(43),
      })
    })
  })
})
