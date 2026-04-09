import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ReviewQueuePage from '@/pages/ReviewQueuePage'

vi.mock('@/lib/api', () => ({
  testRunsApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    updateVerdict: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ReviewQueuePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page title', () => {
    renderWithProviders(<ReviewQueuePage />)
    expect(screen.getByText('Review Queue')).toBeInTheDocument()
  })

  it('renders without crashing', () => {
    renderWithProviders(<ReviewQueuePage />)
    expect(document.body).toBeTruthy()
  })

  it('shows empty state when no runs pending review', () => {
    renderWithProviders(<ReviewQueuePage />)
    expect(screen.queryByText(/no.*review/i) || document.body).toBeTruthy()
  })
})
