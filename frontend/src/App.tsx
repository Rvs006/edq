import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import DashboardLayout from './components/layout/DashboardLayout'
import { ErrorBoundary, PageErrorBoundary } from './components/common/ErrorBoundary'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import DevicesPage from './pages/DevicesPage'
import DeviceDetailPage from './pages/DeviceDetailPage'
import TestRunsPage from './pages/TestRunsPage'
import TestRunDetailPage from './pages/TestRunDetailPage'
import TemplatesPage from './pages/TemplatesPage'
import WhitelistsPage from './pages/WhitelistsPage'
import ReportsPage from './pages/ReportsPage'
import AuditLogPage from './pages/AuditLogPage'
import SettingsPage from './pages/SettingsPage'
import ReviewQueuePage from './pages/ReviewQueuePage'
import AdminPage from './pages/AdminPage'
import NetworkScanPage from './pages/NetworkScanPage'
import TestPlansPage from './pages/TestPlansPage'
import ScanSchedulesPage from './pages/ScanSchedulesPage'
import AgentsPage from './pages/AgentsPage'
import DeviceProfilesPage from './pages/DeviceProfilesPage'
import GuidedTour, { useTourState } from './components/tour/GuidedTour'

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-3 border-brand-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-zinc-500">Loading EDQ...</p>
      </div>
    </div>
  )
}

function LoginGate() {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <LoadingScreen />
  if (isAuthenticated) return <Navigate to="/" replace />
  return <LoginPage />
}

function AppShell() {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()
  const tour = useTourState()

  if (loading) return <LoadingScreen />

  if (!isAuthenticated) {
    if (location.pathname === '/') return <LandingPage />
    return <Navigate to="/" replace />
  }

  return (
    <>
      <DashboardLayout>
        <PageErrorBoundary>
          <Routes>
            <Route path="/" element={<DashboardPage tourState={tour} />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/test-runs" element={<TestRunsPage />} />
            <Route path="/test-runs/:id" element={<TestRunDetailPage />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/whitelists" element={<WhitelistsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/review" element={<ReviewQueuePage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/audit-log" element={<AuditLogPage />} />
            <Route path="/settings" element={<SettingsPage tourState={tour} />} />
            <Route path="/network-scan" element={<NetworkScanPage />} />
            <Route path="/test-plans" element={<TestPlansPage />} />
            <Route path="/scan-schedules" element={<ScanSchedulesPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/device-profiles" element={<DeviceProfilesPage />} />
          </Routes>
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
      <Routes>
        <Route path="/login" element={<LoginGate />} />
        <Route path="/*" element={<AppShell />} />
      </Routes>
    </ErrorBoundary>
  )
}
