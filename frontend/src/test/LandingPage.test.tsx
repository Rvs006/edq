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

    expect(screen.getByText('EDQ — Device Qualifier')).toBeInTheDocument()
  })

  it('displays the capability cards', () => {
    renderLandingPage()

    expect(screen.getByText('Device Discovery')).toBeInTheDocument()
    expect(screen.getByText('Automated Security Scans')).toBeInTheDocument()
    expect(screen.getByText('Guided Manual Tests')).toBeInTheDocument()
    expect(screen.getByText('Report Generation')).toBeInTheDocument()
    expect(screen.getByText('Tools Sidecar')).toBeInTheDocument()
    expect(screen.getByText('Review & Audit')).toBeInTheDocument()
  })

  it('displays the workflow steps', () => {
    renderLandingPage()

    expect(screen.getByText(/Register or discover device/)).toBeInTheDocument()
    expect(screen.getByText(/Create test run/)).toBeInTheDocument()
    expect(screen.getByText(/Complete manual checks/)).toBeInTheDocument()
    expect(screen.getByText(/Generate report/)).toBeInTheDocument()
  })

  it('has a Sign In link that navigates to /login', () => {
    renderLandingPage()

    const signInLinks = screen.getAllByText('Sign In')
    expect(signInLinks.length).toBeGreaterThanOrEqual(1)

    const headerLink = signInLinks[0].closest('a')
    expect(headerLink).toHaveAttribute('href', '/login')
  })

  it('lists the security tools', () => {
    renderLandingPage()

    expect(screen.getByText('nmap')).toBeInTheDocument()
    expect(screen.getByText('testssl.sh')).toBeInTheDocument()
    expect(screen.getByText('ssh-audit')).toBeInTheDocument()
    expect(screen.getByText('hydra')).toBeInTheDocument()
    expect(screen.getByText('snmpwalk')).toBeInTheDocument()
    expect(screen.getByText('nikto')).toBeInTheDocument()
  })

  it('shows What EDQ Does section', () => {
    renderLandingPage()

    expect(screen.getByText('What EDQ Does')).toBeInTheDocument()
    expect(screen.getByText(/60 tests \(29 automated \+ 31 guided manual\)/)).toBeInTheDocument()
    expect(screen.getByText(/Export Excel, Word, and PDF reports/)).toBeInTheDocument()
  })

  it('shows the workflow section', () => {
    renderLandingPage()

    expect(screen.getByText('Workflow')).toBeInTheDocument()
    expect(screen.getByText('Security Tools')).toBeInTheDocument()
  })

  it('shows the practical usage guide', () => {
    renderLandingPage()

    expect(screen.getByText('How to use EDQ effectively')).toBeInTheDocument()
    expect(screen.getByText(/If the device uses DHCP, register its MAC address/)).toBeInTheDocument()
    expect(screen.getByText(/Open the explainer first/)).toBeInTheDocument()
  })

  it('displays the footer with Electracom branding', () => {
    renderLandingPage()

    expect(screen.getAllByAltText('Electracom').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Electracom Projects Ltd/)).toBeInTheDocument()
    expect(screen.getByText(/Internal Use Only/)).toBeInTheDocument()
  })
})
