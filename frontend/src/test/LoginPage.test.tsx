import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'

// Mock AuthContext
const mockLogin = vi.fn()
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: mockLogin,
    isAuthenticated: false,
    loading: false,
    user: null,
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

// Mock react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import LoginPage from '@/pages/LoginPage'

function renderLoginPage() {
  return render(
    <BrowserRouter>
      <LoginPage />
    </BrowserRouter>
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the login form with all required elements', () => {
    renderLoginPage()

    expect(screen.getByText('Electracom')).toBeInTheDocument()
    expect(screen.getByText('Device Qualifier')).toBeInTheDocument()
    expect(screen.getByText('Sign in')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter your username')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter your password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows the password field as password type by default', () => {
    renderLoginPage()

    const passwordInput = screen.getByPlaceholderText('Enter your password')
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('toggles password visibility when eye icon is clicked', async () => {
    const user = userEvent.setup()
    renderLoginPage()

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
    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your username'), 'admin')
    await user.type(screen.getByPlaceholderText('Enter your password'), 'Admin123!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(mockLogin).toHaveBeenCalledWith('admin', 'Admin123!')
  })

  it('shows Electracom branding in footer', () => {
    renderLoginPage()

    expect(screen.getByText(/Electracom Projects Ltd/)).toBeInTheDocument()
  })
})
