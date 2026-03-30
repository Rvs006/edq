import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import ThemeToggle from '@/components/common/ThemeToggle'
import { ElectracomLogo } from '@/components/common/ElectracomLogo'
import {
  LayoutDashboard, Monitor, Play, FileText, Shield, ClipboardList,
  ListChecks, Settings, LogOut, Menu, X, ChevronDown, User,
  Bell, Search, Users, Eye, Network, Wifi, Activity, CalendarClock, Cpu, ShieldCheck
} from 'lucide-react'

const pageDescriptions: Record<string, string> = {
  '/': 'Overview of testing activity, recent sessions, and quick actions',
  '/devices': 'Register, discover, and manage all IP devices under test',
  '/device-profiles': 'Fingerprint rules that auto-identify device types and skip irrelevant tests',
  '/test-runs': 'Security qualification sessions — 43 checks per device (25 automated, 18 guided manual)',
  '/network-scan': 'Scan a subnet to discover and bulk-test multiple devices at once',
  '/templates': 'Define which tests to include and map results to report cells',
  '/test-plans': 'Saved test configurations that can be reused across devices',
  '/scan-schedules': 'Schedule recurring network scans to run automatically',
  '/whitelists': 'Approved port/protocol lists — open ports are checked against these',
  '/reports': 'Generate Excel, Word, or PDF qualification reports from completed test sessions',
  '/agents': 'Tools sidecar instances that execute security scans (nmap, testssl, hydra, etc.)',
  '/review': 'QA review queue — approve, override, or request retests on flagged results',
  '/admin': 'Manage user accounts, roles, and permissions',
  '/audit-log': 'Full history of actions — who did what and when',
  '/settings': 'Application preferences, theme, tool versions, and account settings',
  '/authorized-networks': 'Control which subnets EDQ is allowed to scan — all scan targets must fall within authorized ranges',
}

