import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import DashboardLayout from './components/layout/DashboardLayout'
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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-brand-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zinc-500">Loading EDQ...</p>
        </div>
      </div>
    )
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
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
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/network-scan" element={<NetworkScanPage />} />
              </Routes>
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}
