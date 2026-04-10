import { useState, useEffect, useRef, useMemo } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import ThemeToggle from '@/components/common/ThemeToggle'
import { ElectracomLogo } from '@/components/common/ElectracomLogo'
import {
  LayoutDashboard, Monitor, Play, FileText, Shield, ClipboardList,
  ListChecks, Settings, LogOut, Menu, X, ChevronDown, User,
  Bell, Search, Users, Eye, Network, Activity, CalendarClock, Cpu, ShieldCheck,
  FolderOpen
} from 'lucide-react'

const pageDescriptions: Record<string, string> = {
  '/': 'Overview of testing activity, recent sessions, and quick actions',
  '/projects': 'Organize devices and test runs into project folders',
  '/devices': 'Register, discover, and manage all IP devices under test',
  '/devices/compare': 'Compare up to five devices side by side across attributes and recent outcomes',
  '/device-profiles': 'Fingerprint rules that auto-identify device types and skip irrelevant tests',
  '/test-runs': 'Security qualification sessions - 43 checks per device (29 automated, 14 guided manual)',
  '/network-scan': 'Bulk discovery for unknown IPs and multi-device subnet surveys',
  '/templates': 'Define which tests to include and map results to report cells',
  '/test-plans': 'Saved test configurations that can be reused across devices',
  '/scan-schedules': 'Schedule recurring network scans to run automatically',
  '/whitelists': 'Approved port/protocol lists — open ports are checked against these',
  '/reports': 'Generate Excel, Word, PDF, or CSV qualification reports from completed test sessions',
  '/agents': 'Optional distributed runner registrations. Normal local-laptop use does not need this page.',
  '/review': 'QA review queue — approve, override, or request retests on flagged results',
  '/admin': 'Manage user accounts, roles, and permissions',
  '/audit-log': 'Full history of actions — who did what and when',
  '/settings': 'Application preferences, theme, tool versions, and account settings',
  '/authorized-networks': 'Control which subnets EDQ is allowed to scan — all scan targets must fall within authorized ranges',
}

type NavItem = { name: string; href: string; icon: React.ComponentType<{ className?: string }> }
type NavSection = { label: string; items: NavItem[]; collapsed?: boolean }

