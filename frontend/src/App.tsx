import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import DashboardLayout from './components/layout/DashboardLayout'
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
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/device-profiles" element={<DeviceProfilesPage />} />
        </Routes>
      </DashboardLayout>
      <GuidedTour
        isActive={tour.tourActive}
        currentStep={tour.currentStep}
        onNext={() => tour.setCurrentStep((s: number) => Math.min(s + 1, 7))}
        onPrev={() => tour.setCurrentStep((s: number) => Math.max(s - 1, 0))}
        onSkip={tour.skipTour}
        onComplete={tour.completeTour}
      />
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginGate />} />
      <Route path="/*" element={<AppShell />} />
    </Routes>
  )
}
