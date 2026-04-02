import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

const mockAgentsList = vi.fn()
vi.mock('@/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  agentsApi: {
    list: () => mockAgentsList(),
  },
}))

import AgentsPage from '@/pages/AgentsPage'

const MOCK_AGENTS = [
  {
    id: 'a1',
    name: 'Dylan-MBP',
    hostname: 'dylans-mbp.local',
    api_key_prefix: 'edq_1234',
    platform: 'macos',
    agent_version: '1.0.0',
    ip_address: '192.168.1.10',
    status: 'online',
    last_heartbeat: new Date(Date.now() - 120_000).toISOString(),
    capabilities: null,
    current_task: null,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'a2',
    name: 'Sarah-Thinkpad',
    hostname: 'sarah-tp.local',
    api_key_prefix: 'edq_5678',
    platform: 'windows',
    agent_version: '1.0.0',
    ip_address: '192.168.1.11',
    status: 'busy',
    last_heartbeat: new Date(Date.now() - 5_000).toISOString(),
    capabilities: null,
    current_task: 'run-123',
    is_active: true,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'a3',
    name: 'Alex-Dell',
    hostname: 'alex-dell.local',
    api_key_prefix: 'edq_9abc',
    platform: 'windows',
    agent_version: '0.9.8',
    ip_address: '192.168.1.12',
    status: 'offline',
    last_heartbeat: new Date(Date.now() - 10_800_000).toISOString(),
    capabilities: null,
    current_task: null,
    is_active: true,
    created_at: '2026-01-03T00:00:00Z',
  },
]

function renderAgentsPage() {
  return render(
    <BrowserRouter>
      <AgentsPage />
    </BrowserRouter>
  )
}

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAgentsList.mockResolvedValue({ data: MOCK_AGENTS })
  })

  it('renders the page heading and subtitle', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText('Distributed Agents')).toBeInTheDocument()
    })
    expect(screen.getByText(/Optional fleet view for registered remote runner instances/)).toBeInTheDocument()
  })

  it('displays the info callout explaining the page', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/What is this page/)).toBeInTheDocument()
    })
    expect(screen.getByText(/not needed for the normal laptop-local workflow/i)).toBeInTheDocument()
  })

  it('shows loading state while fetching agents', () => {
    mockAgentsList.mockReturnValue(new Promise(() => {}))
    renderAgentsPage()

    expect(screen.getByText(/Loading agents/)).toBeInTheDocument()
  })

  it('shows an error state when the API fails', async () => {
    mockAgentsList.mockRejectedValue(new Error('Network error'))
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/Failed to load agents/i)).toBeInTheDocument()
    })
  })

  it('renders stats cards with correct counts from API data', async () => {
    renderAgentsPage()

    await waitFor(() => {
      const statValues = screen.getAllByTestId('stat-value')
      expect(statValues).toHaveLength(3)
    })

    expect(screen.getByText('Dylan-MBP')).toBeInTheDocument()
    expect(screen.getByText('Sarah-Thinkpad')).toBeInTheDocument()
    expect(screen.getByText('Alex-Dell')).toBeInTheDocument()
  })

  it('shows outdated version warning for agents not on latest version', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText('Alex-Dell')).toBeInTheDocument()
    })

    expect(screen.getByText(/0\.9\.8/)).toBeInTheDocument()
  })

  it('shows correct status labels for each agent', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText('Dylan-MBP')).toBeInTheDocument()
    })

    expect(screen.getAllByText('Online').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Scanning').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Offline').length).toBeGreaterThanOrEqual(1)
  })

  it('shows the empty state when no distributed agents are registered', async () => {
    mockAgentsList.mockResolvedValue({ data: [] })
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/No distributed agents registered/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/normal if engineers run EDQ locally/i)).toBeInTheDocument()
  })

  it('shows an error state when API returns 401', async () => {
    mockAgentsList.mockRejectedValue({ response: { status: 401 } })
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/Failed to load agents/i)).toBeInTheDocument()
    })
  })
})
