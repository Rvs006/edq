import { useState, useEffect, useCallback } from 'react'
import { healthApi } from '@/lib/api'

interface SystemStatus {
  isOnline: boolean
  frontendHealthy: boolean
  backendHealthy: boolean
  databaseHealthy: boolean
  toolsHealthy: boolean
  toolsStatus: 'ok' | 'unavailable' | 'not_configured' | 'unknown'
  toolsMessage: string | null
  toolVersions: Record<string, string>
  lastChecked: Date | null
}

export function useOnlineStatus(): SystemStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [databaseHealthy, setDatabaseHealthy] = useState(true)
  const [toolsHealthy, setToolsHealthy] = useState(true)
  const [toolsStatus, setToolsStatus] = useState<'ok' | 'unavailable' | 'not_configured' | 'unknown'>('unknown')
  const [toolsMessage, setToolsMessage] = useState<string | null>(null)
  const [toolVersions, setToolVersions] = useState<Record<string, string>>({})
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      const res = await healthApi.systemStatus()
      const data = res.data
      setBackendHealthy(data.backend?.status === 'ok')
      setDatabaseHealthy(data.database?.status === 'ok')
      const sidecarStatus = data.tools_sidecar?.status || 'unknown'
      setToolsHealthy(sidecarStatus === 'ok')
      setToolsStatus(sidecarStatus as 'ok' | 'unavailable' | 'not_configured' | 'unknown')
      setToolsMessage(data.tools_sidecar?.message || null)
      setToolVersions(data.tools || {})
      setLastChecked(data.checked_at ? new Date(data.checked_at) : new Date())
    } catch {
      setBackendHealthy(false)
      setDatabaseHealthy(false)
      setToolsHealthy(false)
      setToolsStatus('unknown')
      setToolsMessage(null)
      setToolVersions({})
      setLastChecked(null)
    }
  }, [])

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  return {
    isOnline,
    frontendHealthy: true,
    backendHealthy,
    databaseHealthy,
    toolsHealthy,
    toolsStatus,
    toolsMessage,
    toolVersions,
    lastChecked,
  }
}