const navSections = [
  {
    label: 'Main',
    items: [
      { name: 'Dashboard', href: '/', icon: LayoutDashboard },
      { name: 'Devices', href: '/devices', icon: Monitor },
      { name: 'Device Profiles', href: '/device-profiles', icon: Cpu },
      { name: 'Test Runs', href: '/test-runs', icon: Play },
      { name: 'Network Scan', href: '/network-scan', icon: Network },
    ],
  },
  {
    label: 'Tools',
    items: [
      { name: 'Templates', href: '/templates', icon: FileText },
      { name: 'Test Plans', href: '/test-plans', icon: ListChecks },
      { name: 'Scan Schedules', href: '/scan-schedules', icon: CalendarClock },
      { name: 'Whitelists', href: '/whitelists', icon: Shield },
      { name: 'Reports', href: '/reports', icon: ClipboardList },
    ],
  },
  {
    label: 'System',
    items: [
      { name: 'Agents', href: '/agents', icon: Wifi },
    ],
  },
  {
    label: 'Admin',
    items: [
      { name: 'Review Queue', href: '/review', icon: Eye },
      { name: 'Users', href: '/admin', icon: Users },
      { name: 'Authorized Networks', href: '/authorized-networks', icon: ShieldCheck },
      { name: 'Audit Log', href: '/audit-log', icon: ListChecks },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [statusTooltipOpen, setStatusTooltipOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)
  const statusRef = useRef<HTMLDivElement>(null)
  const { user, logout } = useAuth()
  const location = useLocation()
  const { backendHealthy, toolsHealthy } = useOnlineStatus()
  const systemOk = backendHealthy && toolsHealthy

  // Close all dropdowns on route change
  useEffect(() => {
    setUserMenuOpen(false)
    setStatusTooltipOpen(false)
    setSidebarOpen(false)
  }, [location.pathname])

  // Close dropdowns on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) {
        setStatusTooltipOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close dropdowns on Escape key
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setUserMenuOpen(false)
        setStatusTooltipOpen(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  const isActive = (href: string) => {
    if (href === '/') return location.pathname === '/'
    return location.pathname.startsWith(href)
  }

  const pageTitle = (() => {
    for (const section of navSections) {
      for (const item of section.items) {
        if (isActive(item.href)) return item.name
      }
    }
    return 'EDQ'
  })()

  const pageDescription = (() => {
    for (const [path, desc] of Object.entries(pageDescriptions)) {
      if (path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)) return desc
    }
    return ''
  })()

  return (
    <div className="min-h-screen bg-surface dark:bg-dark-bg">
      {/* Rainbow accent bar — spans full width at the very top */}
      <div
        className="fixed top-0 left-0 right-0 z-[60] h-[3px] rainbow-bar"
      />

      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed top-1 inset-y-0 left-0 z-50 w-64 bg-white dark:bg-[#0f172a] flex flex-col transition-transform duration-200 lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <SidebarContent
          isActive={isActive}
          onClose={() => setSidebarOpen(false)}
          user={user}
          logout={logout}
        />
      </aside>

      <div className="lg:pl-64 flex flex-col min-h-screen pt-1">
        <header className="sticky top-1 z-20 bg-white dark:bg-dark-surface border-b border-zinc-200 dark:border-slate-700/50">
          <div className="flex items-center justify-between h-14 px-4 sm:px-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors"
                title="Open menu"
              >
                <Menu className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
              </button>
              <div className="min-w-0">
                <h1 className="text-base font-semibold text-zinc-900 dark:text-slate-100">{pageTitle}</h1>
                {pageDescription && (
                  <p className="text-[11px] text-zinc-400 dark:text-slate-500 truncate hidden sm:block">{pageDescription}</p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-2 bg-zinc-100 dark:bg-slate-800 rounded-lg px-3 py-1.5 w-56">
                <Search className="w-4 h-4 text-zinc-400" />
                <input
                  type="text"
                  placeholder="Search..."
                  className="bg-transparent text-sm text-zinc-700 dark:text-slate-200 placeholder-zinc-400 outline-none w-full"
                />
              </div>

              <div className="relative" ref={statusRef}>
                <button
                  onClick={() => setStatusTooltipOpen(!statusTooltipOpen)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    systemOk
                      ? 'bg-green-50 text-green-700 hover:bg-green-100'
                      : 'bg-red-50 text-red-700 hover:bg-red-100'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${
                    systemOk ? 'bg-green-500' : 'bg-red-500 animate-pulse'
                  }`} />
                  <span className="hidden sm:inline">{systemOk ? 'System OK' : 'Service Issue'}</span>
                  <Activity className="w-3 h-3 sm:hidden" />
                </button>
                {statusTooltipOpen && (
                  <>
                    <div className="absolute right-0 mt-1 w-56 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-zinc-200 dark:border-slate-700 p-3 z-50">
                      <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">System Status</p>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Backend API</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${backendHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${backendHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {backendHealthy ? 'Healthy' : 'Unavailable'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Tools Sidecar</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${toolsHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${toolsHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {toolsHealthy ? 'Healthy' : 'Unavailable'}
                          </span>
                        </div>
                      </div>
                      {!toolsHealthy && backendHealthy && (
                        <p className="text-[11px] text-amber-600 mt-2 leading-tight">
                          Security tools sidecar is unreachable. Automated tests will not run.
                        </p>
                      )}
                      {!backendHealthy && (
                        <p className="text-[11px] text-red-600 mt-2 leading-tight">
                          Backend service unavailable. Check that Docker services are running.
                        </p>
                      )}
                    </div>
                  </>
                )}
              </div>

              <ThemeToggle />

              <button className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors relative" title="Notifications">
                <Bell className="w-5 h-5 text-zinc-500" />
              </button>

              <div className="relative" ref={userMenuRef}>
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 transition-colors"
                  title="Account menu"
                >
                  <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center">
                    <span className="text-xs font-semibold text-white">
                      {user?.full_name?.[0] || user?.username?.[0] || 'U'}
                    </span>
                  </div>
                  <span className="hidden sm:block text-sm font-medium text-zinc-700 dark:text-slate-200">
                    {user?.full_name || user?.username}
                  </span>
                  <ChevronDown className="w-4 h-4 text-zinc-400 hidden sm:block" />
                </button>

                {userMenuOpen && (
                  <>
                    <div className="absolute right-0 mt-1 w-48 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-zinc-200 dark:border-slate-700 py-1 z-50">
                      <div className="px-3 py-2 border-b border-zinc-100 dark:border-slate-700">
                        <p className="text-sm font-medium text-zinc-900 dark:text-slate-100">{user?.username}</p>
                        <p className="text-xs text-zinc-500 capitalize">{user?.role}</p>
                      </div>
                      <Link
                        to="/settings"
                        className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-700 dark:text-slate-300 hover:bg-zinc-50 dark:hover:bg-slate-700"
                        onClick={() => setUserMenuOpen(false)}
                      >
                        <Settings className="w-4 h-4" /> Settings
                      </Link>
                      <button
                        onClick={() => { logout(); setUserMenuOpen(false) }}
                        className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 w-full text-left"
                      >
                        <LogOut className="w-4 h-4" /> Sign Out
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1">
          {children}
        </main>
      </div>
    </div>
  )
}

function SidebarContent({
  isActive,
  onClose,
  user,
  logout,
}: {
  isActive: (href: string) => boolean
  onClose?: () => void
  user: { full_name?: string | null; username?: string; role?: string } | null
  logout: () => void
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-slate-800">
        <Link to="/" className="flex items-center gap-2.5" onClick={onClose}>
          <img src="/icon-white.png" alt="" className="h-[58px] w-auto shrink-0 hidden dark:block" />
          <img src="/icon-white.png" alt="" className="h-[58px] w-auto shrink-0 dark:hidden" style={{ filter: 'brightness(0)' }} />
          <ElectracomLogo size="md" />
        </Link>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 lg:hidden" title="Close menu">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.label} className="mb-4">
            <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = isActive(item.href)
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    onClick={onClose}
                    className={`relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? 'bg-zinc-100 text-zinc-900 dark:bg-slate-800 dark:text-white'
                        : 'text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200'
                    }`}
                  >
                    {active && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-blue-400" />
                    )}
                    <item.icon className={`w-[18px] h-[18px] shrink-0 ${active ? 'text-blue-400' : ''}`} />
                    {item.name}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-3 py-3 border-t border-zinc-200 dark:border-slate-800">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-slate-700 flex items-center justify-center">
            <User className="w-4 h-4 text-zinc-500 dark:text-slate-300" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-zinc-900 dark:text-white truncate">{user?.full_name || user?.username}</p>
            <p className="text-xs text-zinc-400 dark:text-slate-500 capitalize">{user?.role}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
