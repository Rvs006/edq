import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import DeviceProfilesPage from '@/pages/DeviceProfilesPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: '1',
      username: 'admin',
      email: 'admin@example.com',
      full_name: 'Admin',
      role: 'admin',
      is_active: true,
    },
  }),
}))

vi.mock('@/lib/api', () => ({
  profilesApi: {
    list: vi.fn().mockResolvedValue({
      data: [
        {
          id: 'profile-1',
          name: 'EasyIO Controller',
          manufacturer: 'EasyIO',
          category: 'controller',
          description: 'Custom controller fingerprint',
          auto_generated: false,
          fingerprint_rules: {
            skip_test_ids: ['U35'],
          },
        },
      ],
    }),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DeviceProfilesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DeviceProfilesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders saved API profiles even when they are not auto-generated', async () => {
    renderWithProviders()

    expect(await screen.findByText('EasyIO Controller')).toBeInTheDocument()
    expect(screen.getByText('Custom controller fingerprint')).toBeInTheDocument()
  })
})
