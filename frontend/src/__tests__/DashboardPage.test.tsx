import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from '@/pages/DashboardPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'admin', full_name: 'Admin User', role: 'admin' },
  }),
}))

vi.mock('@/lib/api', () => ({
  devicesApi: {
    stats: vi.fn(),
  },
  testRunsApi: {
    stats: vi.fn(),
    list: vi.fn(),
  },
}))

import { devicesApi, testRunsApi } from '@/lib/api'

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(devicesApi.stats).mockResolvedValue({
      data: { total: 534, by_category: {} },
    } as Awaited<ReturnType<typeof devicesApi.stats>>)
    vi.mocked(testRunsApi.stats).mockResolvedValue({
      data: {
        by_status: { completed: 0 },
        by_verdict: {},
        completed_this_week: 0,
      },
    } as Awaited<ReturnType<typeof testRunsApi.stats>>)
    vi.mocked(testRunsApi.list).mockResolvedValue({ data: [] } as Awaited<ReturnType<typeof testRunsApi.list>>)
  })

  it('shows a numeric zero pass rate when no completed verdicts exist', async () => {
    renderWithProviders(<DashboardPage />)

    expect(await screen.findByText('Pass Rate')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('surfaces setup shortcuts before quick actions', () => {
    renderWithProviders(<DashboardPage />)

    const setupHeading = screen.getByRole('heading', { name: 'Setup' })
    const quickActionsHeading = screen.getByRole('heading', { name: 'Quick Actions' })

    expect(
      setupHeading.compareDocumentPosition(quickActionsHeading)
      & globalThis.Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(screen.getByRole('link', { name: /Authorize scan ranges/i })).toHaveAttribute('href', '/authorized-networks')
    expect(screen.getByRole('link', { name: /Tune device profiles/i })).toHaveAttribute('href', '/device-profiles')
    expect(screen.getByRole('link', { name: /Review templates/i })).toHaveAttribute('href', '/templates')
    expect(screen.getByRole('link', { name: /Save test plans/i })).toHaveAttribute('href', '/test-plans')
  })
})