function getNavSections(role?: string): NavSection[] {
  const isAdmin = role === 'admin'
  const isReviewer = role === 'reviewer' || isAdmin

  const sections: NavSection[] = [
    {
      label: 'Workflow',
      items: [
        { name: 'Dashboard', href: '/', icon: LayoutDashboard },
        { name: 'Projects', href: '/projects', icon: FolderOpen },
        { name: 'Devices', href: '/devices', icon: Monitor },
        { name: 'Bulk Discovery', href: '/network-scan', icon: Network },
        { name: 'Test Runs', href: '/test-runs', icon: Play },
        { name: 'Reports', href: '/reports', icon: ClipboardList },
      ],
    },
    {
      label: 'Setup',
      collapsed: true,
      items: [
        { name: 'Device Profiles', href: '/device-profiles', icon: Cpu },
        { name: 'Templates', href: '/templates', icon: FileText },
        { name: 'Test Plans', href: '/test-plans', icon: ListChecks },
        { name: 'Scan Schedules', href: '/scan-schedules', icon: CalendarClock },
        { name: 'Whitelists', href: '/whitelists', icon: Shield },
        { name: 'Authorized Networks', href: '/authorized-networks', icon: ShieldCheck },
      ],
    },
  ]

  if (isReviewer) {
    sections.push({
      label: 'Review',
      items: [
        { name: 'Review Queue', href: '/review', icon: Eye },
        { name: 'Audit Log', href: '/audit-log', icon: ListChecks },
      ],
    })
  }

  if (isAdmin) {
    sections.push({
      label: 'Admin',
      collapsed: true,
      items: [
        { name: 'Users', href: '/admin', icon: Users },
      ],
    })
  }

  sections.push({
    label: 'Account',
    items: [
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  })

  return sections
}

const hiddenPageTitles: Record<string, string> = {
  '/devices/compare': 'Device Comparison',
  '/agents': 'Distributed Agents',
  '/projects': 'Projects',
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [statusTooltipOpen, setStatusTooltipOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const userMenuRef = useRef<HTMLDivElement>(null)
  const statusRef = useRef<HTMLDivElement>(null)
  const mobileSidebarRef = useRef<HTMLElement>(null)
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const {
    frontendHealthy,
    backendHealthy,
    databaseHealthy,
    toolsHealthy,
    lastChecked,
  } = useOnlineStatus()
  const systemOk = frontendHealthy && backendHealthy && databaseHealthy && toolsHealthy

  const sections = useMemo(() => getNavSections(user?.role), [user?.role])

  useEffect(() => {
    setUserMenuOpen(false)
    setStatusTooltipOpen(false)
    setSidebarOpen(false)
  }, [location.pathname])

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

  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setUserMenuOpen(false)
        setStatusTooltipOpen(false)
        setSidebarOpen(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  useEffect(() => {
    if (sidebarOpen) {
      mobileSidebarRef.current?.focus()
    }
  }, [sidebarOpen])

  // Update browser tab title
  useEffect(() => {
    const titleMap: Record<string, string> = {
      '/': 'Dashboard',
      '/login': 'Login',
      '/projects': 'Projects',
      '/devices': 'Devices',
      '/devices/compare': 'Device Comparison',
      '/test-runs': 'Test Runs',
      '/reports': 'Reports',
      '/admin': 'Administration',
      '/audit-log': 'Audit Log',
      '/settings': 'Settings',
      '/network-scan': 'Bulk Discovery',
      '/templates': 'Templates',
      '/test-plans': 'Test Plans',
      '/whitelists': 'Whitelists',
      '/review': 'Review Queue',
      '/scan-schedules': 'Scan Schedules',
      '/device-profiles': 'Device Profiles',
      '/agents': 'Agents',
      '/authorized-networks': 'Authorized Networks',
    }
    const match = Object.entries(titleMap)
      .sort((left, right) => right[0].length - left[0].length)
      .find(([path]) => (path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)))
    document.title = match ? `${match[1]} | EDQ` : 'EDQ'
  }, [location.pathname])

  const isActive = (href: string) => {
    if (href === '/') return location.pathname === '/'
    return location.pathname.startsWith(href)
  }

  const getBestMatch = (entries: [string, string][]) =>
    entries
      .sort((left, right) => right[0].length - left[0].length)
      .find(([path]) => (path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)))

  const pageTitle = (() => {
    const hiddenMatch = getBestMatch(Object.entries(hiddenPageTitles))
    if (hiddenMatch) return hiddenMatch[1]
    for (const section of sections) {
      for (const item of section.items) {
        if (isActive(item.href)) return item.name
      }
    }
    return 'EDQ'
  })()

  const pageDescription = (() => {
    const match = getBestMatch(Object.entries(pageDescriptions))
    if (match) return match[1]
    return ''
  })()

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/devices?search=${encodeURIComponent(searchQuery.trim())}`)
      setSearchQuery('')
    }
  }

  return (
    <div className="min-h-screen bg-surface dark:bg-dark-bg">
      <div
        className="fixed top-0 left-0 right-0 z-[60] h-[3px] rainbow-bar"
      />

      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
          <aside
            id="mobile-navigation"
            ref={mobileSidebarRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
            tabIndex={-1}
            className="fixed top-[3px] inset-y-0 left-0 z-50 w-64 bg-white dark:bg-[#0f172a] flex flex-col lg:hidden"
          >
            <SidebarContent
              isActive={isActive}
              onClose={() => setSidebarOpen(false)}
              user={user}
              logout={logout}
              sections={sections}
            />
          </aside>
        </>
      )}
      <aside className="hidden lg:flex fixed top-[3px] inset-y-0 left-0 z-50 w-64 bg-white dark:bg-[#0f172a] flex-col">
        <SidebarContent
          isActive={isActive}
          user={user}
          logout={logout}
          sections={sections}
        />
      </aside>

      <div className="lg:pl-64 flex flex-col min-h-screen pt-[3px]">
        <header className="sticky top-[3px] z-20 bg-white dark:bg-dark-surface border-b border-zinc-200 dark:border-slate-700/50">
          <div className="flex items-center justify-between h-14 px-4 sm:px-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                aria-expanded={sidebarOpen}
                aria-controls="mobile-navigation"
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
                  placeholder="Search devices..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleSearch}
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
                    <div className="absolute right-0 mt-1 w-72 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-zinc-200 dark:border-slate-700 p-3 z-50">
                      <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">System Status</p>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Frontend UI</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${frontendHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${frontendHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {frontendHealthy ? 'Loaded' : 'Unavailable'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Backend API</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${backendHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${backendHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {backendHealthy ? 'Healthy' : 'Unavailable'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Database</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${databaseHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${databaseHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {databaseHealthy ? 'Healthy' : 'Unavailable'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-zinc-700 dark:text-slate-300">Security Tools</span>
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${toolsHealthy ? 'text-green-600' : 'text-red-600'}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${toolsHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                            {toolsHealthy ? 'Healthy' : 'Unavailable'}
                          </span>
                        </div>
                      </div>
                      {lastChecked && (
                        <p className="text-[11px] text-zinc-400 dark:text-slate-500 mt-2">
                          Last checked: {lastChecked.toLocaleTimeString()}
                        </p>
                      )}
                      {!toolsHealthy && backendHealthy && (
                        <p className="text-[11px] text-amber-600 mt-2 leading-tight">
                          Security tools are unreachable. Automated tests will not run.
                        </p>
                      )}
                      {!backendHealthy && (
                        <p className="text-[11px] text-red-600 mt-2 leading-tight">
                          Backend service unavailable. Check that Docker services are running.
                        </p>
                      )}
                      {backendHealthy && !databaseHealthy && (
                        <p className="text-[11px] text-red-600 mt-2 leading-tight">
                          The backend is reachable, but the database is unavailable.
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

        <main id="main-content" tabIndex={-1} className="flex-1">
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
  sections,
}: {
  isActive: (href: string) => boolean
  onClose?: () => void
  user: { full_name?: string | null; username?: string; role?: string } | null
  logout: () => void
  sections: NavSection[]
}) {
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    sections.forEach((section) => {
      if (section.collapsed && !section.items.some((item) => isActive(item.href))) {
        initial.add(section.label)
      }
    })
    return initial
  })

  useEffect(() => {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      sections.forEach((section) => {
        if (section.items.some((item) => isActive(item.href))) {
          next.delete(section.label)
        }
      })
      return next
    })
  }, [isActive, sections])

  const toggleSection = (label: string) => {
    setCollapsedSections(prev => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 min-h-[84px] border-b border-zinc-200 dark:border-slate-700/50">
        <Link to="/" className="py-3" onClick={onClose}>
          <ElectracomLogo size="md" />
        </Link>
        {onClose && (
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-800 lg:hidden min-w-[44px] min-h-[44px] flex items-center justify-center" title="Close menu">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.label} className="mb-4">
            {section.items.length > 1 ? (
              <button
                type="button"
                onClick={() => toggleSection(section.label)}
                aria-expanded={!collapsedSections.has(section.label)}
                aria-controls={`nav-section-${section.label}`}
                className="flex items-center justify-between w-full px-3 mb-1.5 group"
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                  {section.label}
                </p>
                <ChevronDown className={`w-3 h-3 text-zinc-400 transition-transform ${
                  collapsedSections.has(section.label) ? '-rotate-90' : ''
                }`} />
              </button>
            ) : (
              <div className="flex items-center justify-between w-full px-3 mb-1.5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                  {section.label}
                </p>
              </div>
            )}
            {!collapsedSections.has(section.label) && (
              <div id={`nav-section-${section.label}`} className="space-y-0.5">
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
            )}
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
