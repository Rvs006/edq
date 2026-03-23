import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import {
  LayoutDashboard, Monitor, Play, FileText, Shield, ClipboardList,
  ListChecks, Settings, LogOut, Menu, X, ChevronDown, User,
  Bell, Search, Users, Eye, Network
} from 'lucide-react'

const navSections = [
  {
    label: 'Main',
    items: [
      { name: 'Dashboard', href: '/', icon: LayoutDashboard },
      { name: 'Devices', href: '/devices', icon: Monitor },
      { name: 'Test Runs', href: '/test-runs', icon: Play },
      { name: 'Network Scan', href: '/network-scan', icon: Network },
    ],
  },
  {
    label: 'Tools',
    items: [
      { name: 'Templates', href: '/templates', icon: FileText },
      { name: 'Whitelists', href: '/whitelists', icon: Shield },
      { name: 'Reports', href: '/reports', icon: ClipboardList },
    ],
  },
  {
    label: 'Admin',
    items: [
      { name: 'Review Queue', href: '/review', icon: Eye },
      { name: 'Users', href: '/admin', icon: Users },
      { name: 'Audit Log', href: '/audit-log', icon: ListChecks },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const { user, logout } = useAuth()
  const location = useLocation()

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

  return (
    <div className="min-h-screen bg-surface">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-zinc-900 flex flex-col transition-transform duration-200 lg:translate-x-0 ${
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

      <div className="lg:pl-64 flex flex-col min-h-screen">
        <header className="sticky top-0 z-20 bg-white border-b border-zinc-200">
          <div className="flex items-center justify-between h-14 px-4 sm:px-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-1.5 rounded-lg hover:bg-zinc-100 transition-colors"
              >
                <Menu className="w-5 h-5 text-zinc-600" />
              </button>
              <h1 className="text-base font-semibold text-zinc-900">{pageTitle}</h1>
            </div>

            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-2 bg-zinc-100 rounded-lg px-3 py-1.5 w-56">
                <Search className="w-4 h-4 text-zinc-400" />
                <input
                  type="text"
                  placeholder="Search..."
                  className="bg-transparent text-sm text-zinc-700 placeholder-zinc-400 outline-none w-full"
                />
              </div>

              <button className="p-2 rounded-lg hover:bg-zinc-100 transition-colors relative">
                <Bell className="w-5 h-5 text-zinc-500" />
              </button>

              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-zinc-100 transition-colors"
                >
                  <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center">
                    <span className="text-xs font-semibold text-white">
                      {user?.full_name?.[0] || user?.username?.[0] || 'U'}
                    </span>
                  </div>
                  <span className="hidden sm:block text-sm font-medium text-zinc-700">
                    {user?.full_name || user?.username}
                  </span>
                  <ChevronDown className="w-4 h-4 text-zinc-400 hidden sm:block" />
                </button>

                {userMenuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} />
                    <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-zinc-200 py-1 z-50">
                      <div className="px-3 py-2 border-b border-zinc-100">
                        <p className="text-sm font-medium text-zinc-900">{user?.username}</p>
                        <p className="text-xs text-zinc-500 capitalize">{user?.role}</p>
                      </div>
                      <Link
                        to="/settings"
                        className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
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
  user: any
  logout: () => void
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between h-14 px-4 border-b border-zinc-800">
        <Link to="/" className="flex items-center gap-2.5" onClick={onClose}>
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="text-base font-bold text-white tracking-tight">EDQ</span>
            <span className="text-[10px] text-zinc-400 block -mt-0.5 font-medium">Device Qualifier</span>
          </div>
        </Link>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-800 lg:hidden">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.label} className="mb-4">
            <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
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
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? 'bg-zinc-800 text-white border-l-2 border-blue-500 -ml-px'
                        : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
                    }`}
                  >
                    <item.icon className={`w-[18px] h-[18px] ${active ? 'text-blue-400' : ''}`} />
                    {item.name}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-3 py-3 border-t border-zinc-800">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center">
            <User className="w-4 h-4 text-zinc-300" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{user?.full_name || user?.username}</p>
            <p className="text-xs text-zinc-500 capitalize">{user?.role}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
