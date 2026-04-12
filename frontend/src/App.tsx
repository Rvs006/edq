import { Suspense, lazy, type ReactNode } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import DashboardLayout from './components/layout/DashboardLayout'
import { ErrorBoundary, PageErrorBoundary } from './components/common/ErrorBoundary'
import SkipToContent from './components/common/SkipToContent'
import GuidedTour, { useTourState } from './components/tour/GuidedTour'

const LandingPage = lazy(() => import('./pages/LandingPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DevicesPage = lazy(() => import('./pages/DevicesPage'))
const DeviceDetailPage = lazy(() => import('./pages/DeviceDetailPage'))
const DeviceComparePage = lazy(() => import('./pages/DeviceComparePage'))
const TestRunsPage = lazy(() => import('./pages/TestRunsPage'))
const TestRunDetailPage = lazy(() => import('./pages/TestRunDetailPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const WhitelistsPage = lazy(() => import('./pages/WhitelistsPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const AuditLogPage = lazy(() => import('./pages/AuditLogPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const ReviewQueuePage = lazy(() => import('./pages/ReviewQueuePage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const NetworkScanPage = lazy(() => import('./pages/NetworkScanPage'))
const TestPlansPage = lazy(() => import('./pages/TestPlansPage'))
const ScanSchedulesPage = lazy(() => import('./pages/ScanSchedulesPage'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const DeviceProfilesPage = lazy(() => import('./pages/DeviceProfilesPage'))
const AuthorizedNetworksPage = lazy(() => import('./pages/AuthorizedNetworksPage'))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

function LoadingScreen() {
  return (
    <main id="main-content" tabIndex={-1} className="min-h-screen flex items-center justify-center bg-surface">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-3 border-brand-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-zinc-500">Loading EDQ...</p>
      </div>
    </main>
  )
}

function AccessDeniedPage() {
  return (
    <div className="page-container py-12">
      <div className="card max-w-2xl p-8">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-slate-100">Access denied</h1>
        <p className="mt-2 text-sm text-zinc-500 dark:text-slate-400">
          Your account does not have permission to view this page.
        </p>
      </div>
    </div>
  )
}

function LoginGate() {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <LoadingScreen />
  if (isAuthenticated) return <Navigate to="/" replace />
  return (
    <Suspense fallback={<LoadingScreen />}>
      <main id="main-content" tabIndex={-1}>
        <LoginPage />
      </main>
    </Suspense>
  )
}

function RequireRole({ allowed, children }: { allowed: string[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (!allowed.includes(user.role)) {
    return <AccessDeniedPage />
  }
  return <>{children}</>
}

function AppShell() {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()
  const tour = useTourState()

  if (loading) return <LoadingScreen />

  if (!isAuthenticated) {
    if (location.pathname === '/') {
      return (
        <Suspense fallback={<LoadingScreen />}>
          <main id="main-content" tabIndex={-1}>
            <LandingPage />
          </main>
        </Suspense>
      )
    }
    const raw = `${location.pathname}${location.search}${location.hash}`
    const next = raw.startsWith('/') && !raw.startsWith('//') ? raw : '/'
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }

  return (
    <>
      <DashboardLayout>
        <PageErrorBoundary>
          <Suspense fallback={<LoadingScreen />}>
            <Routes>
              <Route path="/" element={<DashboardPage tourState={tour} />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/devices" element={<DevicesPage />} />
              <Route path="/devices/compare" element={<DeviceComparePage />} />
              <Route path="/devices/:id" element={<DeviceDetailPage />} />
              <Route path="/test-runs" element={<TestRunsPage />} />
              <Route path="/test-runs/:id" element={<TestRunDetailPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/whitelists" element={<WhitelistsPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/review" element={<RequireRole allowed={['reviewer', 'admin']}><ReviewQueuePage /></RequireRole>} />
              <Route path="/admin" element={<RequireRole allowed={['admin']}><AdminPage /></RequireRole>} />
              <Route path="/audit-log" element={<RequireRole allowed={['reviewer', 'admin']}><AuditLogPage /></RequireRole>} />
              <Route path="/settings" element={<SettingsPage tourState={tour} />} />
              <Route path="/network-scan" element={<NetworkScanPage />} />
              <Route path="/test-plans" element={<TestPlansPage />} />
              <Route path="/scan-schedules" element={<ScanSchedulesPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/device-profiles" element={<DeviceProfilesPage />} />
              <Route path="/authorized-networks" element={<AuthorizedNetworksPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </PageErrorBoundary>
      </DashboardLayout>
      <GuidedTour
        isActive={tour.tourActive}
        currentStep={tour.currentStep}
        onNext={() => tour.setCurrentStep((s: number) => Math.min(s + 1, 7))}
        onPrev={() => tour.setCurrentStep((s: number) => Math.max(s - 1, 0))}
        onSkip={tour.skipTour}
        onComplete={tour.completeTour}
      />
      {tour.showWelcomeBanner && (
        <div className="fixed bottom-4 right-4 z-[8000] bg-white dark:bg-dark-card rounded-xl shadow-2xl border border-zinc-200 dark:border-slate-700 p-5 max-w-sm animate-fade-in">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-50 dark:bg-brand-950/40 flex items-center justify-center flex-shrink-0">
              <span className="text-lg">🚀</span>
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-1">Welcome to EDQ!</h3>
              <p className="text-sm text-zinc-600 dark:text-slate-400 mb-3 leading-relaxed">
                Take a quick guided tour to learn about the testing workflow.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={tour.startTour}
                  className="px-3 py-1.5 text-xs font-medium bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors"
                >
                  Start Tour
                </button>
                <button
                  onClick={tour.dismissTour}
                  className="px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                >
                  Skip
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <SkipToContent />
      <Routes>
        <Route path="/login" element={<LoginGate />} />
        <Route path="/*" element={<AppShell />} />
      </Routes>
    </ErrorBoundary>
  )
}
