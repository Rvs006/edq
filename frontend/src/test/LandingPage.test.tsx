import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import LandingPage from '@/pages/LandingPage'

function renderLandingPage() {
  return render(
    <BrowserRouter>
      <LandingPage />
    </BrowserRouter>
  )
}

describe('LandingPage', () => {
  it('renders the main heading', () => {
    renderLandingPage()

    expect(screen.getByText('Automated Security')).toBeInTheDocument()
    expect(screen.getByText(/Smart Building Devices/)).toBeInTheDocument()
  })

  it('displays the four stat cards', () => {
    renderLandingPage()

    expect(screen.getByText('43')).toBeInTheDocument()
    expect(screen.getByText('Security Tests')).toBeInTheDocument()
    expect(screen.getByText('60%')).toBeInTheDocument()
    expect(screen.getByText('Automated')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Report Formats')).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('displays the four workflow steps', () => {
    renderLandingPage()

    expect(screen.getByText('Connect Device')).toBeInTheDocument()
    expect(screen.getByText('Run Automated Scans')).toBeInTheDocument()
    expect(screen.getByText('Complete Manual Checks')).toBeInTheDocument()
    expect(screen.getByText('Generate Reports')).toBeInTheDocument()
  })

  it('has a Sign In link that navigates to /login', () => {
    renderLandingPage()

    const signInLinks = screen.getAllByText('Sign In')
    expect(signInLinks.length).toBeGreaterThanOrEqual(1)

    const headerLink = signInLinks[0].closest('a')
    expect(headerLink).toHaveAttribute('href', '/login')
  })

  it('has a Get Started link that navigates to /login', () => {
    renderLandingPage()

    const getStartedLink = screen.getByText('Get Started').closest('a')
    expect(getStartedLink).toHaveAttribute('href', '/login')
  })

  it('displays feature highlights section', () => {
    renderLandingPage()

    expect(screen.getByText('Fully Offline')).toBeInTheDocument()
    expect(screen.getByText('Saves 6+ Hours')).toBeInTheDocument()
    expect(screen.getByText('Client-Ready Reports')).toBeInTheDocument()
  })

  it('shows the How It Works section', () => {
    renderLandingPage()

    expect(screen.getByText('How It Works')).toBeInTheDocument()
    expect(screen.getByText('Four simple steps to qualify any IP device on your network')).toBeInTheDocument()
  })

  it('displays the footer with Electracom branding', () => {
    renderLandingPage()

    expect(screen.getAllByText('Electracom').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Electracom Projects Ltd/)).toBeInTheDocument()
  })
})
